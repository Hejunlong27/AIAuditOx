"""Tool Registry / Executor 与双模式能力解析测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agent.models.enums import FailureClass, ToolRequirementLevel, ToolRiskLevel
from agent.models.result import ToolResult
from agent.models.tool import ToolInvocation, ToolRequirement, ToolSpec
from agent.security.permissions import PermissionPolicy
from agent.tools import (
    ToolExecutionError,
    ToolExecutor,
    ToolRegistry,
    load_tool_requirements,
    register_node_core_tools,
    resolve_skill_tools,
)
from agent.tools.registry import ToolCapabilityError

pytestmark = pytest.mark.unit


def spec(
    name: str = "demo_tool",
    *,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    max_retries: int = 0,
    timeout_seconds: float = 1,
    requires_approval: bool = False,
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="测试工具",
        input_schema=input_schema or {},
        output_schema=output_schema or {},
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        requires_approval=requires_approval,
        risk_level=risk_level,
    )


async def ok_handler(arguments: dict[str, Any], _context) -> dict[str, Any]:
    return {"echo": arguments.get("value")}


def policy(*names: str, max_tool_calls: int = 10) -> PermissionPolicy:
    return PermissionPolicy(allowed_tools=set(names), max_tool_calls=max_tool_calls)


class TestToolRegistry:
    def test_register_duplicate_rejected(self) -> None:
        registry = ToolRegistry()
        registry.register(spec(), ok_handler)
        with pytest.raises(ValueError, match="已注册"):
            registry.register(spec(), ok_handler)

    def test_capability_resolution_reports_double_mode_fallbacks(self) -> None:
        registry = ToolRegistry()
        registry.register(spec("present"), ok_handler)
        resolution = registry.resolve(
            [
                ToolRequirement(name="present", level=ToolRequirementLevel.REQUIRED),
                ToolRequirement(
                    name="absent_preferred",
                    level=ToolRequirementLevel.PREFERRED,
                    fallback="skill_local",
                ),
                ToolRequirement(name="absent_optional", level=ToolRequirementLevel.OPTIONAL),
            ]
        )
        assert resolution.can_run is True
        assert resolution.degraded is True
        assert resolution.available == ("present",)
        assert resolution.missing_preferred == ("absent_preferred",)
        assert resolution.missing_optional == ("absent_optional",)
        assert resolution.fallbacks == {"absent_preferred": "skill_local"}

    def test_missing_required_blocks(self) -> None:
        registry = ToolRegistry()
        resolution = registry.resolve(
            [ToolRequirement(name="required_tool", level=ToolRequirementLevel.REQUIRED)]
        )
        assert resolution.can_run is False
        with pytest.raises(ToolCapabilityError, match="required_tool"):
            registry.require(
                [ToolRequirement(name="required_tool", level=ToolRequirementLevel.REQUIRED)]
            )

    def test_preferred_without_fallback_blocks(self) -> None:
        resolution = ToolRegistry().resolve(
            [ToolRequirement(name="preferred_tool", level=ToolRequirementLevel.PREFERRED)]
        )
        assert resolution.can_run is False


class TestToolRequirementManifest:
    def test_explicit_manifest_allows_standalone_fallback(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "tool-requirements.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "requirements": [
                        {"name": "present", "level": "required"},
                        {
                            "name": "excel_read",
                            "level": "preferred",
                            "fallback": "skill_local",
                        },
                        {"name": "pdf_ops", "level": "optional"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        manifest = load_tool_requirements(skill)
        assert manifest.schema_version == 1
        assert len(manifest.requirements) == 3

        registry = ToolRegistry()
        registry.register(spec("present"), ok_handler)
        resolution = resolve_skill_tools(registry, skill)
        assert resolution.can_run is True
        assert resolution.degraded is True
        assert resolution.fallbacks == {"excel_read": "skill_local"}

    def test_missing_manifest_derives_required_tools_from_dsl(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "dsl.json").write_text(
            json.dumps(
                {
                    "skill_id": "demo",
                    "procedures": [
                        {"id": "P01", "tools": ["recalc_check", "rule_check"]},
                        {"id": "P02", "tools": ["recalc_check"]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        manifest = load_tool_requirements(skill)
        assert [item.name for item in manifest.requirements] == ["recalc_check", "rule_check"]
        assert all(item.level is ToolRequirementLevel.REQUIRED for item in manifest.requirements)

        registry = ToolRegistry()
        registry.register(spec("recalc_check"), ok_handler)
        resolution = resolve_skill_tools(registry, skill)
        assert resolution.can_run is False
        assert resolution.missing_required == ("rule_check",)

    def test_runtime_override_is_used_without_skill_manifest(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill-library" / "demo-skill"
        skill.mkdir(parents=True)
        override = tmp_path / "requirements.json"
        override.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "skills": {
                        "demo-skill": [
                            {
                                "name": "excel_read",
                                "level": "preferred",
                                "fallback": "skill_local",
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        manifest = load_tool_requirements(skill, override_file=override)
        assert manifest.requirements[0].name == "excel_read"
        assert manifest.requirements[0].level is ToolRequirementLevel.PREFERRED

    def test_skill_manifest_takes_precedence_over_runtime_override(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill-library" / "demo-skill"
        skill.mkdir(parents=True)
        (skill / "tool-requirements.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "requirements": [{"name": "recalc_check", "level": "required"}],
                }
            ),
            encoding="utf-8",
        )
        override = tmp_path / "requirements.json"
        override.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "skills": {
                        "demo-skill": [
                            {"name": "excel_read", "level": "optional"}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        manifest = load_tool_requirements(skill, override_file=override)
        assert [item.name for item in manifest.requirements] == ["recalc_check"]

    def test_duplicate_manifest_names_rejected(self, tmp_path: Path) -> None:
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "tool-requirements.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "requirements": [
                        {"name": "recalc_check", "level": "required"},
                        {"name": "recalc_check", "level": "optional"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="工具能力声明重复"):
            load_tool_requirements(skill)


class TestNodeCoreAdapter:
    def test_ok_false_is_mapped_to_need_human(self, tmp_path: Path) -> None:
        class FakeBridge:
            project_root = tmp_path

            async def list_tools(self):
                return [
                    {
                        "name": "excel_read",
                        "description": "读 Excel",
                        "inputSchema": {
                            "type": "object",
                            "required": ["path"],
                            "properties": {"path": {"type": "string"}},
                        },
                        "outputSchema": {},
                        "deterministic": True,
                        "idempotent": True,
                        "riskLevel": "READ_ONLY",
                    }
                ]

            async def call_tool(self, _name, _arguments, *, timeout=30):
                return {"ok": False, "error": "缺少 exceljs"}

        async def scenario():
            registry = ToolRegistry()
            await register_node_core_tools(registry, FakeBridge())
            executor = ToolExecutor(registry)
            return await executor.execute(
                "excel_read",
                {"path": "a.xlsx"},
                policy=policy("excel_read"),
                task_id="TASK-1",
                workspace_root=tmp_path,
            )

        result = asyncio.run(scenario())
        assert result.success is False
        assert result.failure_class is FailureClass.NEED_HUMAN
        assert "exceljs" in (result.error or "")


class TestToolExecutor:
    def test_success_and_audit_record(self) -> None:
        records: list[ToolInvocation] = []
        registry = ToolRegistry()
        registry.register(spec(), ok_handler)
        executor = ToolExecutor(registry, audit_sink=records.append)

        result = asyncio.run(
            executor.execute(
                "demo_tool",
                {"value": 7},
                policy=policy("demo_tool"),
                task_id="TASK-1",
                execution_id="EXEC-1",
            )
        )

        assert result.success is True
        assert result.result == {"echo": 7}
        assert result.execution_id == "EXEC-1"
        assert records[0].tool_name == "demo_tool"
        assert records[0].success is True

    def test_permission_denied_does_not_run_handler(self) -> None:
        called = False

        async def handler(_arguments, _context):
            nonlocal called
            called = True
            return {}

        registry = ToolRegistry()
        registry.register(spec(), handler)
        executor = ToolExecutor(registry)
        result = asyncio.run(
            executor.execute("demo_tool", {}, policy=policy(), task_id="TASK-1")
        )
        assert result.success is False
        assert result.failure_class is FailureClass.NEED_HUMAN
        assert called is False

    def test_retryable_failure_retries_until_success(self) -> None:
        calls = 0

        async def flaky(_arguments, _context):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ToolExecutionError("暂时失败", failure_class=FailureClass.RETRYABLE)
            return {"ok": True}

        registry = ToolRegistry()
        registry.register(spec(max_retries=2), flaky)
        p = policy("demo_tool")
        result = asyncio.run(
            executor_execute(registry, p)
        )
        assert result.success is True
        assert calls == 3
        assert p.call_count == 3

    def test_timeout_is_retryable(self) -> None:
        async def slow(_arguments, _context):
            await asyncio.sleep(0.05)
            return {}

        registry = ToolRegistry()
        registry.register(spec(timeout_seconds=0.01), slow)
        result = asyncio.run(executor_execute(registry, policy("demo_tool")))
        assert result.success is False
        assert result.failure_class is FailureClass.RETRYABLE
        assert "超时" in (result.error or "")

    def test_required_approval_blocks_execution(self) -> None:
        called = False

        async def handler(_arguments, _context):
            nonlocal called
            called = True
            return {}

        registry = ToolRegistry()
        registry.register(spec(requires_approval=True), handler)
        result = asyncio.run(executor_execute(registry, policy("demo_tool")))
        assert result.success is False
        assert result.failure_class is FailureClass.NEED_HUMAN
        assert called is False

    def test_input_schema_rejects_missing_required_field(self) -> None:
        registry = ToolRegistry()
        registry.register(
            spec(
                input_schema={
                    "type": "object",
                    "required": ["value"],
                    "properties": {"value": {"type": "number"}},
                    "additionalProperties": False,
                }
            ),
            ok_handler,
        )
        result = asyncio.run(executor_execute(registry, policy("demo_tool"), arguments={}))
        assert result.success is False
        assert result.failure_class is FailureClass.TERMINAL
        assert "value" in (result.error or "")

    def test_output_schema_rejects_invalid_result(self) -> None:
        registry = ToolRegistry()
        registry.register(
            spec(output_schema={"type": "object", "required": ["ok"]}),
            ok_handler,
        )
        result = asyncio.run(executor_execute(registry, policy("demo_tool")))
        assert result.success is False
        assert result.failure_class is FailureClass.TERMINAL
        assert "schema" in (result.error or "")


def executor_execute(
    registry: ToolRegistry,
    permission: PermissionPolicy,
    *,
    arguments: dict[str, Any] | None = None,
) -> Any:
    executor = ToolExecutor(registry)
    return executor.execute(
        "demo_tool",
        arguments or {},
        policy=permission,
        task_id="TASK-1",
    )
