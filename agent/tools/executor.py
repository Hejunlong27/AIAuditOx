"""统一工具执行器：校验、权限、超时、重试、结果和审计。"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any

from agent.models.base import utcnow
from agent.models.enums import FailureClass
from agent.models.result import ToolResult
from agent.models.tool import ToolInvocation
from agent.security.permissions import PermissionDenied, PermissionPolicy
from agent.tools.base import ToolContext, ToolExecutionError
from agent.tools.registry import ToolRegistry
from agent.tools.schema import SchemaValidationError, validate_json_schema


AuditSink = Callable[[ToolInvocation], None]


class ToolExecutor:
    """所有工具调用的唯一运行时入口。"""

    def __init__(self, registry: ToolRegistry, *, audit_sink: AuditSink | None = None) -> None:
        self.registry = registry
        self.audit_sink = audit_sink

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        policy: PermissionPolicy,
        task_id: str,
        procedure_id: str | None = None,
        execution_id: str = "",
        workspace_root=None,
        host: str = "python",
        approval_granted: bool = False,
    ) -> ToolResult:
        execution_id = execution_id or uuid.uuid4().hex
        started = time.perf_counter()
        attempts = 0

        try:
            registration = self.registry.get(tool_name)
        except KeyError as exc:
            return self._finish_failure(
                tool_name=tool_name,
                task_id=task_id,
                procedure_id=procedure_id,
                execution_id=execution_id,
                arguments=arguments,
                error=str(exc),
                failure_class=FailureClass.TERMINAL,
                attempts=1,
                started=started,
            )

        spec = registration.spec
        if host not in spec.supported_hosts:
            return self._finish_failure(
                tool_name=tool_name,
                task_id=task_id,
                procedure_id=procedure_id,
                execution_id=execution_id,
                arguments=arguments,
                error=f"工具 {tool_name} 未声明支持宿主 {host}",
                failure_class=FailureClass.NEED_HUMAN,
                attempts=1,
                started=started,
            )
        if spec.requires_approval and not approval_granted:
            return self._finish_failure(
                tool_name=tool_name,
                task_id=task_id,
                procedure_id=procedure_id,
                execution_id=execution_id,
                arguments=arguments,
                error=f"工具 {tool_name} 需要人工审批",
                failure_class=FailureClass.NEED_HUMAN,
                attempts=1,
                started=started,
            )

        context = ToolContext(
            task_id=task_id,
            execution_id=execution_id,
            procedure_id=procedure_id,
            workspace_root=workspace_root,
        )
        last_failure: ToolResult | None = None

        for attempt in range(spec.max_retries + 1):
            attempts = attempt + 1
            try:
                policy.check_tool(tool_name, spec.risk_level)
                policy.record_call()
            except PermissionDenied as exc:
                return self._finish_failure(
                    tool_name=tool_name,
                    task_id=task_id,
                    procedure_id=procedure_id,
                    execution_id=execution_id,
                    arguments=arguments,
                    error=str(exc),
                    failure_class=FailureClass.NEED_HUMAN,
                    attempts=attempts,
                    started=started,
                )

            try:
                validate_json_schema(arguments, spec.input_schema)
            except SchemaValidationError as exc:
                return self._finish_failure(
                    tool_name=tool_name,
                    task_id=task_id,
                    procedure_id=procedure_id,
                    execution_id=execution_id,
                    arguments=arguments,
                    error=str(exc),
                    failure_class=FailureClass.TERMINAL,
                    attempts=attempts,
                    started=started,
                )

            try:
                raw = await asyncio.wait_for(
                    registration.handler(arguments, context),
                    timeout=spec.timeout_seconds,
                )
                if isinstance(raw, ToolResult):
                    result = raw.model_copy(
                        update={
                            "tool_name": tool_name,
                            "execution_id": execution_id,
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                        }
                    )
                elif isinstance(raw, dict):
                    result = ToolResult.ok(
                        tool_name,
                        raw,
                        execution_id=execution_id,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                else:
                    raise ToolExecutionError(
                        f"工具返回值类型非法：{type(raw).__name__}",
                        failure_class=FailureClass.TERMINAL,
                    )

                if result.success and spec.output_schema:
                    validate_json_schema(result.result, spec.output_schema, path="$.result")
                if result.success:
                    self._emit(
                        tool_name=tool_name,
                        task_id=task_id,
                        procedure_id=procedure_id,
                        execution_id=execution_id,
                        arguments=arguments,
                        success=True,
                        attempts=attempts,
                        duration_ms=result.duration_ms,
                    )
                    return result
                last_failure = result
                if result.failure_class is not FailureClass.RETRYABLE:
                    break
            except asyncio.TimeoutError:
                last_failure = ToolResult.fail(
                    tool_name,
                    f"工具执行超时（{spec.timeout_seconds:g}s）",
                    failure_class=FailureClass.RETRYABLE,
                    execution_id=execution_id,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            except ToolExecutionError as exc:
                last_failure = ToolResult.fail(
                    tool_name,
                    str(exc),
                    failure_class=exc.failure_class,
                    execution_id=execution_id,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                if exc.failure_class is not FailureClass.RETRYABLE:
                    break
            except SchemaValidationError as exc:
                last_failure = ToolResult.fail(
                    tool_name,
                    f"工具输出不符合 schema：{exc}",
                    failure_class=FailureClass.TERMINAL,
                    execution_id=execution_id,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                break
            except Exception as exc:  # pragma: no cover - 兜底路径由失败用例覆盖
                last_failure = ToolResult.fail(
                    tool_name,
                    f"工具执行异常：{exc}",
                    failure_class=FailureClass.TERMINAL,
                    execution_id=execution_id,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
                break

        result = last_failure or ToolResult.fail(
            tool_name,
            "工具执行失败但未产生失败详情",
            failure_class=FailureClass.TERMINAL,
            execution_id=execution_id,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        self._emit(
            tool_name=tool_name,
            task_id=task_id,
            procedure_id=procedure_id,
            execution_id=execution_id,
            arguments=arguments,
            success=False,
            attempts=attempts,
            duration_ms=result.duration_ms,
            error=result.error,
            failure_class=result.failure_class,
        )
        return result

    def _finish_failure(
        self,
        *,
        tool_name: str,
        task_id: str,
        procedure_id: str | None,
        execution_id: str,
        arguments: dict[str, Any],
        error: str,
        failure_class: FailureClass,
        attempts: int,
        started: float,
    ) -> ToolResult:
        duration_ms = int((time.perf_counter() - started) * 1000)
        self._emit(
            tool_name=tool_name,
            task_id=task_id,
            procedure_id=procedure_id,
            execution_id=execution_id,
            arguments=arguments,
            success=False,
            attempts=attempts,
            duration_ms=duration_ms,
            error=error,
            failure_class=failure_class,
        )
        return ToolResult.fail(
            tool_name,
            error,
            failure_class=failure_class,
            execution_id=execution_id,
            duration_ms=duration_ms,
        )

    def _emit(
        self,
        *,
        tool_name: str,
        task_id: str,
        procedure_id: str | None,
        execution_id: str,
        arguments: dict[str, Any],
        success: bool,
        attempts: int,
        duration_ms: int,
        error: str | None = None,
        failure_class: FailureClass | None = None,
    ) -> None:
        if self.audit_sink is None:
            return
        self.audit_sink(
            ToolInvocation(
                execution_id=execution_id,
                task_id=task_id,
                procedure_id=procedure_id,
                tool_name=tool_name,
                arguments=arguments,
                success=success,
                error=error,
                failure_class=failure_class,
                attempts=attempts,
                duration_ms=duration_ms,
                created_at_ts=utcnow().isoformat(),
            )
        )
