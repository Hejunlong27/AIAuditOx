"""工具元数据模型（PART 9.1）。

工具行为由 ``BaseTool`` 定义，本模型只承载**注册表需要的元信息**，
便于 CLI / API / MCP 在不导入工具实现的情况下列举能力。
"""

from __future__ import annotations

from pydantic import Field

from agent.models.base import AuditModel
from agent.models.enums import FailureClass, ToolRequirementLevel, ToolRiskLevel


class ToolSpec(AuditModel):
    """工具的对外契约描述。"""

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY
    input_schema: dict = Field(default_factory=dict, description="JSON Schema")
    output_schema: dict = Field(default_factory=dict, description="JSON Schema")
    timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    max_retries: int = Field(default=0, ge=0, le=5)
    requires_approval: bool = False
    version: str = Field(default="1.0.0", min_length=1)
    deterministic: bool = True
    idempotent: bool = True
    backend: str = Field(default="runtime", description="central / node / python / skill_local")
    supported_hosts: list[str] = Field(
        default_factory=lambda: ["python", "dsh", "exe"],
        description="已实现并验证支持的宿主",
    )
    declared_by_skills: list[str] = Field(
        default_factory=list,
        description="哪些技能包在 dsl.json 里声明了这个工具",
    )


class ToolRequirement(AuditModel):
    """技能对一项工具能力的需求声明。

    ``fallback`` 描述缺失时可接受的替代方式，例如 ``skill_local`` 或 ``manual``。
    required 缺失时禁止继续；preferred 只有提供 fallback 才允许降级；
    optional 缺失只记录警告。
    """

    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    level: ToolRequirementLevel = ToolRequirementLevel.REQUIRED
    fallback: str | None = None
    note: str = ""


class ToolInvocation(AuditModel):
    """一次工具调用的审计记录（落 tool_runs 表）。"""

    execution_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    procedure_id: str | None = None
    tool_name: str = Field(min_length=1)
    arguments: dict = Field(default_factory=dict)
    success: bool = False
    error: str | None = None
    failure_class: FailureClass | None = None
    attempts: int = Field(default=1, ge=1)
    duration_ms: int = Field(default=0, ge=0)
    created_at_ts: str = ""
