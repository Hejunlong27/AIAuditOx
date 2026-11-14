"""Unit tests for task orchestration, pause/resume, retry, and replanning."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.core import AgentOrchestrator, TaskStateMachine
from agent.models import (
    AuditPlan,
    AuditTask,
    FailureClass,
    HumanSubmission,
    PlanStep,
    StepStatus,
    TaskStatus,
    ToolCall,
    ToolResult,
    ToolRiskLevel,
    ToolSpec,
)
from agent.security.permissions import PermissionPolicy
from agent.tools.base import ToolExecutionError
from agent.tools.executor import ToolExecutor
from agent.tools.registry import ToolRegistry

pytestmark = pytest.mark.unit

EMPTY_OBJECT_SCHEMA = {"type": "object", "additionalProperties": True}


def make_task() -> AuditTask:
    return AuditTask(
        task_id="TASK-ORCH",
        project_id="PRJ-ORCH",
        user_request="执行审计程序",
        skill_id="z-1-2-bank-deposits",
        workspace="C:/tmp/workspace",
    )


def make_plan(
    *,
    step_id: str = "P01",
    status: StepStatus = StepStatus.PENDING,
    required_tools: list[str] | None = None,
    human_required: bool = False,
    max_retries: int = 2,
    missing_inputs: list[str] | None = None,
) -> AuditPlan:
    tools = required_tools or []
    step = PlanStep(
        step_id=step_id,
        procedure_id=step_id,
        name=f"程序 {step_id}",
        required_tools=tools,
        human_required=human_required,
        status=status,
        max_retries=max_retries,
    )
    return AuditPlan(
        plan_id="PLAN-ORCH",
        task_id="TASK-ORCH",
        skill_id="z-1-2-bank-deposits",
        steps=[step],
        execution_order=[[step_id]],
        missing_inputs=missing_inputs or [],
        validated=True,
    )


def make_registry(handler, *, name: str = "demo_tool", max_retries: int = 0) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name=name,
            description="测试工具",
            risk_level=ToolRiskLevel.READ_ONLY,
            input_schema=EMPTY_OBJECT_SCHEMA,
            max_retries=max_retries,
        ),
        handler,
    )
    return registry


def policy(*names: str) -> PermissionPolicy:
    return PermissionPolicy(allowed_tools=set(names), max_tool_calls=50)


def call_provider(task: AuditTask, step: PlanStep) -> list[ToolCall]:
    return [ToolCall(tool_name=name, arguments={"step": step.step_id}) for name in step.required_tools]


def test_missing_input_pauses_before_tool_execution(tmp_path: Path) -> None:
    called = False

    async def handler(_arguments, _context):
        nonlocal called
        called = True
        return {"ok": True}

    task = make_task()
    plan = make_plan(status=StepStatus.BLOCKED, required_tools=["demo_tool"], missing_inputs=["bank_statement"])
    plan.step("P01").missing_inputs = ["bank_statement"]
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    result = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
        )
    )

    assert result.status is TaskStatus.WAITING_INPUT
    assert result.waiting_input_steps == ["P01"]
    assert called is False


def test_automatic_tool_step_completes_after_quality_gate(tmp_path: Path) -> None:
    async def handler(_arguments, _context):
        return {"ok": True}

    task = make_task()
    plan = make_plan(required_tools=["demo_tool"])
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    result = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
        )
    )

    assert result.status is TaskStatus.COMPLETED
    assert result.verified_steps == ["P01"]
    assert plan.step("P01").status is StepStatus.VERIFIED


def test_human_step_pauses_then_resumes_to_completion() -> None:
    task = make_task()
    plan = make_plan(status=StepStatus.WAITING_HUMAN, human_required=True)
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(ToolRegistry()),
    )

    paused = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy(),
            tool_call_provider=call_provider,
        )
    )
    assert paused.status is TaskStatus.WAITING_HUMAN
    assert paused.waiting_human_steps == ["P01"]

    resumed = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy(),
            tool_call_provider=call_provider,
            human_submissions={
                "P01": HumanSubmission(step_id="P01", actor="reviewer", comment="已复核")
            },
        )
    )
    assert resumed.status is TaskStatus.COMPLETED
    assert resumed.verified_steps == ["P01"]


def test_independent_steps_in_same_layer_still_advance(tmp_path: Path) -> None:
    async def handler(_arguments, _context):
        return {"ok": True}

    task = make_task()
    plan = AuditPlan(
        plan_id="PLAN-LAYER",
        task_id="TASK-ORCH",
        skill_id="z-1-2-bank-deposits",
        steps=[
            PlanStep(
                step_id="P01",
                procedure_id="P01",
                name="自动程序",
                required_tools=["demo_tool"],
                status=StepStatus.PENDING,
            ),
            PlanStep(
                step_id="P02",
                procedure_id="P02",
                name="人工程序",
                human_required=True,
                status=StepStatus.WAITING_HUMAN,
            ),
        ],
        execution_order=[["P01", "P02"]],
        validated=True,
    )
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    result = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
        )
    )

    assert result.status is TaskStatus.WAITING_HUMAN
    assert plan.step("P01").status is StepStatus.VERIFIED
    assert plan.step("P02").status is StepStatus.WAITING_HUMAN


def test_retryable_failure_exhausts_step_retries_then_escalates(tmp_path: Path) -> None:
    calls = 0

    async def handler(_arguments, _context):
        nonlocal calls
        calls += 1
        return ToolResult.fail("demo_tool", "临时失败", failure_class=FailureClass.RETRYABLE)

    task = make_task()
    plan = make_plan(required_tools=["demo_tool"], max_retries=2)
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    result = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
        )
    )

    assert calls == 3
    assert result.status is TaskStatus.WAITING_HUMAN
    assert result.waiting_human_steps == ["P01"]

    resumed = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
            human_submissions={
                "P01": HumanSubmission(step_id="P01", actor="reviewer", comment="人工接管并复核")
            },
        )
    )
    assert resumed.status is TaskStatus.COMPLETED
    assert calls == 3


def test_terminal_failure_marks_task_failed(tmp_path: Path) -> None:
    async def handler(_arguments, _context):
        raise ToolExecutionError("格式损坏", failure_class=FailureClass.TERMINAL)

    task = make_task()
    plan = make_plan(required_tools=["demo_tool"])
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    result = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
        )
    )

    assert result.status is TaskStatus.FAILED
    assert result.failed_steps == ["P01"]


def test_terminal_failure_can_be_replanned(tmp_path: Path) -> None:
    calls = 0
    replans = 0

    async def handler(_arguments, _context):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ToolExecutionError("首次执行失败", failure_class=FailureClass.TERMINAL)
        return {"ok": True}

    def replanner(_task, _plan, _reason):
        nonlocal replans
        replans += 1
        replacement = make_plan(required_tools=["demo_tool"])
        return replacement.model_copy(update={"plan_id": "PLAN-ORCH-REPLAN"})

    task = make_task()
    plan = make_plan(required_tools=["demo_tool"])
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    result = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
            replanner=replanner,
            max_replans=1,
        )
    )

    assert replans == 1
    assert result.replans == 1
    assert result.status is TaskStatus.COMPLETED
    assert result.plan_id == "PLAN-ORCH-REPLAN"


def test_tool_output_can_require_human_review_then_resume(tmp_path: Path) -> None:
    async def handler(_arguments, _context):
        return ToolResult.ok("demo_tool", {"ok": True}, requires_human_review=True)

    task = make_task()
    plan = make_plan(required_tools=["demo_tool"])
    orchestrator = AgentOrchestrator(
        state_machine=TaskStateMachine(),
        tool_executor=ToolExecutor(make_registry(handler)),
    )

    paused = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
        )
    )
    assert paused.status is TaskStatus.WAITING_HUMAN

    resumed = asyncio.run(
        orchestrator.execute(
            task,
            plan,
            permission_policy=policy("demo_tool"),
            tool_call_provider=call_provider,
            workspace_root=tmp_path,
            human_submissions={
                "P01": HumanSubmission(step_id="P01", actor="reviewer", comment="已复核工具结果")
            },
        )
    )
    assert resumed.status is TaskStatus.COMPLETED