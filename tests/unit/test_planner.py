"""Planner/DAG、三源校验与输入缺口测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent.models.enums import StepStatus
from agent.planning import AuditPlanner, PlanningError, SkillValidationError, SkillValidator
from agent.planning.dag import DagError, topological_layers
from agent.skills import SkillLoader, SkillRegistry

pytestmark = pytest.mark.unit

SKILL = "z-1-2-bank-deposits"
TOOLS = {
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


@pytest.fixture(scope="module")
def loader(repo_root: Path) -> SkillLoader:
    registry = SkillRegistry(repo_root).load()
    return SkillLoader(repo_root, registry)


@pytest.fixture(scope="module")
def validator(loader: SkillLoader) -> SkillValidator:
    return SkillValidator(loader, available_tools=TOOLS)


@pytest.fixture(scope="module")
def config_path(repo_root: Path) -> Path:
    return repo_root / "agent" / "config" / "procedures" / "bank_deposits.yaml"


def test_skill_validation_merges_runtime_dependencies(
    validator: SkillValidator,
    config_path: Path,
) -> None:
    result = validator.validate(SKILL, config_path)
    assert len(result.procedures) == 10
    assert result.procedures["P04"].dependencies == ["P02", "P08"]
    assert result.procedures["P09"].enabled_when == "存在资金池或集团资金往来时"
    assert result.procedures["P05"].mandatory is True


def test_planner_execution_order_matches_contract(
    validator: SkillValidator,
    config_path: Path,
) -> None:
    planner = AuditPlanner(validator, config_root=config_path.parent)
    plan = planner.build_plan(
        task_id="TASK-BANK-1",
        skill_id=SKILL,
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
    assert set(plan.human_tasks) == {"P02", "P03", "P04", "P05", "P07", "P10"}
    assert plan.conditional_tasks == ["P09"]
    assert plan.step("P09").status is StepStatus.SKIPPED_NOT_APPLICABLE
    assert plan.missing_inputs == []


def test_planner_activates_conditional_procedure(
    validator: SkillValidator,
    config_path: Path,
) -> None:
    planner = AuditPlanner(validator, config_root=config_path.parent)
    plan = planner.build_plan(
        task_id="TASK-BANK-2",
        skill_id=SKILL,
        provided_inputs=ALL_INPUTS,
        active_conditions={"P09"},
    )
    assert plan.execution_order[-2] == ["P07", "P09"]
    assert plan.step("P09").status is StepStatus.PENDING


def test_missing_inputs_block_steps(
    validator: SkillValidator,
    config_path: Path,
) -> None:
    planner = AuditPlanner(validator, config_root=config_path.parent)
    plan = planner.build_plan(
        task_id="TASK-BANK-3",
        skill_id=SKILL,
        provided_inputs={"bank_balance_detail", "general_ledger", "financial_statement"},
    )
    assert "bank_statement" in plan.missing_inputs
    assert plan.step("P04").status is StepStatus.BLOCKED
    assert "bank_reconciliation" in plan.step("P04").missing_inputs


def test_cycle_between_p01_and_p04_is_rejected(
    validator: SkillValidator,
    config_path: Path,
    tmp_path: Path,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["procedures"]["P01"]["depends_on"] = ["P04"]
    data["procedures"]["P04"]["depends_on"] = ["P01"]
    broken = tmp_path / "bank_deposits_cycle.yaml"
    broken.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SkillValidationError, match="存在环"):
        validator.validate(SKILL, broken)


def test_topological_helper_reports_cycle() -> None:
    with pytest.raises(DagError, match="P01.*P04|P04.*P01"):
        topological_layers({"P01": ["P04"], "P04": ["P01"]})


def test_missing_mandatory_procedure_is_rejected(
    validator: SkillValidator,
    config_path: Path,
    tmp_path: Path,
) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    del data["procedures"]["P05"]
    broken = tmp_path / "bank_deposits_missing_mandatory.yaml"
    broken.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SkillValidationError, match="P05"):
        validator.validate(SKILL, broken)


def test_missing_tool_is_rejected(
    loader: SkillLoader,
    config_path: Path,
) -> None:
    validator = SkillValidator(loader, available_tools=TOOLS - {"rule_check"})
    with pytest.raises(SkillValidationError, match="rule_check"):
        validator.validate(SKILL, config_path)


def test_plan_requires_config_for_unknown_skill(
    validator: SkillValidator,
    config_path: Path,
) -> None:
    planner = AuditPlanner(validator, config_root=config_path.parent)
    with pytest.raises(PlanningError, match="没有 runtime procedure config"):
        planner.build_plan(task_id="TASK-X", skill_id="unknown-skill")
