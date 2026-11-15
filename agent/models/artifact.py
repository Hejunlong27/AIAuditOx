"""Persisted artifact metadata referenced by task evidence chains."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from agent.models.base import AuditModel, utcnow


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ArtifactRecord(AuditModel):
    """A file or inline output owned by one task.

    The artifact table stores paths and hashes only; customer files remain on
    disk inside the task workspace.
    """

    artifact_id: str = Field(min_length=1, max_length=64)
    task_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=1024)
    sha256: str
    size_bytes: int = Field(default=0, ge=0)
    template_version: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("sha256")
    @classmethod
    def _sha256_format(cls, value: str) -> str:
        value = value.strip().lower()
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 必须是 64 位小写十六进制")
        return value

    @field_validator("created_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("时间戳必须带时区")
        return value


__all__ = ["ArtifactRecord"]
