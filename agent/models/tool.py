"""工具元数据模型（PART 9.1）。

工具行为由 ``BaseTool`` 定义，本模型只承载**注册表需要的元信息**，
便于 CLI / API / MCP 在不导入工具实现的情况下列举能力。
"""

from __future__ import annotations

from pydantic import Field

from agent.models.base import AuditModel
from agent.models.enums import ToolRiskLevel


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
    declared_by_skills: list[str] = Field(
        default_factory=list,
        description="哪些技能包在 dsl.json 里声明了这个工具",
    )


class ToolInvocation(AuditModel):
    """一次工具调用的审计记录（落 tool_runs 表）。"""

    execution_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    procedure_id: str | None = None
    tool_name: str = Field(min_length=1)
    arguments: dict = Field(default_factory=dict)
    success: bool = False
    error: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    created_at_ts: str = ""
