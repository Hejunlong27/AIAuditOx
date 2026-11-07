"""技能注册表（PART 7.1）。

**唯一索引源是 ``registry/skills.json``**，由 ``tools/build_index.py`` 生成。
本模块只读，绝不另建第二套索引（任务书 PART 7.1 明令禁止）。

同时提供 ``refresh()``——它调用生成器的库函数而非重写扫描逻辑，
保证"运行时看到的技能清单"与"CI 校验的技能清单"永远一致。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from agent.security.workspace import SecurityError


def _load_module(path: Path, name: str) -> ModuleType:
    """按文件路径加载一个模块（用于复用 tools/ 下的生成器脚本）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class SkillEntry:
    """注册表里的一条技能记录。"""

    id: str
    name: str
    version: str
    description: str
    variant: str
    path: str
    tools: tuple[str, ...]
    procedure_count: int

    @property
    def is_skill_group(self) -> bool:
        return self.variant == "skill-group"


class SkillRegistry:
    """技能发现入口。"""

    SUPPORTED_SCHEMA = 1

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.registry_file = self.repo_root / "registry" / "skills.json"
        self._entries: dict[str, SkillEntry] = {}
        self._loaded = False
        self.schema_version = 0
        self.generated_at = ""

    # ---------- 加载 ----------

    def load(self) -> "SkillRegistry":
        if not self.registry_file.is_file():
            raise FileNotFoundError(
                f"技能索引不存在：{self.registry_file}；请先运行 python tools/build_index.py"
            )
        raw = json.loads(self.registry_file.read_text(encoding="utf-8"))
        self.schema_version = int(raw.get("schemaVersion", 0))
        if self.schema_version != self.SUPPORTED_SCHEMA:
            raise ValueError(
                f"技能索引 schemaVersion={self.schema_version} 不受支持（期望 {self.SUPPORTED_SCHEMA}）"
            )
        self.generated_at = str(raw.get("generatedAt", ""))
        entries: dict[str, SkillEntry] = {}
        for item in raw.get("skills", []):
            entry = SkillEntry(
                id=item["id"],
                name=item.get("name") or item["id"],
                version=str(item.get("version") or ""),
                description=item.get("description") or "",
                variant=item.get("variant") or "standard",
                path=item.get("path") or f"skills/{item['id']}",
                tools=tuple(item.get("tools") or ()),
                procedure_count=int((item.get("counts") or {}).get("procedures") or 0),
            )
            entries[entry.id] = entry
        self._entries = entries
        self._loaded = True
        return self

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def refresh(self, *, write: bool = False) -> int:
        """重建索引。

        默认只读校验（``--check`` 语义），``write=True`` 才落盘——
        避免每次刷新都改 ``generatedAt`` 制造无意义 diff。

        实现上复用 ``tools/build_index.py`` 的 ``main()``（通过 argv 注入
        ``--check``），不复制扫描逻辑，保证运行时与 CI 的判别规则永不es分叉。
        """
        gen = self.repo_root / "tools" / "build_index.py"
        if not gen.is_file():
            raise FileNotFoundError(f"索引生成器不存在：{gen}")
        module = _load_module(gen, "_auditox_build_index")
        saved_argv = sys.argv
        try:
            sys.argv = [str(gen)] + ([] if write else ["--check"])
            code = module.main()
        finally:
            sys.argv = saved_argv
        if code != 0 and write is False:
            raise RuntimeError(
                f"技能索引校验未通过（退出码 {code}），存在缺 SKILL.md 的技能包"
            )
        self._loaded = False
        self.load()
        return len(self._entries)

    # ---------- 查询 ----------

    def get(self, skill_id: str) -> SkillEntry:
        self._ensure_loaded()
        try:
            return self._entries[skill_id]
        except KeyError:
            raise KeyError(
                f"未注册的技能 {skill_id!r}；可用示例：{', '.join(self.list_ids()[:5])}"
            ) from None

    def has(self, skill_id: str) -> bool:
        self._ensure_loaded()
        return skill_id in self._entries

    def list_ids(self) -> list[str]:
        self._ensure_loaded()
        return sorted(self._entries)

    def list_skills(self, *, variant: str | None = None) -> list[SkillEntry]:
        self._ensure_loaded()
        items = [self._entries[k] for k in self.list_ids()]
        if variant:
            items = [s for s in items if s.variant == variant]
        return items

    def get_skill_path(self, skill_id: str) -> Path:
        """技能的绝对目录，且必须落在仓库 ``skills/`` 内。"""
        entry = self.get(skill_id)
        path = (self.repo_root / entry.path).resolve()
        skills_root = (self.repo_root / "skills").resolve()
        if not path.is_relative_to(skills_root):
            raise SecurityError(f"技能路径越界：{path} 不在 {skills_root} 内")
        if not path.is_dir():
            raise FileNotFoundError(f"技能目录不存在：{path}")
        return path

    def search(self, query: str, *, limit: int = 10) -> list[SkillEntry]:
        """关键词检索。

        打分规则（确定性、可解释，不依赖模型）：
        - 技能 ID 完全命中：100
        - ID 片段命中：40
        - 名称命中：30
        - 描述命中：10
        - 每个命中词累加，最后按分数降序、ID 升序稳定排序。
        """
        self._ensure_loaded()
        terms = [t for t in _tokenize(query) if t]
        if not terms:
            return []
        scored: list[tuple[int, SkillEntry]] = []
        for sid in self.list_ids():
            entry = self._entries[sid]
            score = 0
            low_id = entry.id.lower()
            low_name = entry.name.lower()
            low_desc = entry.description.lower()
            for term in terms:
                if term == low_id:
                    score += 100
                elif term in low_id:
                    score += 40
                if term in low_name:
                    score += 30
                if term in low_desc:
                    score += 10
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return [e for _, e in scored[:limit]]


def _tokenize(query: str) -> list[str]:
    """把查询切成检索词：中文按 2 字滑窗 + 英文/数字整体保留。

    中文没有空格，直接整串匹配会大量漏检（"银行存款审计" 与描述里的
    "银行存款" 就无法命中），所以做 2-gram 滑窗。
    """
    import re

    text = (query or "").strip().lower()
    if not text:
        return []
    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9][a-z0-9\-_]*", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(chunk) <= 2:
            tokens.append(chunk)
        else:
            tokens.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return tokens
