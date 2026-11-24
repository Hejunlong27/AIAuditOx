"""Base contracts for deterministic skill adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Protocol

from agent.models.execution import ToolCall
from agent.models.plan import PlanStep
from agent.models.task import AuditTask


class AdapterError(RuntimeError):
    """The task inputs cannot be converted to safe tool calls."""


class SkillAdapter(Protocol):
    """Convert one skill's normalized inputs into explicit tool calls."""

    skill_id: str

    def calls_for(self, task: AuditTask, step: PlanStep) -> list[ToolCall]:
        ...


class AutoToolCallProvider:
    """Callable adapter used by AgentOrchestrator."""

    def __init__(self, adapter: SkillAdapter) -> None:
        self.adapter = adapter

    def __call__(self, task: AuditTask, step: PlanStep) -> list[ToolCall]:
        return self.adapter.calls_for(task, step)


AdapterInputs = Mapping[str, Path]

__all__ = ["AdapterError", "AdapterInputs", "AutoToolCallProvider", "SkillAdapter"]
