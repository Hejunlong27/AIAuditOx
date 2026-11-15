"""Persisted audit project metadata."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from agent.models.base import AuditModel, utcnow


class AuditProject(AuditModel):
    """One local audit project represented by a stable folder identity."""

    project_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    client_label: str = Field(default="", max_length=255)
    period: str = Field(default="", max_length=64)
    created_by: str = Field(default="system", max_length=128)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("project_id")
    @classmethod
    def _safe_project_id(cls, value: str) -> str:
        for bad in ("/", "\\", "..", "\x00", ":"):
            if bad in value:
                raise ValueError(f"项目 ID 不得包含 {bad!r}")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("时间戳必须带时区")
        return value


__all__ = ["AuditProject"]
