"""工具文件参数的工作区边界策略。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


class ToolPathError(ValueError):
    """工具文件路径缺失工作区上下文或越出工作区。"""


def _resolve_one(raw: Any, workspace_root: Path) -> str:
    if not isinstance(raw, str):
        raise ToolPathError(f"文件路径必须是字符串，实际为 {type(raw).__name__}")
    value = raw.strip()
    if not value:
        return value
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(workspace_root):
        raise ToolPathError(f"文件路径越出任务工作区：{resolved}")
    return str(resolved)


def normalize_workspace_paths(
    arguments: dict[str, Any],
    path_fields: Iterable[str],
    workspace_root: Path | None,
) -> dict[str, Any]:
    """返回文件参数已规范化为工作区内绝对路径的新参数对象。"""
    fields = tuple(path_fields)
    if not fields:
        return dict(arguments)
    if workspace_root is None:
        raise ToolPathError("该工具包含文件参数，但执行上下文未提供 workspace_root")
    root = Path(workspace_root).resolve()
    normalized = dict(arguments)
    for field in fields:
        if field not in normalized or normalized[field] in (None, ""):
            continue
        value = normalized[field]
        if isinstance(value, list):
            normalized[field] = [_resolve_one(item, root) for item in value]
        else:
            normalized[field] = _resolve_one(value, root)
    return normalized
