"""DAG-driven audit task orchestration with pause, retry, and replan support."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent.core.quality import DefaultProcedureQualityGate, ProcedureQualityGate, QualityContext
from agent.core.state_machine import TaskStateMachine
from agent.models.enums import FailureClass, StepStatus, TaskStatus
from agent.models.execution import (
    HumanSubmission,
    OrchestrationResult,
    QualityDecision,
    ToolCall,
)
from agent.models.plan import AuditPlan, PlanStep
from agent.models.result import ToolResult
from agent.models.task import AuditTask
from agent.security.permissions import PermissionPolicy
from agent.tools.executor import ToolExecutor


ToolCallProvider = Callable[[AuditTask, PlanStep], Sequence[ToolCall]]
Replanner = Callable[[AuditTask, AuditPlan, str], AuditPlan | None]


class OrchestrationError(RuntimeError):
    """The task, plan, or execution adapter is not safe to run."""


@dataclass(frozen=True)
class _StepOutcome:
    kind: str
    reason: str = ""


class AgentOrchestrator:
    """Advance one validated audit plan through the central ToolExecutor.

    The orchestrator deliberately does not know how audit-specific tool
    arguments are assembled. Callers inject a ``tool_call_provider`` so the
    same execution kernel can serve Python, DSH, or standalone EXE hosts.
    """

    def __init__(
        self,
        *,
        state_machine: TaskStateMachine,
        tool_executor: ToolExecutor,
        quality_gate: ProcedureQualityGate | None = None,
    ) -> None:
        self.state_machine = state_machine
        self.tool_executor = tool_executor
        self.quality_gate = quality_gate or DefaultProcedureQualityGate()

    async def execute(
        self,
        task: AuditTask,
        plan: AuditPlan,
        *,
        permission_policy: PermissionPolicy,
        tool_call_provider: ToolCallProvider,
        workspace_root: Path | None = None,
        human_submissions: Mapping[str, HumanSubmission] | None = None,
        replanner: Replanner | None = None,
        max_replans: int = 1,
    ) -> OrchestrationResult:
        """Execute or resume a task until completion or the next real waiting point."""

        if max_replans < 0:
            raise ValueError("max_replans 不能为负数")
        submissions = dict(human_submissions or {})
        self._validate_submissions(submissions)

        active_plan = plan
        self._validate_plan(task, active_plan)
        preparation = self._prepare_task(task, active_plan)
        if preparation is not None:
            return self._snapshot(task, active_plan, replans=0, message=preparation.reason)

        replans = 0
        while True:
            outcome = await self._run_schedule(
                task,
                active_plan,
                permission_policy=permission_policy,
                tool_call_provider=tool_call_provider,
                workspace_root=workspace_root,
                submissions=submissions,
            )

            can_replan = outcome.kind in {"failed", "escalate"}
            if not can_replan or replanner is None or replans >= max_replans:
                break

            try:
                replacement = replanner(task, active_plan, outcome.reason)
            except Exception as exc:  # pragma: no cover - defensive adapter boundary
                outcome = _StepOutcome("failed", f"重规划器异常：{exc}")
                break
            if replacement is None:
                break

            try:
                self._validate_plan(task, replacement)
            except OrchestrationError as exc:
                outcome = _StepOutcome("failed", f"重规划结果无效：{exc}")
                break
            if replacement.plan_id == active_plan.plan_id:
                outcome = _StepOutcome("failed", "重规划结果必须使用新的 plan_id")
                break

            active_plan = replacement
            task.plan_id = replacement.plan_id
            task.skill_id = replacement.skill_id
            task.skill_version = replacement.skill_version
            replans += 1

        self._apply_outcome(task, outcome)
        return self._snapshot(task, active_plan, replans=replans, message=outcome.reason)

    def _prepare_task(self, task: AuditTask, plan: AuditPlan) -> _StepOutcome | None:
        task.plan_id = plan.plan_id
        task.skill_id = plan.skill_id
        task.skill_version = plan.skill_version

        if task.status is TaskStatus.CREATED:
            self.state_machine.transition_task(task, TaskStatus.PLANNING, reason="开始校验并执行计划")

        if plan.missing_inputs:
            if task.status in {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN}:
                self.state_machine.transition_task(
                    task,
                    TaskStatus.WAITING_INPUT,
                    reason="缺少输入：" + "、".join(plan.missing_inputs),
                )
            return _StepOutcome("input", "缺少输入：" + "、".join(plan.missing_inputs))

        if task.status is TaskStatus.PLANNING:
            self.state_machine.transition_task(task, TaskStatus.READY, reason="计划校验通过")
        elif task.status is TaskStatus.WAITING_INPUT:
            self.state_machine.transition_task(task, TaskStatus.READY, reason="输入已补齐")
        elif task.status is TaskStatus.WAITING_HUMAN:
            self.state_machine.transition_task(task, TaskStatus.RUNNING, reason="人工材料已提交，继续执行")

        if task.status is TaskStatus.READY:
            self.state_machine.transition_task(task, TaskStatus.RUNNING, reason="开始执行计划")
        elif task.status is TaskStatus.RUNNING:
            pass
        else:
            raise OrchestrationError(f"任务 {task.task_id} 当前状态 {task.status.value} 不可执行")
        return None

    async def _run_schedule(
        self,
        task: AuditTask,
        plan: AuditPlan,
        *,
        permission_policy: PermissionPolicy,
        tool_call_provider: ToolCallProvider,
        workspace_root: Path | None,
        submissions: Mapping[str, HumanSubmission],
    ) -> _StepOutcome:
        if plan.missing_inputs:
            return _StepOutcome("input", "执行计划仍缺少输入：" + "、".join(plan.missing_inputs))

        scheduled = {step_id for layer in plan.execution_order for step_id in layer}
        remaining_human_only = sorted(
            step.step_id
            for step in plan.steps
            if step.step_id not in scheduled
            and step.status is not StepStatus.SKIPPED_NOT_APPLICABLE
        )
        layers = [list(layer) for layer in plan.execution_order]
        if remaining_human_only:
            layers.append(remaining_human_only)

        for layer in layers:
            paused: _StepOutcome | None = None
            for step_id in layer:
                step = plan.step(step_id)
                if step.status in {StepStatus.VERIFIED, StepStatus.SKIPPED_NOT_APPLICABLE}:
                    continue

                dependency_outcome = self._dependency_outcome(plan, step)
                if dependency_outcome is not None:
                    if dependency_outcome.kind in {"failed", "escalate"}:
                        return dependency_outcome
                    paused = paused or dependency_outcome
                    continue

                outcome = await self._process_step(
                    task,
                    plan,
                    step,
                    permission_policy=permission_policy,
                    tool_call_provider=tool_call_provider,
                    workspace_root=workspace_root,
                    submissions=submissions,
                )
                if outcome.kind in {"failed", "escalate"}:
                    return outcome
                if outcome.kind in {"human", "input"}:
                    paused = paused or outcome

            if paused is not None:
                return paused

        return self._completion_outcome(plan)

    async def _process_step(
        self,
        task: AuditTask,
        plan: AuditPlan,
        step: PlanStep,
        *,
        permission_policy: PermissionPolicy,
        tool_call_provider: ToolCallProvider,
        workspace_root: Path | None,
        submissions: Mapping[str, HumanSubmission],
    ) -> _StepOutcome:
        submission = submissions.get(step.step_id)

        if step.status is StepStatus.BLOCKED:
            return _StepOutcome("input", "缺少输入：" + "、".join(step.missing_inputs))
        if step.status is StepStatus.FAILED:
            return _StepOutcome("failed", step.notes or f"步骤 {step.step_id} 已失败")

        if step.status is StepStatus.WAITING_HUMAN:
            if submission is None:
                return _StepOutcome("human", f"步骤 {step.step_id} 等待人工材料")
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.HUMAN_COMPLETED,
                actor=submission.actor,
                reason=submission.comment or "人工材料已提交",
            )
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.VERIFYING,
                actor="system",
                reason="开始校验人工提交",
            )
            decision = await self._evaluate(plan, step, (), submission)
            return await self._apply_decision(
                task,
                plan,
                step,
                decision,
                permission_policy=permission_policy,
                tool_call_provider=tool_call_provider,
                workspace_root=workspace_root,
                submissions=submissions,
            )

        if step.status is StepStatus.PENDING:
            self.state_machine.transition_step(
                plan, step.step_id, StepStatus.READY, reason="依赖已满足"
            )

        if step.status is not StepStatus.READY:
            raise OrchestrationError(f"步骤 {step.step_id} 当前状态 {step.status.value} 不可推进")

        if step.human_required and not step.required_tools:
            self.state_machine.transition_step(
                plan, step.step_id, StepStatus.WAITING_HUMAN, reason="人工主导程序"
            )
            if submission is None:
                return _StepOutcome("human", f"步骤 {step.step_id} 等待人工材料")
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.HUMAN_COMPLETED,
                actor=submission.actor,
                reason=submission.comment or "人工材料已提交",
            )
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.VERIFYING,
                actor="system",
                reason="开始校验人工提交",
            )
            decision = await self._evaluate(plan, step, (), submission)
            return await self._apply_decision(
                task,
                plan,
                step,
                decision,
                permission_policy=permission_policy,
                tool_call_provider=tool_call_provider,
                workspace_root=workspace_root,
                submissions=submissions,
            )

        if step.required_tools:
            self.state_machine.transition_step(
                plan, step.step_id, StepStatus.RUNNING, reason="开始调用确定性工具"
            )
            tool_results = await self._run_tools(
                task,
                step,
                permission_policy=permission_policy,
                tool_call_provider=tool_call_provider,
                workspace_root=workspace_root,
            )
            self.state_machine.transition_step(
                plan, step.step_id, StepStatus.VERIFYING, reason="工具执行完成，进入质量门"
            )
        else:
            self.state_machine.transition_step(
                plan, step.step_id, StepStatus.VERIFYING, reason="无工具程序，进入质量门"
            )
            tool_results = ()

        decision = await self._evaluate(plan, step, tool_results, submission)
        return await self._apply_decision(
            task,
            plan,
            step,
            decision,
            permission_policy=permission_policy,
            tool_call_provider=tool_call_provider,
            workspace_root=workspace_root,
            submissions=submissions,
        )

    async def _run_tools(
        self,
        task: AuditTask,
        step: PlanStep,
        *,
        permission_policy: PermissionPolicy,
        tool_call_provider: ToolCallProvider,
        workspace_root: Path | None,
    ) -> tuple[ToolResult, ...]:
        try:
            calls = list(tool_call_provider(task, step))
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            return (
                ToolResult.fail(
                    "procedure_precondition",
                    f"工具调用参数构造失败：{exc}",
                    failure_class=FailureClass.TERMINAL,
                ),
            )

        declared = set(step.required_tools)
        requested = {call.tool_name for call in calls}
        missing = sorted(declared - requested)
        extra = sorted(requested - declared)
        if missing or extra:
            details: list[str] = []
            if missing:
                details.append("缺少工具调用：" + "、".join(missing))
            if extra:
                details.append("调用了未声明工具：" + "、".join(extra))
            return (
                ToolResult.fail(
                    "procedure_precondition",
                    "；".join(details),
                    failure_class=FailureClass.TERMINAL,
                ),
            )

        results: list[ToolResult] = []
        for call in calls:
            result = await self.tool_executor.execute(
                call.tool_name,
                call.arguments,
                policy=permission_policy,
                task_id=task.task_id,
                procedure_id=step.procedure_id,
                workspace_root=workspace_root,
                approval_granted=call.approval_granted,
            )
            results.append(result)
            if not result.success:
                break
        return tuple(results)

    async def _evaluate(
        self,
        plan: AuditPlan,
        step: PlanStep,
        tool_results: Sequence[ToolResult],
        submission: HumanSubmission | None,
    ) -> QualityDecision:
        return await self.quality_gate.evaluate(
            QualityContext(
                task_id=plan.task_id,
                skill_id=plan.skill_id,
                step=step,
                tool_results=tuple(tool_results),
                human_submission=submission,
            )
        )

    async def _apply_decision(
        self,
        task: AuditTask,
        plan: AuditPlan,
        step: PlanStep,
        decision: QualityDecision,
        *,
        permission_policy: PermissionPolicy,
        tool_call_provider: ToolCallProvider,
        workspace_root: Path | None,
        submissions: Mapping[str, HumanSubmission],
    ) -> _StepOutcome:
        if decision.passed:
            needs_human = step.human_required
            if needs_human and step.step_id not in submissions:
                self.state_machine.transition_step(
                    plan,
                    step.step_id,
                    StepStatus.WAITING_HUMAN,
                    reason="质量门通过，但程序仍需人工确认",
                )
                return _StepOutcome("human", f"步骤 {step.step_id} 等待人工确认")
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.VERIFIED,
                reason=decision.reason or "质量门通过",
            )
            return _StepOutcome("verified", decision.reason)

        if decision.requires_human:
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.WAITING_HUMAN,
                reason=decision.reason or "质量门要求人工处理",
            )
            return _StepOutcome("human", decision.reason)

        if decision.retryable:
            if step.retryable:
                step.retry_count += 1
                self.state_machine.transition_step(
                    plan,
                    step.step_id,
                    StepStatus.READY,
                    reason=f"第 {step.retry_count} 次重试：{decision.reason}",
                )
                return await self._process_step(
                    task,
                    plan,
                    step,
                    permission_policy=permission_policy,
                    tool_call_provider=tool_call_provider,
                    workspace_root=workspace_root,
                    submissions=submissions,
                )
            self.state_machine.transition_step(
                plan,
                step.step_id,
                StepStatus.WAITING_HUMAN,
                reason=f"重试次数耗尽，转人工接管：{decision.reason}",
            )
            return _StepOutcome("escalate", f"步骤 {step.step_id} 重试次数耗尽：{decision.reason}")

        self.state_machine.transition_step(
            plan,
            step.step_id,
            StepStatus.FAILED,
            reason=decision.reason or "质量门终止失败",
        )
        return _StepOutcome("failed", f"步骤 {step.step_id} 终止失败：{decision.reason}")

    def _dependency_outcome(self, plan: AuditPlan, step: PlanStep) -> _StepOutcome | None:
        for dependency_id in step.dependencies:
            dependency = plan.step(dependency_id)
            if dependency.status in {StepStatus.VERIFIED, StepStatus.SKIPPED_NOT_APPLICABLE}:
                continue
            if dependency.status is StepStatus.FAILED:
                return _StepOutcome("failed", f"步骤 {step.step_id} 的依赖 {dependency_id} 已失败")
            if dependency.status is StepStatus.BLOCKED:
                return _StepOutcome("input", f"步骤 {step.step_id} 等待依赖 {dependency_id} 的输入")
            return _StepOutcome("human", f"步骤 {step.step_id} 等待依赖 {dependency_id} 完成")
        return None

    def _completion_outcome(self, plan: AuditPlan) -> _StepOutcome:
        active = [step for step in plan.steps if step.status is not StepStatus.SKIPPED_NOT_APPLICABLE]
        failed = [step.step_id for step in active if step.status is StepStatus.FAILED]
        if failed:
            return _StepOutcome("failed", "步骤失败：" + "、".join(failed))

        waiting_human = [
            step.step_id
            for step in active
            if step.status in {StepStatus.WAITING_HUMAN, StepStatus.HUMAN_COMPLETED}
        ]
        if waiting_human:
            return _StepOutcome("human", "等待人工完成：" + "、".join(waiting_human))

        waiting_input = [step.step_id for step in active if step.status is StepStatus.BLOCKED]
        if waiting_input:
            return _StepOutcome("input", "等待输入：" + "、".join(waiting_input))

        unfinished = [
            step.step_id
            for step in active
            if step.status not in {StepStatus.VERIFIED, StepStatus.SKIPPED_NOT_APPLICABLE}
        ]
        if unfinished:
            raise OrchestrationError("计划执行结束但仍有未完成步骤：" + "、".join(unfinished))
        return _StepOutcome("completed", "全部活动程序已通过质量门")

    def _apply_outcome(self, task: AuditTask, outcome: _StepOutcome) -> None:
        if outcome.kind == "completed":
            if task.status is TaskStatus.RUNNING:
                self.state_machine.transition_task(task, TaskStatus.VERIFYING, reason="最终质量检查")
            if task.status is TaskStatus.VERIFYING:
                self.state_machine.transition_task(task, TaskStatus.COMPLETED, reason=outcome.reason)
            return

        if outcome.kind == "human":
            if task.status in {TaskStatus.RUNNING, TaskStatus.VERIFYING}:
                self.state_machine.transition_task(task, TaskStatus.WAITING_HUMAN, reason=outcome.reason)
            return

        if outcome.kind == "input":
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN}:
                self.state_machine.transition_task(task, TaskStatus.WAITING_INPUT, reason=outcome.reason)
            return

        if outcome.kind in {"failed", "escalate"}:
            if outcome.kind == "escalate" and task.status in {TaskStatus.RUNNING, TaskStatus.VERIFYING}:
                self.state_machine.transition_task(task, TaskStatus.WAITING_HUMAN, reason=outcome.reason)
                return
            if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN, TaskStatus.VERIFYING}:
                self.state_machine.transition_task(task, TaskStatus.FAILED, reason=outcome.reason)
            return

        raise OrchestrationError(f"未知编排结果：{outcome.kind}")

    def _snapshot(
        self,
        task: AuditTask,
        plan: AuditPlan,
        *,
        replans: int,
        message: str,
    ) -> OrchestrationResult:
        return OrchestrationResult(
            task_id=task.task_id,
            plan_id=plan.plan_id,
            status=task.status,
            verified_steps=sorted(
                step.step_id for step in plan.steps if step.status is StepStatus.VERIFIED
            ),
            waiting_human_steps=sorted(
                step.step_id
                for step in plan.steps
                if step.status in {StepStatus.WAITING_HUMAN, StepStatus.HUMAN_COMPLETED}
            ),
            waiting_input_steps=sorted(
                step.step_id for step in plan.steps if step.status is StepStatus.BLOCKED
            ),
            failed_steps=sorted(
                step.step_id for step in plan.steps if step.status is StepStatus.FAILED
            ),
            skipped_steps=sorted(
                step.step_id
                for step in plan.steps
                if step.status is StepStatus.SKIPPED_NOT_APPLICABLE
            ),
            replans=replans,
            message=message,
        )

    @staticmethod
    def _validate_plan(task: AuditTask, plan: AuditPlan) -> None:
        if not plan.validated:
            raise OrchestrationError("未通过三源校验的计划不能执行")
        if plan.task_id != task.task_id:
            raise OrchestrationError(f"计划 task_id={plan.task_id!r} 与任务 {task.task_id!r} 不一致")
        step_ids = {step.step_id for step in plan.steps}
        flattened = [step_id for layer in plan.execution_order for step_id in layer]
        unknown = sorted(set(flattened) - step_ids)
        duplicates = sorted({step_id for step_id in flattened if flattened.count(step_id) > 1})
        if unknown:
            raise OrchestrationError("执行顺序包含不存在的步骤：" + "、".join(unknown))
        if duplicates:
            raise OrchestrationError("执行顺序包含重复步骤：" + "、".join(duplicates))
        for step in plan.steps:
            missing = sorted(set(step.dependencies) - step_ids)
            if missing:
                raise OrchestrationError(
                    f"步骤 {step.step_id} 依赖不存在的步骤：" + "、".join(missing)
                )

    @staticmethod
    def _validate_submissions(submissions: Mapping[str, HumanSubmission]) -> None:
        for key, submission in submissions.items():
            if key != submission.step_id:
                raise OrchestrationError(
                    f"人工提交键 {key!r} 与 step_id={submission.step_id!r} 不一致"
                )


__all__ = [
    "AgentOrchestrator",
    "OrchestrationError",
    "Replanner",
    "ToolCallProvider",
]