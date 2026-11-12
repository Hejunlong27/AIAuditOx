"""注册第一组 Node 中心工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.models.enums import FailureClass, ToolRiskLevel
from agent.models.tool import ToolSpec
from agent.tools.base import ToolContext, ToolExecutionError
from agent.tools.node_bridge import NodeToolBridge, NodeBridgeTransportError, NodeToolError
from agent.tools.path_policy import ToolPathError, normalize_workspace_paths
from agent.tools.registry import ToolRegistry


def _open_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """放宽旧中心工具的兼容性输出契约，但保留 required 字段要求。

    - 输出对象允许额外证据/诊断字段：``additionalProperties=true``。
    - 非 required 字段允许 ``null``；required 字段仍严格校验。
    - 输入 schema 不做任何放宽。
    """
    result = dict(schema)
    if result.get("type") == "object":
        result["additionalProperties"] = True
        required = set(result.get("required") or [])
        if isinstance(result.get("properties"), dict):
            properties: dict[str, Any] = {}
            for key, value in result["properties"].items():
                if isinstance(value, dict):
                    child = _open_output_schema(value)
                    if key not in required and "type" in child:
                        types = child["type"] if isinstance(child["type"], list) else [child["type"]]
                        if "null" not in types:
                            child["type"] = [*types, "null"]
                    properties[key] = child
                else:
                    properties[key] = value
            result["properties"] = properties
    if isinstance(result.get("items"), dict):
        result["items"] = _open_output_schema(result["items"])
    return result


FILE_PATH_FIELDS: dict[str, tuple[str, ...]] = {
    "xlsx_export": ("out",),
    "wp_to_docx": ("out",),
    "pdf_to_word": ("input", "output"),
    "pdf_tables_to_excel": ("input", "output"),
    "pdf_ops": ("input", "inputs", "output"),
    "excel_read": ("path",),
    "excel_write": ("path",),
    "sheet_to_csv": ("path", "out"),
    "csv_to_sheet": ("path", "csv_path"),
}


def _declaring_skills(project_root: Path) -> dict[str, list[str]]:
    root = project_root / "skill-library"
    result: dict[str, set[str]] = {}
    if not root.is_dir():
        return {}
    for dsl in sorted(root.glob("*/dsl.json")):
        raw = json.loads(dsl.read_text(encoding="utf-8"))
        for procedure in raw.get("procedures", []):
            for tool in procedure.get("tools") or []:
                result.setdefault(str(tool), set()).add(dsl.parent.name)
    return {name: sorted(skills) for name, skills in result.items()}


async def register_node_core_tools(
    registry: ToolRegistry,
    bridge: NodeToolBridge,
    *,
    timeout_seconds: float = 30.0,
) -> list[ToolSpec]:
    """从 Node 桥读取真实工具契约，并注册到 Python Registry。"""
    declared = _declaring_skills(bridge.project_root)
    registered: list[ToolSpec] = []

    for item in await bridge.list_tools():
        name = str(item["name"])

        path_fields = FILE_PATH_FIELDS.get(name, ())

        async def handler(
            arguments: dict[str, Any],
            context: ToolContext,
            *,
            tool_name: str = name,
            file_fields: tuple[str, ...] = path_fields,
        ) -> dict[str, Any]:
            try:
                safe_arguments = normalize_workspace_paths(
                    arguments,
                    file_fields,
                    context.workspace_root,
                )
                result = await bridge.call_tool(
                    tool_name,
                    safe_arguments,
                    timeout=timeout_seconds,
                )
                if result.get("ok") is False:
                    raise ToolExecutionError(
                        str(result.get("error") or f"工具 {tool_name} 报告执行失败"),
                        failure_class=FailureClass.NEED_HUMAN,
                    )
                return result
            except ToolExecutionError:
                raise
            except ToolPathError as exc:
                raise ToolExecutionError(
                    str(exc), failure_class=FailureClass.NEED_HUMAN
                ) from exc
            except NodeBridgeTransportError as exc:
                raise ToolExecutionError(
                    str(exc), failure_class=FailureClass.RETRYABLE
                ) from exc
            except NodeToolError as exc:
                raise ToolExecutionError(
                    str(exc), failure_class=FailureClass.TERMINAL
                ) from exc

        tool_spec = ToolSpec(
            name=name,
            description=str(item.get("description") or name),
            risk_level=ToolRiskLevel(str(item.get("riskLevel") or "READ_ONLY")),
            input_schema=dict(item.get("inputSchema") or {}),
            output_schema=_open_output_schema(dict(item.get("outputSchema") or {})),
            timeout_seconds=timeout_seconds,
            max_retries=0,
            requires_approval=False,
            version="1.0.0",
            deterministic=bool(item.get("deterministic", True)),
            idempotent=bool(item.get("idempotent", True)),
            backend="node",
            supported_hosts=["python", "dsh", "exe"],
            declared_by_skills=declared.get(name, []),
        )
        registry.register(tool_spec, handler)
        registered.append(tool_spec)
    return registered
