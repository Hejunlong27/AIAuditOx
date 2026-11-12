"""技能工具能力清单加载。

技能包可选提供 ``tool-requirements.json`` 描述 required/preferred/optional
和 standalone fallback；未提供时，从 ``dsl.json`` 中的所有 tools 推导为
required，避免在工具缺失时静默执行。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from agent.models.base import AuditModel
from agent.models.tool import ToolRequirement
from agent.tools.registry import CapabilityResolution, ToolRegistry


class ToolRequirementManifest(AuditModel):
    """技能包的显式工具能力清单。"""

    schema_version: int = Field(default=1, alias="schemaVersion", ge=1)
    requirements: list[ToolRequirement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> "ToolRequirementManifest":
        names = [item.name for item in self.requirements]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"工具能力声明重复：{duplicates}")
        return self


def _load_override(
    skill_id: str,
    override_file: Path | None,
) -> ToolRequirementManifest | None:
    if override_file is None or not override_file.is_file():
        return None
    raw = json.loads(override_file.read_text(encoding="utf-8"))
    requirements = (raw.get("skills") or {}).get(skill_id)
    if requirements is None:
        return None
    return ToolRequirementManifest(
        schemaVersion=int(raw.get("schemaVersion", 1)),
        requirements=[ToolRequirement.model_validate(item) for item in requirements],
    )


def load_tool_requirements(
    skill_dir: Path,
    *,
    override_file: Path | None = None,
) -> ToolRequirementManifest:
    """按技能清单 → Runtime 覆盖配置 → dsl.json 的顺序读取能力声明。"""
    skill_dir = Path(skill_dir).resolve()
    manifest_path = skill_dir / "tool-requirements.json"
    if manifest_path.is_file():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ToolRequirementManifest.model_validate(raw)

    override = _load_override(skill_dir.name, override_file)
    if override is not None:
        return override

    dsl_path = skill_dir / "dsl.json"
    if not dsl_path.is_file():
        return ToolRequirementManifest()
    raw = json.loads(dsl_path.read_text(encoding="utf-8"))
    names = sorted(
        {
            str(tool)
            for procedure in raw.get("procedures", [])
            for tool in (procedure.get("tools") or [])
        }
    )
    return ToolRequirementManifest(
        requirements=[ToolRequirement(name=name) for name in names]
    )


def resolve_skill_tools(
    registry: ToolRegistry,
    skill_dir: Path,
    *,
    override_file: Path | None = None,
) -> CapabilityResolution:
    """解析某个技能在当前 Registry 中的执行能力。"""
    return registry.resolve(
        load_tool_requirements(skill_dir, override_file=override_file).requirements
    )
