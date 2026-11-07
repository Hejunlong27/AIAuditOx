"""工具调用结果模型（PART 5.6）。"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from agent.models.base import AuditModel
from agent.models.enums import FailureClass


class ToolResult(AuditModel):
    """一次工具执行的返回值。

    ``result`` 用 ``dict`` 承载工具特有结构，但**外层必须是本模型**，
    禁止让业务代码直接传裸 dict —— 否则 evidence_files / warnings
    这些可追溯信息会在传递中丢失。
    """

    success: bool
    tool_name: str = Field(min_length=1)
    result: dict[str, Any] = Field(default_factory=dict)
    evidence_files: list[str] = Field(default_factory=list, description="产出文件绝对路径")
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    execution_id: str = Field(default="", description="工具执行 ID，用于关联 tool_runs 表")
    failure_class: FailureClass | None = None
    error: str | None = None
    duration_ms: int = Field(default=0, ge=0)

    @classmethod
    def ok(
        cls,
        tool_name: str,
        result: dict[str, Any] | None = None,
        *,
        execution_id: str = "",
        evidence_files: list[str] | None = None,
        warnings: list[str] | None = None,
        requires_human_review: bool = False,
        duration_ms: int = 0,
    ) -> "ToolResult":
        return cls(
            success=True,
            tool_name=tool_name,
            result=result or {},
            evidence_files=evidence_files or [],
            warnings=warnings or [],
            requires_human_review=requires_human_review,
            execution_id=execution_id,
            duration_ms=duration_ms,
        )

    @classmethod
    def fail(
        cls,
        tool_name: str,
        error: str,
        *,
        failure_class: FailureClass = FailureClass.TERMINAL,
        execution_id: str = "",
        duration_ms: int = 0,
    ) -> "ToolResult":
        return cls(
            success=False,
            tool_name=tool_name,
            error=error,
            failure_class=failure_class,
            execution_id=execution_id,
            duration_ms=duration_ms,
        )
