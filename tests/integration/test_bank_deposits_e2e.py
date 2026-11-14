"""End-to-end acceptance for the real bank-deposit plan and shared tool kernel."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.core import AgentOrchestrator, TaskStateMachine
from agent.models import (
    AuditTask,
    HumanSubmission,
    StepStatus,
    TaskStatus,
    ToolCall,
    ToolRiskLevel,
    ToolSpec,
)
from agent.planning import AuditPlanner, SkillValidator
from agent.security.permissions import PermissionPolicy
from agent.skills import SkillLoader, SkillRegistry
from agent.tools import ToolExecutor, ToolRegistry

pytestmark = pytest.mark.integration

SKILL_ID = "z-1-2-bank-deposits"
BANK_TOOLS = {
    "recalc_check",
    "balance_confirm",
    "recon_statement_recalc",
    "threshold_flag",
    "bank_reconcile_dual",
    "sampling_draw",
    "rule_check",
}
ALL_INPUTS = {
    "bank_balance_detail",
    "general_ledger",
    "financial_statement",
    "bank_account_list",
    "time_deposit_certificates",
    "bank_reconciliation",
    "bank_statement",
    "confirmation_requests_responses",
    "bank_journal",
    "interest_income",
    "interest_rate",
    "disclosure_draft",
    "fund_pool_agreements",
    "related_party_transactions",
}


def test_bank_deposits_runs_to_completion_through_orchestrator(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        registry = ToolRegistry()
        calls: list[str] = []

        async def handler(arguments, _context):
            calls.append(str(arguments["tool"]))
            return {"ok": True, "tool": arguments["tool"], "step": arguments["step"]}

        for tool_name in sorted(BANK_TOOLS):
            registry.register(
                ToolSpec(
                    name=tool_name,
                    description=f"测试桩：{tool_name}",
                    risk_level=ToolRiskLevel.READ_ONLY,
                    input_schema={
                        "type": "object",
                        "required": ["tool", "step"],
                        "properties": {
                            "tool": {"type": "string"},
                            "step": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                ),
                handler,
            )

        skill_registry = SkillRegistry(repo_root).load()
        loader = SkillLoader(repo_root, skill_registry)
        validator = SkillValidator(loader, available_tools=set(registry.list_names()))
        planner = AuditPlanner(
            validator,
            config_root=repo_root / "agent" / "config" / "procedures",
        )
        plan = planner.build_plan(
            task_id="TASK-BANK-E2E",
            skill_id=SKILL_ID,
            provided_inputs=ALL_INPUTS,
        )
        assert plan.execution_order == [
            ["P01"],
            ["P02", "P08"],
            ["P04"],
            ["P06"],
            ["P07"],
            ["P10"],
        ]

        task = AuditTask(
            task_id="TASK-BANK-E2E",
            project_id="PRJ-BANK-E2E",
            user_request="执行银行存款审计程序",
            skill_id=SKILL_ID,
            workspace=str(tmp_path / "workspace"),
        )

        def provider(_task, step):
            return [
                ToolCall(
                    tool_name=tool_name,
                    arguments={"tool": tool_name, "step": step.step_id},
                )
                for tool_name in step.required_tools
            ]

        submissions = {
            step_id: HumanSubmission(
                step_id=step_id,
                actor="reviewer",
                comment=f"{step_id} 人工复核完成",
            )
            for step_id in plan.human_tasks
            if plan.step(step_id).status is not StepStatus.SKIPPED_NOT_APPLICABLE
        }
        orchestrator = AgentOrchestrator(
            state_machine=TaskStateMachine(),
            tool_executor=ToolExecutor(registry),
        )
        result = await orchestrator.execute(
            task,
            plan,
            permission_policy=PermissionPolicy(allowed_tools=BANK_TOOLS),
            tool_call_provider=provider,
            workspace_root=tmp_path,
            human_submissions=submissions,
        )

        assert result.status is TaskStatus.COMPLETED
        assert result.skipped_steps == ["P09"]
        assert result.verified_steps == [
            "P01",
            "P02",
            "P03",
            "P04",
            "P05",
            "P06",
            "P07",
            "P08",
            "P10",
        ]
        assert len(calls) == 9
        assert plan.step("P10").status is StepStatus.VERIFIED

    asyncio.run(scenario())