"""工具实现与 Runtime 之间的最小协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from agent.models.enums import FailureClass
from agent.models.result import ToolResult


@dataclass(frozen=True)
class ToolContext:
    """一次工具调用所需的执行上下文。

    工具只能使用显式传入的上下文，不读取模块级全局目录或宿主私有状态。
    """

    task_id: str
    execution_id: str
    procedure_id: str | None = None
    workspace_root: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolExecutionError(Exception):
    """工具主动返回的可分类执行异常。"""

    def __init__(
        self,
        message: str,
        *,
        failure_class: FailureClass = FailureClass.TERMINAL,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class


ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult | dict[str, Any]]]
