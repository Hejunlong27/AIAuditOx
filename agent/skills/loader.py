"""技能加载器（PART 7.2）。

职责：把散落在文件系统里的技能包读成结构化对象，并保证**任何路径都不越出
``skills/``**。它只读，不写——技能库是资产，运行时无权修改。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agent.models.procedure import ConflictRecord, ProcedureDefinition
from agent.security.workspace import SecurityError
from agent.skills.parser import (
    CONDITIONAL_HINT_RE,
    DSLParser,
    DispatchRow,
    DispatchTableParser,
    merge_procedure,
    parse_frontmatter,
)
from agent.skills.registry import SkillEntry, SkillRegistry


@dataclass
class LoadedSkill:
    """一个技能包的完整内存视图。"""

    entry: SkillEntry
    root: Path
    frontmatter: dict[str, str]
    skill_md: str
    dsl: dict
    dispatch_rows: list[DispatchRow]
    procedures: list[ProcedureDefinition]
    conflicts: list[ConflictRecord]
    missing_procedure_docs: list[str]


class SkillLoader:
    """技能包读取器。"""

    def __init__(self, repo_root: Path, registry: SkillRegistry | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.skills_root = (self.repo_root / "skills").resolve()
        self.registry = registry or SkillRegistry(self.repo_root).load()
        self._dsl_parser = DSLParser()
        self._table_parser = DispatchTableParser()
        self._cache: dict[str, LoadedSkill] = {}

    # ---------- 路径安全 ----------

    def skill_dir(self, skill_id: str) -> Path:
        path = self.registry.get_skill_path(skill_id)
        if not path.is_relative_to(self.skills_root):
            raise SecurityError(f"技能目录越界：{path}")
        return path

    def _safe_child(self, skill_dir: Path, relative: str) -> Path:
        """技能包内相对路径解析，拒绝 ``..`` 与绝对路径。"""
        candidate = (skill_dir / relative).resolve()
        if not candidate.is_relative_to(skill_dir):
            raise SecurityError(f"技能包内路径越界：{relative!r}")
        return candidate

    # ---------- 基础读取 ----------

    def load_skill(self, skill_id: str) -> LoadedSkill:
        if skill_id in self._cache:
            return self._cache[skill_id]

        entry = self.registry.get(skill_id)
        root = self.skill_dir(skill_id)
        skill_md_path = root / "SKILL.md"
        if not skill_md_path.is_file():
            raise FileNotFoundError(f"技能 {skill_id} 缺 SKILL.md：{skill_md_path}")
        skill_md = skill_md_path.read_text(encoding="utf-8", errors="replace")

        dsl = self._dsl_parser.parse(root) if (root / "dsl.json").is_file() else {}
        dispatch_rows = self._table_parser.parse(skill_md)
        by_id = {r.procedure_id: r for r in dispatch_rows}

        procedures: list[ProcedureDefinition] = []
        conflicts: list[ConflictRecord] = []
        missing_docs: list[str] = []
        procedure_dir = root / "procedures"

        for dsl_proc in dsl.get("procedures") or []:
            pid = dsl_proc["id"]
            card_path = self._find_procedure_card(procedure_dir, pid)
            card_text = card_path.read_text(encoding="utf-8", errors="replace") if card_path else ""
            if card_path is None:
                missing_docs.append(pid)
            proc, proc_conflicts = merge_procedure(
                skill_id=skill_id,
                skill_version=entry.version,
                dsl_proc=dsl_proc,
                dispatch=by_id.get(pid),
                card_text=card_text,
                procedure_doc=(
                    str(card_path.relative_to(root)).replace("\\", "/") if card_path else None
                ),
            )
            procedures.append(proc)
            conflicts.extend(proc_conflicts)

        # 条件程序：只在 SKILL.md 正文里以自然语言出现，用限定句式提取
        conditions = _extract_conditions(skill_md)
        if conditions:
            updated: list[ProcedureDefinition] = []
            for p in procedures:
                if p.id in conditions:
                    p.conditional = True
                    p.condition = conditions[p.id]
                    p.sources["conditional"] = "skill_md_steps"
                updated.append(p)
            procedures = updated

        loaded = LoadedSkill(
            entry=entry,
            root=root,
            frontmatter=parse_frontmatter(skill_md),
            skill_md=skill_md,
            dsl=dsl,
            dispatch_rows=dispatch_rows,
            procedures=procedures,
            conflicts=conflicts,
            missing_procedure_docs=missing_docs,
        )
        self._cache[skill_id] = loaded
        return loaded

    def _find_procedure_card(self, procedure_dir: Path, procedure_id: str) -> Path | None:
        """按文件名前缀定位程序卡，如 ``P01-银行存款余额明细表编制.md``。"""
        if not procedure_dir.is_dir():
            return None
        for p in sorted(procedure_dir.glob("*.md")):
            if p.name.startswith(procedure_id) and (len(p.name) == len(procedure_id) or p.name[len(procedure_id)] in "-_ "):
                return p
        return None

    # ---------- 细分读取 ----------

    def load_dsl(self, skill_id: str) -> dict:
        skill_dir = self.skill_dir(skill_id)
        path = skill_dir / "dsl.json"
        if not path.is_file():
            return {}
        return self._dsl_parser.parse(skill_dir)

    def load_procedure(self, skill_id: str, procedure_id: str) -> ProcedureDefinition:
        loaded = self.load_skill(skill_id)
        for p in loaded.procedures:
            if p.id == procedure_id:
                return p
        raise KeyError(f"技能 {skill_id} 中不存在程序 {procedure_id}")

    def load_procedure_card(self, skill_id: str, procedure_id: str) -> str:
        """读程序卡原文，供 LLM 分析或人工复核引用。"""
        root = self.skill_dir(skill_id)
        card = self._find_procedure_card(root / "procedures", procedure_id)
        if card is None:
            raise FileNotFoundError(f"技能 {skill_id} 缺程序 {procedure_id} 的程序卡文档")
        return card.read_text(encoding="utf-8", errors="replace")

    def load_template(self, skill_id: str, template_name: str) -> Path:
        """返回技能包 ``templates/`` 下的模板路径（只校验存在性，不复制）。"""
        root = self.skill_dir(skill_id)
        path = self._safe_child(root, f"templates/{template_name}")
        if not path.is_file():
            available = sorted(p.name for p in (root / "templates").glob("*")) if (root / "templates").is_dir() else []
            raise FileNotFoundError(
                f"技能 {skill_id} 缺模板 {template_name!r}；可用：{available}"
            )
        return path

    def list_templates(self, skill_id: str) -> list[str]:
        root = self.skill_dir(skill_id)
        tdir = root / "templates"
        if not tdir.is_dir():
            return []
        return sorted(p.name for p in tdir.iterdir() if p.is_file())

    def load_wp_standard(self) -> dict:
        """加载全局底稿制式规范。

        编制任何底稿前必须先读它（AGENTS.md 强制）。返回结构化要点，
        供 Workpaper Writer 与质量门做确定性校验。
        """
        skill_id = "auditox-wp-standard"
        root = self.skill_dir(skill_id)
        text = (root / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        return {
            "skill_id": skill_id,
            "version": self.registry.get(skill_id).version,
            "path": str(root),
            "sections": ["一、项目基本信息", "二、审计目标和程序说明", "三、审计程序执行结果", "四、审计说明"],
            "header_elements": ["被审计单位", "审计期间", "编制人", "编制日期", "审核人", "审核日期", "索引号"],
            "index_pattern": r"^[ZFQS]-\d+(-\d+)*-\d+(SA|SB|SC)?$",
            "raw": text,
        }

    def load_template_bytes(self, skill_id: str, template_name: str) -> bytes:
        """读模板二进制（用于复制到工作区后再填充，绝不原地改模板）。"""
        return self.load_template(skill_id, template_name).read_bytes()

    def clear_cache(self) -> None:
        self._cache.clear()

    # ---------- 便捷查询 ----------

    def list_procedure_ids(self, skill_id: str) -> list[str]:
        return [p.id for p in self.load_skill(skill_id).procedures]

    def export_conflicts(self, skill_id: str) -> list[dict]:
        loaded = self.load_skill(skill_id)
        return [json.loads(c.model_dump_json()) for c in loaded.conflicts]


def _extract_conditions(skill_md: str) -> dict[str, str]:
    """从 SKILL.md 正文提取条件程序的启用条件。

    只认「P09 视资金池/集团情况决定是否启用」这类限定句式——
    宁可漏识别（条件程序被当成必做，更保守），不可把普通叙述误判成条件
    （那会让强制程序被跳过）。
    """
    out: dict[str, str] = {}
    for m in CONDITIONAL_HINT_RE.finditer(skill_md):
        pid = m.group(1)
        sentence = m.group(0).strip()
        if pid not in out:
            out[pid] = sentence
    return out
