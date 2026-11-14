"""Strict task and procedure-step state transitions with audit events."""

from __future__ import annotations

from collections.abc import Callable

from agent.models.base import utcnow
from agent.models.enums import StepStatus, TaskStatus
from agent.models.execution import StateChange
from agent.models.plan import AuditPlan
from agent.models.task import AuditTask


class IllegalStateTransition(RuntimeError):
    """Raised when a caller attempts a transition outside the audit lifecycle."""


TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.PLANNING: frozenset(
        {TaskStatus.WAITING_INPUT, TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_INPUT: frozenset(
        {TaskStatus.PLANNING, TaskStatus.READY, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.READY: frozenset(
        {TaskStatus.RUNNING, TaskStatus.WAITING_INPUT, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING_INPUT,
            TaskStatus.WAITING_HUMAN,
            TaskStatus.VERIFYING,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_HUMAN: frozenset(
        {TaskStatus.RUNNING, TaskStatus.WAITING_INPUT, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.VERIFYING: frozenset(
        {TaskStatus.COMPLETED, TaskStatus.WAITING_HUMAN, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


STEP_TRANSITIONS: dict[StepStatus, frozenset[StepStatus]] = {
    StepStatus.PENDING: frozenset(
        {
            StepStatus.READY,
            StepStatus.BLOCKED,
            StepStatus.WAITING_HUMAN,
            StepStatus.SKIPPED_NOT_APPLICABLE,
            StepStatus.FAILED,
        }
    ),
    StepStatus.BLOCKED: frozenset(
        {StepStatus.READY, StepStatus.PENDING, StepStatus.SKIPPED_NOT_APPLICABLE, StepStatus.FAILED}
    ),
    StepStatus.READY: frozenset(
        {
            StepStatus.RUNNING,
            StepStatus.VERIFYING,
            StepStatus.WAITING_HUMAN,
            StepStatus.SKIPPED_NOT_APPLICABLE,
            StepStatus.FAILED,
        }
    ),
    StepStatus.RUNNING: frozenset(
        {StepStatus.VERIFYING, StepStatus.WAITING_HUMAN, StepStatus.FAILED}
    ),
    StepStatus.WAITING_HUMAN: frozenset({StepStatus.HUMAN_COMPLETED, StepStatus.FAILED}),
    StepStatus.HUMAN_COMPLETED: frozenset({StepStatus.VERIFYING, StepStatus.FAILED}),
    StepStatus.VERIFYING: frozenset(
        {StepStatus.VERIFIED, StepStatus.READY, StepStatus.WAITING_HUMAN, StepStatus.FAILED}
    ),
    StepStatus.VERIFIED: frozenset(),
    StepStatus.SKIPPED_NOT_APPLICABLE: frozenset(),
    StepStatus.FAILED: frozenset({StepStatus.READY}),
}


class TaskStateMachine:
    """Apply only legal transitions and emit one event per actual change."""

    def __init__(self, event_sink: Callable[[StateChange], None] | None = None) -> None:
        self.event_sink = event_sink

    def transition_task(
        self,
        task: AuditTask,
        target: TaskStatus,
        *,
        actor: str = "system",
        reason: str = "",
    ) -> TaskStatus:
        source = task.status
        if source is target:
            return source
        allowed = TASK_TRANSITIONS[source]
        if target not in allowed:
            raise IllegalStateTransition(f"任务 {task.task_id} 不允许 {source.value} → {target.value}")
        task.status = target
        task.updated_at = utcnow()
        if target is TaskStatus.FAILED:
            task.metadata = {**task.metadata, "failure_reason": reason}
        self._emit(
            StateChange(
                task_id=task.task_id,
                object_type="task",
                object_id=task.task_id,
                from_status=source.value,
                to_status=target.value,
                actor=actor,
                reason=reason,
            )
        )
        return target

    def transition_step(
        self,
        plan: AuditPlan,
        step_id: str,
        target: StepStatus,
        *,
        actor: str = "system",
        reason: str = "",
    ) -> StepStatus:
        step = plan.step(step_id)
        source = step.status
        if source is target:
            return source
        allowed = STEP_TRANSITIONS[source]
        if target not in allowed:
            raise IllegalStateTransition(
                f"步骤 {step_id} 不允许 {source.value} → {target.value}"
            )
        step.status = target
        if reason:
            step.notes = reason
        self._emit(
            StateChange(
                task_id=plan.task_id,
                object_type="step",
                object_id=step_id,
                from_status=source.value,
                to_status=target.value,
                actor=actor,
                reason=reason,
            )
        )
        return target

    def _emit(self, change: StateChange) -> None:
        if self.event_sink is not None:
            self.event_sink(change)


__all__ = [
    "IllegalStateTransition",
    "STEP_TRANSITIONS",
    "TASK_TRANSITIONS",
    "TaskStateMachine",
]