"""Application-layer value objects."""

from __future__ import annotations

from pydantic import Field

from agent.models.approval import ApprovalRequest
from agent.models.base import AuditModel
from agent.models.execution import OrchestrationResult
from agent.models.plan import AuditPlan
from agent.models.project import AuditProject
from agent.models.task import AuditTask


class TaskBundle(AuditModel):
    """Project, task and validated plan created together for one audit job."""

    project: AuditProject
    task: AuditTask
    plan: AuditPlan


class TaskRunResult(AuditModel):
    """A persisted execution pass plus any approval work left for a human."""

    task: AuditTask
    plan: AuditPlan
    result: OrchestrationResult
    pending_approvals: list[ApprovalRequest] = Field(default_factory=list)


__all__ = ["TaskBundle", "TaskRunResult"]
