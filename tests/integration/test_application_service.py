"""End-to-end application service tests over a restart-safe SQLite store."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from openpyxl import load_workbook

from agent.application import RouteConfirmationRequired, TaskApplicationService
from agent.config.settings import Settings
from agent.models import TaskStatus, ToolCall, ToolRiskLevel, ToolSpec
from agent.planning import AuditPlanner, SkillValidator
from agent.skills import SkillLoader, SkillRegistry
from agent.skills.router import SkillRouter
from agent.storage.database import Database
from agent.storage.repository import AuditRepository
from agent.tools import ToolRegistry

pytestmark = pytest.mark.integration

SKILL_ID = "z-1-2-bank-deposits"
ALL_INPUTS = [
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
]
BANK_TOOLS = {
    "recalc_check",
    "balance_confirm",
    "recon_statement_recalc",
    "threshold_flag",
    "bank_reconcile_dual",
    "sampling_draw",
    "rule_check",
}


def _tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    async def handler(arguments, _context):
        return {"ok": True, "step": arguments["step"]}

    for name in sorted(BANK_TOOLS):
        registry.register(
            ToolSpec(
                name=name,
                description=f"应用层测试工具 {name}",
                risk_level=ToolRiskLevel.READ_ONLY,
                input_schema={"type": "object", "additionalProperties": True},
            ),
            handler,
        )
    return registry


def _service(
    settings: Settings,
    database: Database,
    tool_registry: ToolRegistry,
    repo_root: Path,
    *,
    repository: AuditRepository | None = None,
) -> TaskApplicationService:
    skill_registry = SkillRegistry(repo_root).load()
    loader = SkillLoader(repo_root, skill_registry)
    validator = SkillValidator(loader, available_tools=set(tool_registry.list_names()))
    planner = AuditPlanner(validator, config_root=repo_root / "agent" / "config" / "procedures")
    return TaskApplicationService(
        settings=settings,
        database=database,
        tool_registry=tool_registry,
        skill_router=SkillRouter(skill_registry),
        planner=planner,
        repository=repository,
    )


def _provider(_task, step):
    return [ToolCall(tool_name=name, arguments={"step": step.step_id}) for name in step.required_tools]


def test_task_inputs_are_copied_hashed_and_persisted(
    tmp_settings: Settings,
    db: Database,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    tools = _tool_registry()
    service = _service(tmp_settings, db, tools, repo_root)
    project = service.create_project(name="测试项目", period="2026")
    bank_file = tmp_path / "bank.csv"
    bank_file.write_text("账户,金额\nA,100\n", encoding="utf-8")

    bundle = service.create_task(
        project_id=project.project_id,
        user_request="执行银行存款审计程序",
        skill_id=SKILL_ID,
        input_files={"bank_balance_detail": bank_file},
        provided_inputs={"bank_balance_detail"},
    )

    inputs = service.task_inputs(bundle.task.task_id)
    assert set(inputs) == {"bank_balance_detail"}
    assert inputs["bank_balance_detail"].is_file()
    assert inputs["bank_balance_detail"].parent.name == "01_原始资料"
    artifacts = AuditRepository(db).list_artifacts(bundle.task.task_id)
    assert len(artifacts) == 1
    assert artifacts[0].sha256
    assert artifacts[0].metadata["logical_input"] == "bank_balance_detail"


def test_task_and_plan_survive_service_restart(
    tmp_settings: Settings,
    db: Database,
    repo_root: Path,
) -> None:
    tools = _tool_registry()
    first = _service(tmp_settings, db, tools, repo_root)
    project = first.create_project(name="可恢复项目", period="2026")
    bundle = first.create_task(
        project_id=project.project_id,
        user_request="执行银行存款审计程序",
        skill_id=SKILL_ID,
        provided_inputs=set(ALL_INPUTS),
    )

    second = _service(tmp_settings, db, tools, repo_root, repository=AuditRepository(db))
    restored_task = second.get_task(bundle.task.task_id)
    restored_plan = second.get_plan(bundle.task.task_id)

    assert restored_task.project_id == project.project_id
    assert restored_task.plan_id == bundle.plan.plan_id
    assert restored_plan.execution_order == bundle.plan.execution_order
    assert [step.step_id for step in restored_plan.steps] == [step.step_id for step in bundle.plan.steps]


def test_bank_task_resumes_after_approval_across_service_instances(
    tmp_settings: Settings,
    db: Database,
    repo_root: Path,
    tmp_path: Path,
) -> None:
    tools = _tool_registry()
    service = _service(tmp_settings, db, tools, repo_root)
    project = service.create_project(name="银行存款应用层验收", period="2026")
    inputs: dict[str, Path] = {}
    for key in ALL_INPUTS:
        path = tmp_path / f"{key}.csv"
        path.write_text(f"key,value\n{key},1\n", encoding="utf-8")
        inputs[key] = path
    bundle = service.create_task(
        project_id=project.project_id,
        user_request="执行银行存款审计程序",
        skill_id=SKILL_ID,
        input_files=inputs,
    )
    task_id = bundle.task.task_id

    source_path = service.task_inputs(task_id)["general_ledger"]

    def provider(_task, step):
        arguments = {"step": step.step_id}
        if step.step_id == "P01":
            arguments["source_file"] = str(source_path)
        return [ToolCall(tool_name=name, arguments=arguments) for name in step.required_tools]

    first = asyncio.run(service.run_task(task_id, tool_call_provider=provider))
    assert first.task.status is TaskStatus.WAITING_HUMAN
    assert first.pending_approvals
    assert first.plan.step("P01").status.value == "VERIFIED"
    assert len(service.repository.list_evidence(task_id)) == 4

    restarted = _service(tmp_settings, db, tools, repo_root, repository=AuditRepository(db))
    final = first
    human_note = Path(bundle.task.workspace) / "03_产出" / "human-review.txt"
    human_note.write_text("人工复核说明", encoding="utf-8")
    attached_once = False
    for _ in range(12):
        pending = restarted.list_pending_approvals(task_id)
        if not pending:
            break
        for approval in pending:
            attachments = []
            if not attached_once:
                attachments = [str(human_note)]
                attached_once = True
            restarted.submit_human_review(
                approval.approval_id,
                approved=True,
                actor="reviewer",
                comment=f"{approval.procedure_id} 已复核",
                attachments=attachments,
            )
        final = asyncio.run(restarted.run_task(task_id, tool_call_provider=provider))

    restored_task = restarted.get_task(task_id)
    restored_plan = restarted.get_plan(task_id)
    assert final.task.status is TaskStatus.COMPLETED
    assert restored_task.status is TaskStatus.COMPLETED
    assert restored_plan.step("P09").status.value == "SKIPPED_NOT_APPLICABLE"
    assert restored_plan.step("P10").status.value == "VERIFIED"

    evidence = restarted.repository.list_evidence(task_id)
    assert len(evidence) == 10
    assert any(item.kind.value == "HUMAN_ATTACHMENT" for item in evidence)
    assert any(item.traceable for item in evidence)

    workpaper = restarted.export_workpaper(
        task_id,
        prepared_by="Codex Test",
        reviewer="Independent Reviewer",
    )
    workpaper_path = Path(workpaper.path)
    preview_path = Path(workpaper.metadata["preview_path"])
    assert workpaper_path.is_file()
    assert preview_path.is_file()
    assert workpaper.kind == "WORKPAPER_XLSX"
    workbook = load_workbook(workpaper_path, data_only=False)
    assert {"工作底稿", "程序明细", "证据清单", "修订记录"}.issubset(workbook.sheetnames)
    assert workbook["工作底稿"]["A1"].value == "银行存款审计程序执行工作底稿"
    assert workbook["证据清单"].max_row >= 2
    assert "四、审计说明" in preview_path.read_text(encoding="utf-8")

    events = restarted.repository.list_audit_events(task_id)
    assert any(event["event"] == "TASK_COMPLETED" for event in events)
    assert any(event["event"] == "WORKPAPER_EXPORTED" for event in events)
    assert any(event["event"] == "APPROVAL_DECIDED" for event in events)
    assert any(event["event"] == "STEP_STATE_CHANGED" for event in events)


def test_explicit_skill_is_required_when_route_is_ambiguous(
    tmp_settings: Settings,
    db: Database,
    repo_root: Path,
) -> None:
    tools = _tool_registry()
    service = _service(tmp_settings, db, tools, repo_root)
    project = service.create_project(name="路由测试")

    with pytest.raises(RouteConfirmationRequired):
        service.create_task(
            project_id=project.project_id,
            user_request="执行审计程序",
        )
