"""Host-neutral tool-call providers for the application layer."""

from __future__ import annotations

import json
from pathlib import Path
from agent.models.execution import ToolCall
from agent.models.plan import PlanStep
from agent.models.task import AuditTask


class JsonToolCallProvider:
    """Read explicit per-procedure calls from a local JSON object.

    The format is intentionally explicit rather than heuristic: callers must
    supply arguments for every declared tool. The orchestrator still enforces
    that no missing or undeclared tool call is accepted.
    """

    def __init__(self, calls: dict[str, list[ToolCall]]) -> None:
        self.calls = calls

    @classmethod
    def from_file(cls, path: Path) -> "JsonToolCallProvider":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("工具调用文件根节点必须是对象")
        calls: dict[str, list[ToolCall]] = {}
        for step_id, items in raw.items():
            if not isinstance(items, list):
                raise ValueError(f"步骤 {step_id} 的工具调用必须是数组")
            calls[str(step_id)] = [ToolCall.model_validate(item) for item in items]
        return cls(calls)

    def __call__(self, _task: AuditTask, step: PlanStep) -> list[ToolCall]:
        return list(self.calls.get(step.step_id, []))


__all__ = ["JsonToolCallProvider"]
