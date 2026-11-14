"""Unit tests for strict audit task and procedure state transitions."""

from __future__ import annotations

import pytest

from agent.core.state_machine import IllegalStateTransition, TaskStateMachine
from agent.models import AuditPlan, AuditTask, PlanStep, StateChange, StepStatus, TaskStatus

pytestmark = pytest.mark.unit


def make_task(status: TaskStatus = TaskStatus.CREATED) -> AuditTask:
    return AuditTask(
        task_id="TASK-SM",
        project_id="PRJ-SM",
        user_request="执行银行存款审计程序",
        workspace="C:/tmp/workspace",
        status=status,
    )


def make_plan(status: StepStatus = StepStatus.PENDING) -> AuditPlan:
    return AuditPlan(
        plan_id="PLAN-SM",
        task_id="TASK-SM",
        skill_id="z-1-2-bank-deposits",
        steps=[
            PlanStep(
                step_id="P02",
                procedure_id="P02",
                name="银行账户完整性检查",
                human_required=True,
                status=status,
            )
        ],
        execution_order=[["P02"]],
        validated=True,
    )


def test_task_transitions_follow_audit_lifecycle() -> None:
    task = make_task()
    sm = TaskStateMachine()

    sm.transition_task(task, TaskStatus.PLANNING)
    sm.transition_task(task, TaskStatus.READY)
    sm.transition_task(task, TaskStatus.RUNNING)
    sm.transition_task(task, TaskStatus.VERIFYING)
    sm.transition_task(task, TaskStatus.COMPLETED)

    assert task.status is TaskStatus.COMPLETED


def test_illegal_task_transition_is_rejected() -> None:
    task = make_task()
    sm = TaskStateMachine()

    with pytest.raises(IllegalStateTransition, match="CREATED → COMPLETED"):
        sm.transition_task(task, TaskStatus.COMPLETED)

    assert task.status is TaskStatus.CREATED


def test_human_step_requires_submission_and_verification() -> None:
    plan = make_plan(StepStatus.WAITING_HUMAN)
    sm = TaskStateMachine()

    sm.transition_step(plan, "P02", StepStatus.HUMAN_COMPLETED)
    sm.transition_step(plan, "P02", StepStatus.VERIFYING)
    sm.transition_step(plan, "P02", StepStatus.VERIFIED)

    assert plan.step("P02").status is StepStatus.VERIFIED


def test_human_completed_cannot_be_skipped() -> None:
    plan = make_plan(StepStatus.WAITING_HUMAN)
    sm = TaskStateMachine()
    sm.transition_step(plan, "P02", StepStatus.HUMAN_COMPLETED)

    with pytest.raises(IllegalStateTransition, match="HUMAN_COMPLETED → VERIFIED"):
        sm.transition_step(plan, "P02", StepStatus.VERIFIED)


def test_actual_changes_emit_state_events() -> None:
    events: list[StateChange] = []
    task = make_task()
    plan = make_plan(StepStatus.PENDING)
    sm = TaskStateMachine(event_sink=events.append)

    sm.transition_task(task, TaskStatus.PLANNING)
    sm.transition_task(task, TaskStatus.PLANNING)
    sm.transition_step(plan, "P02", StepStatus.READY)

    assert [(event.object_type, event.to_status) for event in events] == [
        ("task", "PLANNING"),
        ("step", "READY"),
    ]