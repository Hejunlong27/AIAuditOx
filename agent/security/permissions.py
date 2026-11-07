"""工具白名单与权限分级（PART 20 第 7、8、10、11 条）。

原则：**默认拒绝**。工具必须先注册进白名单才能被调用；
白名单之外的任何名字一律拒绝，而不是"找不到就跳过"。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.models.enums import ToolRiskLevel
from agent.security.workspace import SecurityError


class PermissionDenied(SecurityError):
    """权限不足。调用方必须把它当作终止性错误，不得重试。"""


@dataclass
class PermissionPolicy:
    """一次任务执行期间的权限上下文。

    ``allow_network`` 与 ``allow_shell`` 默认关闭，且第一版不提供开启入口
    （PART 20 第 9、10 条）。保留字段是为了让审计日志能记录"当时是什么策略"，
    而不是为了以后偷偷打开。
    """

    allowed_tools: set[str] = field(default_factory=set)
    allow_network: bool = False
    allow_shell: bool = False
    max_tool_calls: int = 500
    max_steps: int = 20
    call_count: int = 0

    def check_tool(self, tool_name: str, risk: ToolRiskLevel) -> None:
        """调用前检查。不通过抛 :class:`PermissionDenied`。"""
        if self.call_count >= self.max_tool_calls:
            raise PermissionDenied(
                f"工具调用次数已达上限 {self.max_tool_calls}，任务必须停下交由人工处理"
            )
        if tool_name not in self.allowed_tools:
            raise PermissionDenied(
                f"工具 {tool_name!r} 不在白名单内。已允许：{sorted(self.allowed_tools)}"
            )
        if risk is ToolRiskLevel.EXTERNAL_IO and not self.allow_network:
            raise PermissionDenied(f"工具 {tool_name!r} 需要外部网络，当前策略禁止")
        if risk is ToolRiskLevel.DESTRUCTIVE:
            raise PermissionDenied(
                f"工具 {tool_name!r} 属破坏性操作，第一版直接禁止（含物理删除）"
            )

    def record_call(self) -> None:
        self.call_count += 1


class ShellGuard:
    """Shell 执行的最终闸门：第一版恒拒绝。

    PART 20 第 10 条明确「Shell 执行默认禁止」。这里不做命令白名单
    解析——命令白名单的历史漏洞太多，直接不开门是唯一可靠做法。
    """

    @staticmethod
    def check_enabled(policy: PermissionPolicy) -> None:
        if not policy.allow_shell:
            raise PermissionDenied("Shell 执行已被禁用；如需外部处理请走受控工具")

    @staticmethod
    def run_or_refuse(*args: object, **kwargs: object) -> None:
        raise PermissionDenied("Shell 执行已被禁用")
