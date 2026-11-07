"""运行时统一数据模型（PART 5）。

所有核心业务数据一律使用本包的类型，禁止在业务代码里传无结构 dict。
"""

from __future__ import annotations

from agent.models.approval import ApprovalRequest
from agent.models.base import AuditModel, Money, Percent, to_money, utcnow
from agent.models.enums import (
    ApprovalStatus,
    ConflictSeverity,
    EvidenceKind,
    EvidenceStatus,
    ExecutionMode,
    FailureClass,
    StepStatus,
    TaskStatus,
    ToolRiskLevel,
)
from agent.models.evidence import Evidence, ResultRef, SourceRef
from agent.models.plan import AuditPlan, PlanStep
from agent.models.procedure import ConflictRecord, ExecutionPolicy, ProcedureDefinition
from agent.models.result import ToolResult
from agent.models.task import AuditTask
from agent.models.tool import ToolInvocation, ToolSpec

__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "AuditModel",
    "AuditPlan",
    "AuditTask",
    "ConflictRecord",
    "ConflictSeverity",
    "Evidence",
    "EvidenceKind",
    "EvidenceStatus",
    "ExecutionMode",
    "ExecutionPolicy",
    "FailureClass",
    "Money",
    "Percent",
    "PlanStep",
    "ProcedureDefinition",
    "ResultRef",
    "SourceRef",
    "StepStatus",
    "TaskStatus",
    "ToolInvocation",
    "ToolResult",
    "ToolRiskLevel",
    "ToolSpec",
    "to_money",
    "utcnow",
]
