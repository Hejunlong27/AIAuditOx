"""SQLAlchemy ORM 定义：9 张表（PART 16）。

设计要点：
- 金额列用 ``Numeric(20, 2)``，**不用 Float**；
- 时间列统一存 ISO8601 字符串（UTC），避免 SQLite 的 datetime 时区丢失；
- 每张业务表带 ``version`` 做乐观锁，防止并发覆盖（PART 6 第 10 条）；
- 大文件不存库，``artifacts`` 只存路径 + 哈希（PART 16 末条）。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """ORM 基类。"""


class ProjectRow(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_label: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    period: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    tasks: Mapped[list["TaskRow"]] = relationship(back_populates="project")


class TaskRow(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    skill_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    skill_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workspace: Mapped[str] = mapped_column(String(1024), nullable=False)
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    meta_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[ProjectRow] = relationship(back_populates="tasks")
    plans: Mapped[list["PlanRow"]] = relationship(back_populates="task")
    steps: Mapped[list["PlanStepRow"]] = relationship(back_populates="task")
    evidences: Mapped[list["EvidenceRow"]] = relationship(back_populates="task")
    approvals: Mapped[list["ApprovalRow"]] = relationship(back_populates="task")
    tool_runs: Mapped[list["ToolRunRow"]] = relationship(back_populates="task")
    artifacts: Mapped[list["ArtifactRow"]] = relationship(back_populates="task")
    events: Mapped[list["AuditEventRow"]] = relationship(back_populates="task")

    __table_args__ = (Index("ix_tasks_project_status", "project_id", "status"),)


class PlanRow(Base):
    __tablename__ = "plans"

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    execution_order_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    validated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    task: Mapped[TaskRow] = relationship(back_populates="plans")


class PlanStepRow(Base):
    __tablename__ = "plan_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    step_id: Mapped[str] = mapped_column(String(32), nullable=False)
    procedure_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    human_required: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mandatory: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dependencies_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    task: Mapped[TaskRow] = relationship(back_populates="steps")

    __table_args__ = (UniqueConstraint("task_id", "step_id", name="uq_plan_steps_task_step"),)


class ToolRunRow(Base):
    __tablename__ = "tool_runs"

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    procedure_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    arguments_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    task: Mapped[TaskRow] = relationship(back_populates="tool_runs")


class EvidenceRow(Base):
    __tablename__ = "evidences"

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    procedure_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="TOOL_OUTPUT", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="UNVERIFIED", nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_arguments_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conclusion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requires_human_review: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    task: Mapped[TaskRow] = relationship(back_populates="evidences")


class ApprovalRow(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    procedure_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    attachments_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    task: Mapped[TaskRow] = relationship(back_populates="approvals")


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    template_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    task: Mapped[TaskRow] = relationship(back_populates="artifacts")


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=True, index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), default="system", nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    task: Mapped[TaskRow | None] = relationship(back_populates="events")


__all__ = [
    "ApprovalRow",
    "ArtifactRow",
    "AuditEventRow",
    "Base",
    "EvidenceRow",
    "PlanRow",
    "PlanStepRow",
    "ProjectRow",
    "TaskRow",
    "ToolRunRow",
]
