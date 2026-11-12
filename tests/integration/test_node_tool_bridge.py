"""Node 中心工具桥的真实集成测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.models.enums import FailureClass
from agent.security.permissions import PermissionPolicy
from agent.tools import NodeToolBridge, ToolExecutor, ToolRegistry, register_node_core_tools
from agent.tools.node_bridge import NodeBridgeTransportError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_AVAILABLE = (
    (PROJECT_ROOT / 'skill-library').is_dir()
    and (PROJECT_ROOT / 'skill-tools' / 'auditox-tools').is_dir()
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not WORKSPACE_AVAILABLE, reason='需要统一工作区中的 skill-library/skill-tools'),
]


def test_pure_node_tools_execute_through_python_runtime(repo_root: Path) -> None:
    async def scenario() -> None:
        project_root = repo_root.parent
        bridge = NodeToolBridge(project_root)
        try:
            registry = ToolRegistry()
            specs = await register_node_core_tools(registry, bridge)
            assert sorted(spec.name for spec in specs) == [
                "ageing_bucket",
                "balance_confirm",
                "bank_reconcile_dual",
                "csv_to_sheet",
                "cutoff_test",
                "depreciation_calc",
                "excel_read",
                "excel_write",
                "index_numbering",
                "interest_calc",
                "manifest_json",
                "pdf_ops",
                "pdf_tables_to_excel",
                "pdf_to_word",
                "provision_calc",
                "recalc_check",
                "recon_statement_recalc",
                "revision_record",
                "rule_check",
                "sampling_draw",
                "sheet_to_csv",
                "threshold_flag",
                "workpaper_fill",
                "workpaper_spec",
                "wp_to_docx",
                "xlsx_export",
            ]
            assert "z-1-2-bank-deposits" in next(
                spec.declared_by_skills for spec in specs if spec.name == "recalc_check"
            )

            policy = PermissionPolicy(allowed_tools=set(registry.list_names()))
            executor = ToolExecutor(registry)
            workpaper_args = {
                "header": {
                    "client": "示例公司",
                    "period": "2025",
                    "index": "Z-1-2-01",
                    "preparer": "A",
                    "date": "2025-12-31",
                    "reviewer": "B",
                },
                "name": "银行存款审计工作底稿",
                "goal": "验证银行存款余额",
                "program_rows": [{"procedure": "获取并核对余额明细表", "assertion": "E"}],
                "result_sections": [{"title": "核对结果", "rows": [{"k": "差异", "v": "0"}]}],
                "notes": ["数据来源：示例资料"],
                "pending_human": [],
            }
            cases = [
                (
                    "recalc_check",
                    {"op": "diff", "operands": [10, 7]},
                    {"result": 3, "classification": "abnormal"},
                ),
                (
                    "rule_check",
                    {
                        "data": {"a": 1},
                        "schema": {
                            "type": "object",
                            "required": ["a"],
                            "properties": {"a": {"type": "number"}},
                        },
                    },
                    {"valid": True, "classification": "clean"},
                ),
                (
                    "threshold_flag",
                    {
                        "rows": [{"id": "A", "amount": 10}],
                        "field": "amount",
                        "thresholds": [{"op": "gte", "value": 10, "label": "命中"}],
                    },
                    {"flagged_count": 1, "classification": "abnormal"},
                ),
                (
                    "sampling_draw",
                    {"population_size": 10, "sample_size": 3, "seed": 1},
                    {"selected": [4, 8, 9]},
                ),
                (
                    "balance_confirm",
                    {"book": 100, "bank": 100.01, "tolerance_abs": 0.01},
                    {"consistent": True, "classification": "clean"},
                ),
                (
                    "bank_reconcile_dual",
                    {
                        "statement": [{"id": "A", "amount": 100}],
                        "journal": [{"id": "A", "amount": 100}],
                    },
                    {"matched": 1, "diff_rows": 0, "classification": "clean"},
                ),
                (
                    "index_numbering",
                    {
                        "items": [
                            {
                                "kind": "workpaper",
                                "group": "Z",
                                "project": "1-2",
                                "seq": 1,
                                "name": "余额明细表",
                            }
                        ]
                    },
                    {"count": 1, "classification": "clean"},
                ),
                (
                    "manifest_json",
                    {
                        "project": {"project_id": "P1", "name": "示例公司"},
                        "skill_id": "z-1-2-bank-deposits",
                        "workpapers": [
                            {"index": "Z-1-2-01", "name": "余额明细表", "file": "a.md", "revision": 1}
                        ],
                        "review": {"level1_passed": True, "pending_human": []},
                        "coverage": {"deterministic_pct": 100},
                    },
                    {"classification": "clean"},
                ),
                (
                    "revision_record",
                    {
                        "workpaper_index": "Z-1-2-01",
                        "entries": [{"action": "init", "summary": "创建底稿"}],
                    },
                    {"version_count": 1, "classification": "clean"},
                ),
                (
                    "workpaper_fill",
                    workpaper_args,
                    {"index": "Z-1-2-01", "classification": "clean"},
                ),
                (
                    "workpaper_spec",
                    workpaper_args,
                    {"classification": "clean"},
                ),
                (
                    "recon_statement_recalc",
                    {"book_balance": 100, "statement_balance": 100, "items": []},
                    {"balanced": True, "classification": "clean"},
                ),
                (
                    "ageing_bucket",
                    {
                        "balance_date": "2025-12-31",
                        "rows": [{"id": "A", "date": "2025-12-01", "amount": 100}],
                    },
                    {"total": 100, "classification": "clean"},
                ),
                (
                    "provision_calc",
                    {
                        "booked_provision": 45,
                        "ageing": [
                            {"label": "1年以内", "amount": 1000, "rate": 2},
                            {"label": "1-2年", "amount": 500, "rate": 5},
                        ],
                    },
                    {"computed_provision": 45, "classification": "clean"},
                ),
                (
                    "depreciation_calc",
                    {
                        "cost": 120000,
                        "useful_life_years": 5,
                        "start_date": "2020-01-01",
                        "period_start": "2022-01-01",
                        "period_end": "2022-12-31",
                        "method": "straight",
                    },
                    {"period_depreciation": 24000, "classification": "clean"},
                ),
                (
                    "interest_calc",
                    {
                        "principal": 1000000,
                        "annual_rate": 4.35,
                        "start_date": "2025-01-01",
                        "end_date": "2025-12-31",
                        "day_count": "actual/365",
                    },
                    {"interest": 43380.82, "classification": "clean"},
                ),
                (
                    "cutoff_test",
                    {
                        "period_end": "2025-12-31",
                        "rows": [
                            {
                                "id": "1",
                                "doc_date": "2025-12-20",
                                "recorded_period": "2025-12",
                                "amount": 100,
                            }
                        ],
                    },
                    {"row_count": 1, "cross_period_count": 0, "classification": "clean"},
                ),
            ]

            for index, (name, arguments, expected) in enumerate(cases):
                result = await executor.execute(
                    name,
                    arguments,
                    policy=policy,
                    task_id="TASK-NODE-1",
                    execution_id=f"EXEC-NODE-{index}",
                )
                assert result.success is True, result.error
                for key, want in expected.items():
                    assert result.result[key] == want
            assert policy.call_count == len(cases)
        finally:
            await bridge.close()

    asyncio.run(scenario())


def test_bridge_rejects_tool_outside_whitelist(repo_root: Path) -> None:
    async def scenario() -> None:
        bridge = NodeToolBridge(repo_root.parent)
        try:
            with pytest.raises(NodeBridgeTransportError, match="白名单"):
                await bridge.call_tool("not_a_tool", {})
        finally:
            await bridge.close()

    asyncio.run(scenario())


def test_office_tools_use_workspace_boundary(repo_root: Path, tmp_path: Path) -> None:
    async def scenario() -> None:
        bridge = NodeToolBridge(repo_root.parent)
        try:
            registry = ToolRegistry()
            await register_node_core_tools(registry, bridge)
            policy = PermissionPolicy(allowed_tools=set(registry.list_names()))
            executor = ToolExecutor(registry)

            write = await executor.execute(
                "excel_write",
                {
                    "path": "output.xlsx",
                    "sheets": [
                        {
                            "name": "余额",
                            "rows": [["ID", "Amount"], ["A", 100]],
                        }
                    ],
                },
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert write.success is True, write.error
            assert write.result["ok"] is True
            assert (tmp_path / "output.xlsx").is_file()

            read = await executor.execute(
                "excel_read",
                {"path": str(tmp_path / "output.xlsx")},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert read.success is True, read.error
            assert read.result["ok"] is True
            assert read.result["sheets"][0]["rows"][1][0] == "A"

            csv_out = await executor.execute(
                "sheet_to_csv",
                {"path": str(tmp_path / "output.xlsx"), "out": "output.csv"},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert csv_out.success is True, csv_out.error
            assert (tmp_path / "output.csv").is_file()

            from_csv = await executor.execute(
                "csv_to_sheet",
                {"path": "from-csv.xlsx", "csv": "id,amount\nA,1\n"},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert from_csv.success is True, from_csv.error
            assert (tmp_path / "from-csv.xlsx").is_file()

            workpaper = await executor.execute(
                "workpaper_spec",
                {
                    "header": {
                        "client": "示例公司",
                        "period": "2025",
                        "index": "Z-1-2-01",
                        "preparer": "A",
                        "date": "2025-12-31",
                        "reviewer": "B",
                    },
                    "name": "银行存款审计工作底稿",
                    "goal": "验证银行存款余额",
                    "program_rows": [{"procedure": "核对余额", "assertion": "E"}],
                    "result_sections": [
                        {"title": "核对结果", "rows": [{"k": "差异", "v": "0"}]}
                    ],
                    "notes": ["数据来源：示例资料"],
                    "pending_human": [],
                },
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert workpaper.success is True, workpaper.error
            spec = workpaper.result["spec"]

            xlsx = await executor.execute(
                "xlsx_export",
                {"spec": spec, "out": "workpaper.xlsx"},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert xlsx.success is True, xlsx.error
            assert xlsx.result["ok"] is True
            assert (tmp_path / "workpaper.xlsx").is_file()

            docx = await executor.execute(
                "wp_to_docx",
                {"spec": spec, "out": "workpaper.docx"},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert docx.success is True, docx.error
            assert docx.result["ok"] is True
            assert (tmp_path / "workpaper.docx").is_file()

            escape = await executor.execute(
                "excel_write",
                {"path": "../escape.xlsx", "sheets": [{"name": "S", "rows": [["x"]]}]},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert escape.success is False
            assert escape.failure_class is FailureClass.NEED_HUMAN
            assert not (tmp_path.parent / "escape.xlsx").exists()

            no_workspace = await executor.execute(
                "excel_read",
                {"path": str(tmp_path / "output.xlsx")},
                policy=policy,
                task_id="TASK-OFFICE-1",
            )
            assert no_workspace.success is False
            assert no_workspace.failure_class is FailureClass.NEED_HUMAN

            bad_pdf = tmp_path / "invalid.pdf"
            bad_pdf.write_bytes(b"%PDF-1.4\ninvalid\n")
            pdf_result = await executor.execute(
                "pdf_ops",
                {"op": "merge", "inputs": ["invalid.pdf"], "output": "merged.pdf"},
                policy=policy,
                task_id="TASK-OFFICE-1",
                workspace_root=tmp_path,
            )
            assert pdf_result.success is False
            assert pdf_result.failure_class is FailureClass.NEED_HUMAN
        finally:
            await bridge.close()

    asyncio.run(scenario())
