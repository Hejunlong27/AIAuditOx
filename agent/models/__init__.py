"""运行时统一数据模型（PART 5）。

所有核心业务数据一律使用本包的类型，禁止在业务代码里传无结构 dict。
"""

from __future__ import annotations

from agent.models.approval import ApprovalRequest
from agent.models.artifact import ArtifactRecord
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
    ToolRequirementLevel,
    ToolRiskLevel,
)
from agent.models.evidence import Evidence, ResultRef, SourceRef
from agent.models.execution import (
    HumanSubmission,
    OrchestrationResult,
    QualityDecision,
    StateChange,
    ToolCall,
)
from agent.models.plan import AuditPlan, PlanStep
from agent.models.procedure import ConflictRecord, ExecutionPolicy, ProcedureDefinition
from agent.models.project import AuditProject
from agent.models.result import ToolResult
from agent.models.task import AuditTask
from agent.models.tool import ToolInvocation, ToolRequirement, ToolSpec

__all__ = [
    "ApprovalRequest",
    "ArtifactRecord",
    "ApprovalStatus",
    "AuditModel",
    "AuditPlan",
    "AuditProject",
    "AuditTask",
    "ConflictRecord",
    "ConflictSeverity",
    "Evidence",
    "EvidenceKind",
    "EvidenceStatus",
    "ExecutionMode",
    "ExecutionPolicy",
    "HumanSubmission",
    "FailureClass",
    "Money",
    "OrchestrationResult",
    "Percent",
    "PlanStep",
    "ProcedureDefinition",
    "QualityDecision",
    "ResultRef",
    "SourceRef",
    "StateChange",
    "StepStatus",
    "TaskStatus",
    "ToolCall",
    "ToolInvocation",
    "ToolResult",
    "ToolRequirement",
    "ToolRequirementLevel",
    "ToolRiskLevel",
    "ToolSpec",
    "to_money",
    "utcnow",
]
