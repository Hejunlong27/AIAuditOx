"""Validate merged DSL, SKILL.md and runtime procedure configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agent.models.enums import ConflictSeverity
from agent.models.procedure import ConflictRecord, ProcedureDefinition
from agent.planning.dag import DagError, topological_layers
from agent.planning.schema import ProcedureConfig
from agent.skills.loader import LoadedSkill, SkillLoader


class SkillValidationError(ValueError):
    """A skill cannot be planned safely until configuration conflicts are fixed."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("技能计划配置校验失败：\n- " + "\n- ".join(errors))


@dataclass
class SkillValidationResult:
    skill_id: str
    skill_version: str
    procedures: dict[str, ProcedureDefinition]
    conflicts: list[ConflictRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SkillValidator:
    """Build a validated, three-source procedure dictionary."""

    def __init__(
        self,
        loader: SkillLoader,
        *,
        available_tools: set[str] | None = None,
    ) -> None:
        self.loader = loader
        self.available_tools = available_tools

    @staticmethod
    def load_config(path: Path) -> ProcedureConfig:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SkillValidationError(["YAML 根节点必须是对象"])
        return ProcedureConfig.model_validate(raw)

    def validate(self, skill_id: str, config_path: Path) -> SkillValidationResult:
        config = self.load_config(config_path)
        loaded = self.loader.load_skill(skill_id)
        errors: list[str] = []
        conflicts: list[ConflictRecord] = []

        if config.skill_id != skill_id:
            errors.append(f"配置 skill_id={config.skill_id!r} 与请求 {skill_id!r} 不一致")

        merged = {procedure.id: procedure for procedure in loaded.procedures}
        config_ids = set(config.procedures)
        merged_ids = set(merged)
        if config_ids != merged_ids:
            missing = sorted(merged_ids - config_ids)
            extra = sorted(config_ids - merged_ids)
            if missing:
                errors.append(f"配置缺少程序：{', '.join(missing)}")
            if extra:
                errors.append(f"配置包含技能中不存在的程序：{', '.join(extra)}")

        mandatory_ids = {
            procedure.id
            for procedure in merged.values()
            if procedure.mandatory or procedure.execution_policy.mandatory
        }
        missing_mandatory = sorted(mandatory_ids - config_ids)
        if missing_mandatory:
            errors.append(f"强制程序未在 runtime config 中声明：{', '.join(missing_mandatory)}")

        configured: dict[str, ProcedureDefinition] = {}
        for procedure_id in sorted(merged_ids & config_ids):
            procedure = merged[procedure_id]
            runtime = config.procedures[procedure_id]
            if sorted(runtime.tools) != sorted(procedure.tools):
                conflicts.append(
                    ConflictRecord(
                        skill_id=skill_id,
                        procedure_id=procedure_id,
                        field="tools",
                        values={
                            "runtime_config": ", ".join(runtime.tools),
                            "merged_skill": ", ".join(procedure.tools),
                        },
                        resolved="阻断；以 DSL/SKILL.md 和 runtime config 对齐后再执行",
                        severity=ConflictSeverity.BLOCKING,
                    )
                )
                errors.append(f"{procedure_id} 的工具声明在 runtime config 与技能层不一致")
            configured[procedure_id] = procedure.model_copy(
                update={
                    "dependencies": list(runtime.depends_on),
                    "required_inputs": list(runtime.required_inputs),
                    "enabled_when": runtime.enabled_when,
                    "conditional": runtime.enabled_when is not None,
                    "sources": {
                        **procedure.sources,
                        "dependencies": "runtime_config",
                        "required_inputs": "runtime_config",
                        "enabled_when": "runtime_config",
                    },
                }
            )

        if self.available_tools is not None:
            declared_tools = {tool for item in configured.values() for tool in item.tools}
            missing_tools = sorted(declared_tools - self.available_tools)
            if missing_tools:
                errors.append(f"工具注册表缺少：{', '.join(missing_tools)}")

        try:
            topological_layers(
                {pid: item.dependencies for pid, item in configured.items()}
            )
        except DagError as exc:
            errors.append(str(exc))

        warnings = list(loaded.missing_procedure_docs)
        if warnings:
            warnings = [f"{skill_id}: 缺程序卡文档 {item}" for item in warnings]

        if errors:
            raise SkillValidationError(errors)
        return SkillValidationResult(
            skill_id=skill_id,
            skill_version=loaded.entry.version,
            procedures=configured,
            conflicts=conflicts,
            warnings=warnings,
        )
