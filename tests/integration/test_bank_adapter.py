"""Bank-deposit adapter unit and real-tool end-to-end tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.adapters.bank_deposits import BankDepositsAdapter
from agent.application import TaskApplicationService
from agent.config.settings import Settings
from agent.models import TaskStatus
from agent.planning import AuditPlanner, SkillValidator
from agent.skills import SkillLoader, SkillRegistry
from agent.skills.router import SkillRouter
from agent.storage.database import Database
from agent.tools import NodeToolBridge, ToolRegistry, register_node_core_tools

pytestmark = pytest.mark.integration

FACT_ROOT = Path(r'D:\编程\AIAuditOx\skill-library')
SAMPLE = FACT_ROOT / 'z-1-2-bank-deposits' / 'tests' / 'sandbox' / 'inputs'
SKILL_ID = 'z-1-2-bank-deposits'

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (SAMPLE / 'accounts.csv').is_file(),
        reason='需要统一工作区中的银行存款样例数据',
    ),
]


def _inputs(tmp_path: Path) -> dict[str, Path]:
    disclosure = tmp_path / 'disclosure_draft.csv'
    disclosure.write_text(
        '项目,是否披露\n银行存款,是\n受限货币资金,是\n',
        encoding='utf-8',
    )
    return {
        'bank_balance_detail': SAMPLE / 'accounts.csv',
        'general_ledger': SAMPLE / 'accounts.csv',
        'financial_statement': SAMPLE / 'accounts.csv',
        'bank_account_list': SAMPLE / 'accounts.csv',
        'time_deposit_certificates': SAMPLE / 'accounts.csv',
        'bank_reconciliation': SAMPLE / 'recon_items_A002.csv',
        'bank_statement': SAMPLE / 'statement_A002.csv',
        'confirmation_requests_responses': SAMPLE / 'confirmations.csv',
        'bank_journal': SAMPLE / 'journal_A002.csv',
        'interest_income': SAMPLE / 'interest.csv',
        'interest_rate': SAMPLE / 'interest.csv',
        'disclosure_draft': disclosure,
    }


def test_bank_adapter_builds_all_program_calls(tmp_path: Path) -> None:
    adapter = BankDepositsAdapter(_inputs(tmp_path))
    assert len(adapter.calls['P01']) == 2
    assert len(adapter.calls['P04']) == 5
    assert len(adapter.calls['P06']) == 2
    assert len(adapter.calls['P08']) == 2
    assert len(adapter.calls['P10']) == 1
    assert adapter.calls['P01'][0].arguments['operands'] == [11210000.0, 11200000.0]
    assert all(call.source_files for calls in adapter.calls.values() for call in calls)


def test_bank_task_runs_without_calls_json(repo_root: Path, tmp_path: Path) -> None:
    async def scenario() -> None:
        bridge = NodeToolBridge(repo_root.parent)
        try:
            registry = ToolRegistry()
            await register_node_core_tools(registry, bridge)
            skill_registry = SkillRegistry(
                repo_root,
                skills_dir=FACT_ROOT,
                registry_file=repo_root / 'registry' / 'skill-library.json',
            ).load()
            loader = SkillLoader(repo_root, skill_registry)
            validator = SkillValidator(loader, available_tools=set(registry.list_names()))
            planner = AuditPlanner(
                validator,
                config_root=repo_root / 'agent' / 'config' / 'procedures',
            )
            settings = Settings(
                repo_root=repo_root,
                skills_dir=FACT_ROOT,
                registry_path=repo_root / 'registry' / 'skill-library.json',
                data_root=tmp_path / 'storage',
                workspace_root=tmp_path / 'workspaces',
                artifacts_root=tmp_path / 'artifacts',
            )
            settings.ensure_dirs()
            database = Database(settings.resolved_database_url)
            database.create_all()
            service = TaskApplicationService(
                settings=settings,
                database=database,
                tool_registry=registry,
                skill_router=SkillRouter(skill_registry),
                planner=planner,
            )
            project = service.create_project(name='自动适配验收', period='2026')
            bundle = service.create_task(
                project_id=project.project_id,
                user_request='执行银行存款审计程序',
                skill_id=SKILL_ID,
                input_files=_inputs(tmp_path),
            )
            task_id = bundle.task.task_id
            result = await service.run_task(task_id)
            for _ in range(8):
                if result.task.status is TaskStatus.COMPLETED:
                    break
                pending = service.list_pending_approvals(task_id)
                assert pending, result.result.message
                for approval in pending:
                    service.submit_human_review(
                        approval.approval_id,
                        approved=True,
                        actor='验收员',
                        comment=f'{approval.procedure_id} 自动适配验收通过',
                    )
                result = await service.run_task(task_id)

            assert result.task.status is TaskStatus.COMPLETED
            assert result.plan.step('P09').status.value == 'SKIPPED_NOT_APPLICABLE'
            assert service.repository.list_evidence(task_id)
            workpaper = service.export_workpaper(task_id, prepared_by='验收员', reviewer='复核员')
            assert Path(workpaper.path).is_file()
        finally:
            await bridge.close()

    asyncio.run(scenario())
