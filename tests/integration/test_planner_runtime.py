"""Planner 与真实 Node ToolRegistry 的集成验收。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.planning import AuditPlanner, SkillValidator
from agent.skills import SkillLoader, SkillRegistry
from agent.tools import NodeToolBridge, ToolRegistry, register_node_core_tools

pytestmark = pytest.mark.integration


def test_bank_planner_uses_registered_runtime_tools(repo_root: Path) -> None:
    async def scenario() -> None:
        bridge = NodeToolBridge(repo_root.parent)
        try:
            tool_registry = ToolRegistry()
            await register_node_core_tools(tool_registry, bridge)
            skill_registry = SkillRegistry(repo_root).load()
            loader = SkillLoader(repo_root, skill_registry)
            validator = SkillValidator(
                loader,
                available_tools=set(tool_registry.list_names()),
            )
            config_root = repo_root / "agent" / "config" / "procedures"
            planner = AuditPlanner(validator, config_root=config_root)
            plan = planner.build_plan(
                task_id="TASK-PLANNER-RUNTIME",
                skill_id="z-1-2-bank-deposits",
                provided_inputs={
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
                },
            )
            assert plan.execution_order == [
                ["P01"],
                ["P02", "P08"],
                ["P04"],
                ["P06"],
                ["P07"],
                ["P10"],
            ]
        finally:
            await bridge.close()

    asyncio.run(scenario())
