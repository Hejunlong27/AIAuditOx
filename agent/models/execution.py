"""Execution records shared by the runtime state machine and orchestrator."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from agent.models.base import AuditModel, utcnow
from agent.models.enums import FailureClass, TaskStatus


class ToolCall(AuditModel):
    """A deterministic tool call requested for one audit procedure."""

    tool_name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_granted: bool = False


class HumanSubmission(AuditModel):
    """Material supplied by a human for a procedure awaiting review."""

    step_id: str = Field(pattern=r"^[A-Z]\d{1,3}$")
    actor: str = Field(min_length=1, max_length=128)
    comment: str = ""
    evidence_files: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _submission_needs_content(self) -> "HumanSubmission":
        if not self.comment.strip() and not self.evidence_files:
            raise ValueError("人工提交必须包含说明或证据文件")
        return self


class QualityDecision(AuditModel):
    """Procedure-level quality gate decision."""

    passed: bool = False
    requires_human: bool = False
    retryable: bool = False
    terminal: bool = False
    reason: str = ""
    failure_class: FailureClass | None = None

    @model_validator(mode="after")
    def _one_outcome(self) -> "QualityDecision":
        outcomes = sum((self.passed, self.requires_human, self.retryable, self.terminal))
        if outcomes != 1:
            raise ValueError("质量门决策必须且只能选择 passed/requires_human/retryable/terminal 之一")
        return self

    @classmethod
    def pass_(cls, reason: str = "") -> "QualityDecision":
        return cls(passed=True, reason=reason)

    @classmethod
    def human(cls, reason: str) -> "QualityDecision":
        return cls(requires_human=True, reason=reason, failure_class=FailureClass.NEED_HUMAN)

    @classmethod
    def retry(cls, reason: str) -> "QualityDecision":
        return cls(retryable=True, reason=reason, failure_class=FailureClass.RETRYABLE)

    @classmethod
    def fail(cls, reason: str) -> "QualityDecision":
        return cls(terminal=True, reason=reason, failure_class=FailureClass.TERMINAL)


class StateChange(AuditModel):
    """One auditable task or step state transition."""

    task_id: str = Field(min_length=1)
    object_type: str = Field(pattern=r"^(task|step)$")
    object_id: str = Field(min_length=1)
    from_status: str = Field(min_length=1)
    to_status: str = Field(min_length=1)
    actor: str = Field(default="system", min_length=1, max_length=128)
    reason: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class OrchestrationResult(AuditModel):
    """Serializable snapshot returned after one orchestration pass."""

    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: TaskStatus
    verified_steps: list[str] = Field(default_factory=list)
    waiting_human_steps: list[str] = Field(default_factory=list)
    waiting_input_steps: list[str] = Field(default_factory=list)
    failed_steps: list[str] = Field(default_factory=list)
    skipped_steps: list[str] = Field(default_factory=list)
    replans: int = Field(default=0, ge=0)
    message: str = ""


__all__ = [
    "HumanSubmission",
    "OrchestrationResult",
    "QualityDecision",
    "StateChange",
    "ToolCall",
]