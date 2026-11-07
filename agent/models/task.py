"""任务模型（PART 5.1）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from agent.models.base import AuditModel, utcnow
from agent.models.enums import TaskStatus


class AuditTask(AuditModel):
    """一次审计任务的完整状态快照。

    ``workspace`` 必须是绝对路径且位于受控根目录下（由
    :class:`agent.security.workspace.Workspace` 在实际创建时校验），
    模型层只做非空与字符串规范化，避免校验逻辑分散两处。
    """

    task_id: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)
    user_request: str = Field(min_length=1)
    skill_id: str | None = None
    skill_version: str | None = None
    status: TaskStatus = TaskStatus.CREATED
    workspace: str = Field(min_length=1)
    plan_id: str | None = None
    created_by: str = Field(default="system", max_length=128)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("时间戳必须带时区（UTC）")
        return value

    @field_validator("task_id", "project_id")
    @classmethod
    def _no_path_separator(cls, value: str) -> str:
        # ID 会参与目录名拼接，出现分隔符即等于路径穿越
        for bad in ("/", "\\", "..", "\x00"):
            if bad in value:
                raise ValueError(f"标识符不得包含 {bad!r}：{value!r}")
        return value
