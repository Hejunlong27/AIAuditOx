"""Runtime-only procedure planning configuration loaded from YAML."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from agent.models.base import AuditModel


PROCEDURE_ID_RE = re.compile(r"^[A-Z]\d{1,3}$")


class RuntimeProcedureConfig(AuditModel):
    """Dependencies and input requirements owned by the runtime layer."""

    depends_on: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    enabled_when: str | None = None

    @field_validator("depends_on")
    @classmethod
    def _valid_dependencies(cls, values: list[str]) -> list[str]:
        bad = [item for item in values if not PROCEDURE_ID_RE.fullmatch(item)]
        if bad:
            raise ValueError(f"非法依赖程序 ID：{bad}")
        if len(values) != len(set(values)):
            raise ValueError("depends_on 不能重复")
        return values


class ProcedureConfig(AuditModel):
    """A skill-specific planning configuration file."""

    schema_version: int = Field(default=1, ge=1)
    skill_id: str = Field(min_length=1)
    procedures: dict[str, RuntimeProcedureConfig] = Field(default_factory=dict)

    @field_validator("procedures")
    @classmethod
    def _valid_procedure_ids(
        cls,
        values: dict[str, RuntimeProcedureConfig],
    ) -> dict[str, RuntimeProcedureConfig]:
        bad = [item for item in values if not PROCEDURE_ID_RE.fullmatch(item)]
        if bad:
            raise ValueError(f"非法程序 ID：{bad}")
        return values
