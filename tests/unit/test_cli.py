"""CLI smoke tests and explicit tool-call provider tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent.application import JsonToolCallProvider
from agent.models import AuditTask, PlanStep
from cli.main import app

pytestmark = pytest.mark.unit


def test_json_tool_call_provider_returns_step_calls(tmp_path: Path) -> None:
    path = tmp_path / "calls.json"
    path.write_text(
        json.dumps(
            {
                "P01": [
                    {"tool_name": "recalc_check", "arguments": {"operands": [1, 2]}}
                ]
            }
        ),
        encoding="utf-8",
    )
    provider = JsonToolCallProvider.from_file(path)
    task = AuditTask(
        task_id="T1",
        project_id="P1",
        user_request="x",
        workspace=str(tmp_path),
    )
    step = PlanStep(step_id="P01", procedure_id="P01", name="x", required_tools=["recalc_check"])

    assert provider(task, step)[0].tool_name == "recalc_check"


def test_cli_project_create_and_list(repo_root: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    common = [
        "--repo-root",
        str(repo_root),
        "--data-root",
        str(tmp_path / "data"),
        "--workspace-root",
        str(tmp_path / "workspaces"),
    ]
    created = runner.invoke(app, [*common, "project", "create", "--name", "CLI 测试项目"])
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    assert payload["name"] == "CLI 测试项目"
    assert payload["project_id"].startswith("PRJ-")

    listed = runner.invoke(app, [*common, "project", "list"])
    assert listed.exit_code == 0, listed.output
    projects = json.loads(listed.output)
    assert any(item["project_id"] == payload["project_id"] for item in projects)
