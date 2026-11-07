"""技能包加载与解析（PART 7.2 / 7.3）。

解析分三层，各自做一件事：
1. :class:`FrontmatterParser` —— 极简 frontmatter（不能用 PyYAML，值是中文带冒号的散文）；
2. :class:`DispatchTableParser` —— 按**表头名**取列（不是按位置，`s-1-revenue` 少一列）；
3. :class:`DSLParser` —— 归一化真实 dsl.json（字段与 docs/skill-spec.md 不一致）。

合并策略见 :func:`merge_procedure`：任一来源认为需要人工，结果就要人。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.models.enums import ConflictSeverity, ExecutionMode
from agent.models.procedure import ConflictRecord, ExecutionPolicy, ProcedureDefinition

PROC_ID_RE = re.compile(r"^[A-Z]\d{1,3}$")
WORKPAPER_INDEX_RE = re.compile(r"\b([ZFQS]-\d+(?:-\d+)*-\d+)\b")
# 程序卡 Steps 里的执行主体标签，是"该步骤谁来做"最细的信号
STEP_TAG_RE = re.compile(r"【(脚本|规则|人工)】")
# 「（强制）」这类标记出现在程序名里
MANDATORY_HINT_RE = re.compile(r"强制|必须实施")
# 条件程序提示句：「P09 视资金池/集团情况决定是否启用」
CONDITIONAL_HINT_RE = re.compile(
    r"(P\d{1,3})[^。；;\n]{0,40}?(视[^。；;\n]{0,30}?|根据[^。；;\n]{0,30}?|如[^。；;\n]{0,20}?)"
    r"(决定是否启用|决定启用|决定是否实施|启用)"
)


def parse_frontmatter(text: str) -> dict[str, str]:
    """极简 frontmatter 解析：只取顶层 ``key: value``。

    为什么不用 PyYAML：真实值里有中文冒号、全角括号、未转义的引号，
    严格 YAML 解析会直接抛异常，而 `build_index.py` 用的是同一套宽松逻辑。
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    key: str | None = None
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] not in (" ", "\t") and ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            data[key] = val
        elif key and line[:1] in (" ", "\t"):
            data[key] = (data.get(key, "") + " " + line.strip()).strip()
    return data


@dataclass
class DispatchRow:
    """程序分派表的一行。"""

    procedure_id: str
    name: str
    source: str = ""
    assertions: list[str] = field(default_factory=list)
    execution_method: str = ""
    workpaper_index: str | None = None
    raw_cells: dict[str, str] = field(default_factory=dict)


class DispatchTableParser:
    """解析 SKILL.md 的「程序分派表」。

    关键设计：**按表头名映射列**。实测 25 个包是 6 列
    （程序卡/程序名称/程序库来源/对应认定/执行方式/产出底稿），
    `s-1-revenue` 只有 5 列（无「执行方式」）。按位置取值会让它的
    「产出底稿」被当成「执行方式」读走，且不报错——静默错位最危险。
    """

    HEADER_ALIASES: dict[str, str] = {
        "程序卡": "procedure_id",
        "程序序号": "procedure_id",
        "编号": "procedure_id",
        "程序名称": "name",
        "程序库来源": "source",
        "来源": "source",
        "对应认定": "assertions",
        "认定": "assertions",
        "执行方式": "execution_method",
        "产出底稿": "workpaper_index",
        "底稿索引": "workpaper_index",
    }

    def parse(self, skill_md_text: str) -> list[DispatchRow]:
        rows: list[DispatchRow] = []
        columns: dict[int, str] = {}
        for line in skill_md_text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("|"):
                if columns and rows:
                    break  # 表已结束
                columns = {}
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not cells:
                continue
            # 表头行
            if "程序卡" in cells or "编号" in cells:
                columns = {}
                for idx, cell in enumerate(cells):
                    key = self.HEADER_ALIASES.get(cell)
                    if key:
                        columns[idx] = key
                continue
            if not columns:
                continue
            first = cells[0] if cells else ""
            if not PROC_ID_RE.match(first):
                continue  # 分隔行 |---|---| 或空行
            record: dict[str, str] = {}
            for idx, key in columns.items():
                record[key] = cells[idx] if idx < len(cells) else ""
            rows.append(
                DispatchRow(
                    procedure_id=first,
                    name=record.get("name", ""),
                    source=record.get("source", ""),
                    assertions=_split_assertions(record.get("assertions", "")),
                    execution_method=record.get("execution_method", ""),
                    workpaper_index=_extract_workpaper_index(record.get("workpaper_index", "")),
                    raw_cells=record,
                )
            )
        return rows


def _split_assertions(raw: str) -> list[str]:
    """「C、E、A」→ ['C','E','A']，保持顺序去重。"""
    parts = re.split(r"[、,，/\s]+", raw or "")
    out: list[str] = []
    for p in parts:
        token = p.strip().upper()
        if token in {"E", "C", "A", "V", "P"} and token not in out:
            out.append(token)
    return out


def _extract_workpaper_index(raw: str) -> str | None:
    """从「产出底稿」列提取索引号。

    真实取值有 4 种特殊形态：`引用《A.01 银行函证工作簿》`（提不出）、
    `Z-1-2-04 附区`（提取 Z-1-2-04）、`联动 Z-1-2-10（回函核对入 F-1-02）`（取第一个）。
    """
    m = WORKPAPER_INDEX_RE.search(raw or "")
    return m.group(1) if m else None


class DSLParser:
    """解析并归一化 ``dsl.json``。

    真实 schema（27 个包实测完全一致）::

        {skill_id, name, version, owner_role, cycle, group_code,
         risk_level, description, procedures[], quality_gate}

        procedures 元素：{id, name, tools?, human?}

    与 ``docs/skill-spec.md`` 描述的差异（``skill``/``assertions``/``mode``/
    ``output``/``source``）在本类里被**显式容忍**：读到就收，读不到置 None，
    绝不脑补默认值。
    """

    ROOT_ALIASES = {"skill": "skill_id"}

    def parse(self, skill_dir: Path) -> dict[str, Any]:
        dsl_file = Path(skill_dir) / "dsl.json"
        if not dsl_file.is_file():
            return {}
        raw = json.loads(dsl_file.read_text(encoding="utf-8"))
        return self.normalize(raw)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError(f"dsl.json 顶层必须是对象，实际是 {type(raw).__name__}")
        out: dict[str, Any] = {}
        for key, value in raw.items():
            out[self.ROOT_ALIASES.get(key, key)] = value

        procedures = out.get("procedures")
        if procedures is None:
            procedures = []
        if not isinstance(procedures, list):
            raise ValueError("dsl.json 的 procedures 必须是数组")

        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in procedures:
            if not isinstance(item, dict):
                raise ValueError(f"procedures 元素必须是对象：{item!r}")
            pid = str(item.get("id") or "").strip()
            if not PROC_ID_RE.match(pid):
                raise ValueError(f"非法程序 ID：{pid!r}（应为 P01 或 G1 形态）")
            if pid in seen:
                raise ValueError(f"程序 ID 重复：{pid}")
            seen.add(pid)
            normalized.append(
                {
                    "id": pid,
                    "name": str(item.get("name") or "").strip(),
                    "tools": _as_str_list(item.get("tools")),
                    # 三态：True / False / None（未知）。None 不能被当成 False。
                    "human": _as_optional_bool(item.get("human")),
                    "assertions": _as_str_list(item.get("assertions")),
                    "mode": item.get("mode"),
                    "output": item.get("output"),
                    "source": item.get("source"),
                }
            )
        out["procedures"] = normalized
        out["quality_gate"] = out.get("quality_gate") or {}
        return out


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    raise ValueError(f"期望字符串数组，实际是 {type(value).__name__}")


def _as_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
    raise ValueError(f"human 字段只能是布尔或缺失，实际是 {value!r}")


def infer_policy(execution_method: str, dsl_human: bool | None, card_has_human_step: bool) -> ExecutionPolicy:
    """从三源推断执行策略（PART 11.3：取最严，不降级）。

    这是**故意保守**的：只要文本里出现「人工」，就要求人工确认。
    号称"自动+人工判断"的程序如果被当成全自动跑，等于把审计判断交给了模型。
    """
    text = execution_method or ""
    rationale: list[str] = []

    human_led = ("人工为主" in text) or ("人工主导" in text)
    has_judgment = ("判断" in text) or ("评价" in text)
    has_confirm = "人工" in text
    human_confirmation = has_confirm or card_has_human_step or bool(dsl_human)

    if dsl_human is not None:
        rationale.append(f"dsl.human={dsl_human}")
    if execution_method:
        rationale.append(f"SKILL.md 执行方式=「{execution_method}」")
    if card_has_human_step:
        rationale.append("程序卡 Steps 含【人工】步骤")

    if human_led:
        mode = ExecutionMode.HUMAN_LED
    elif has_judgment:
        mode = ExecutionMode.AUTO_WITH_JUDGMENT
    elif has_confirm or card_has_human_step or dsl_human:
        mode = ExecutionMode.AUTO_WITH_CONFIRM
    else:
        mode = ExecutionMode.AUTO

    # 模式与人工标记必须自洽：只要有人工，mode 不能停在 AUTO
    if mode is ExecutionMode.AUTO and (human_confirmation or has_judgment):
        mode = ExecutionMode.AUTO_WITH_CONFIRM

    return ExecutionPolicy(
        automated_execution=True,
        human_confirmation=human_confirmation,
        human_judgment=has_judgment or human_led,
        mandatory=False,  # 由调用方按程序名/配置补
        conditional=False,
        mode=mode,
        rationale=rationale,
    )


def card_has_human_step(card_text: str) -> bool:
    """程序卡 Steps 里是否有【人工】标签。"""
    return "【人工】" in card_text


def merge_procedure(
    *,
    skill_id: str,
    skill_version: str,
    dsl_proc: dict[str, Any],
    dispatch: DispatchRow | None,
    card_text: str,
    procedure_doc: str | None,
) -> tuple[ProcedureDefinition, list[ConflictRecord]]:
    """三源合并为一条 :class:`ProcedureDefinition`，并产出冲突记录。"""
    pid = dsl_proc["id"]
    conflicts: list[ConflictRecord] = []
    sources: dict[str, str] = {"id": "dsl"}

    name = dsl_proc.get("name") or (dispatch.name if dispatch else "")
    if dispatch and dispatch.name and dsl_proc.get("name") and dispatch.name != dsl_proc["name"]:
        conflicts.append(
            ConflictRecord(
                skill_id=skill_id,
                procedure_id=pid,
                field="name",
                values={"dsl": dsl_proc["name"], "skill_md": dispatch.name},
                resolved=dsl_proc["name"],
                severity=ConflictSeverity.INFO,
                note="程序名表述差异，以 DSL 为准（DSL 更短，用于显示）",
            )
        )
    sources["name"] = "dsl" if dsl_proc.get("name") else "skill_md"

    execution_method = dispatch.execution_method if dispatch else ""
    has_human_step = card_has_human_step(card_text)
    dsl_human = dsl_proc.get("human")

    policy = infer_policy(execution_method, dsl_human, has_human_step)
    sources["execution_policy"] = "dsl+skill_md+procedure_card"

    # 冲突：DSL 说 false，但 SKILL.md 或程序卡要求人工
    if dsl_human is False and policy.requires_human:
        conflicts.append(
            ConflictRecord(
                skill_id=skill_id,
                procedure_id=pid,
                field="human",
                values={
                    "dsl": "false",
                    "skill_md": execution_method or "(无执行方式列)",
                    "procedure_card": "有【人工】步骤" if has_human_step else "无",
                },
                resolved="true（保守取严，不得自动降低人工要求）",
                severity=ConflictSeverity.BLOCKING,
                note="DSL 未声明人工要求，但技能正文要求人工；按 PART 11.3 采用保守策略",
            )
        )

    mandatory = bool(MANDATORY_HINT_RE.search(name))
    if mandatory:
        sources["mandatory"] = "skill_md_name"

    assertions = dispatch.assertions if dispatch else []
    if assertions:
        sources["assertions"] = "skill_md"

    workpaper_index = dispatch.workpaper_index if dispatch else None
    if workpaper_index:
        sources["workpaper_index"] = "skill_md"

    source_text = (dispatch.source if dispatch and dispatch.source else "") or str(
        dsl_proc.get("source") or ""
    )

    proc = ProcedureDefinition(
        id=pid,
        name=name,
        description="",
        tools=list(dsl_proc.get("tools") or []),
        assertions=assertions,
        execution_policy=policy,
        dependencies=[],  # DSL 无依赖，由运行时配置提供
        mandatory=mandatory,
        conditional=False,
        condition=None,
        source=source_text,
        workpaper_index=workpaper_index,
        procedure_doc=procedure_doc,
        skill_id=skill_id,
        skill_version=skill_version,
        sources=sources,
    )
    return proc, conflicts
