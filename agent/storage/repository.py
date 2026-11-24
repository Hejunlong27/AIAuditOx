"""Persistence adapters for tasks, plans, approvals, evidence and artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from agent.models.approval import ApprovalRequest
from agent.models.artifact import ArtifactRecord
from agent.models.enums import ApprovalStatus, StepStatus, TaskStatus
from agent.models.evidence import Evidence
from agent.models.execution import HumanSubmission, StateChange
from agent.models.plan import AuditPlan, PlanStep
from agent.models.project import AuditProject
from agent.models.task import AuditTask
from agent.models.tool import ToolInvocation
from agent.storage.database import Database
from agent.storage.orm import (
    ApprovalRow,
    ArtifactRow,
    AuditEventRow,
    EvidenceRow,
    PlanRow,
    PlanStepRow,
    ProjectRow,
    TaskRow,
    ToolRunRow,
)


class RepositoryError(RuntimeError):
    """A persisted object is missing, conflicting, or malformed."""


class AuditRepository:
    """SQLAlchemy-backed persistence facade used by the application layer."""

    def __init__(self, database: Database) -> None:
        self.database = database

    # ---------- projects ----------

    def create_project(self, project: AuditProject) -> AuditProject:
        with self.database.session() as session:
            if session.get(ProjectRow, project.project_id) is not None:
                raise RepositoryError(f"项目已存在：{project.project_id}")
            session.add(
                ProjectRow(
                    project_id=project.project_id,
                    name=project.name,
                    client_label=project.client_label,
                    period=project.period,
                    created_by=project.created_by,
                    created_at=_iso(project.created_at),
                    updated_at=_iso(project.updated_at),
                    version=1,
                )
            )
        return project

    def get_project(self, project_id: str) -> AuditProject | None:
        with self.database.session() as session:
            row = session.get(ProjectRow, project_id)
            return _project_from_row(row) if row else None

    def list_projects(self) -> list[AuditProject]:
        with self.database.session() as session:
            rows = session.scalars(select(ProjectRow).order_by(ProjectRow.updated_at.desc())).all()
            return [_project_from_row(row) for row in rows]

    # ---------- tasks ----------

    def save_task(self, task: AuditTask) -> AuditTask:
        with self.database.session() as session:
            row = session.get(TaskRow, task.task_id)
            if row is None:
                row = TaskRow(
                    task_id=task.task_id,
                    project_id=task.project_id,
                    user_request=task.user_request,
                    status=task.status.value,
                    workspace=task.workspace,
                    created_at=_iso(task.created_at),
                    updated_at=_iso(task.updated_at),
                )
                session.add(row)
            else:
                row.project_id = task.project_id
                row.user_request = task.user_request
                row.status = task.status.value
                row.workspace = task.workspace
                row.updated_at = _iso(task.updated_at)
                row.version = (row.version or 1) + 1
            row.skill_id = task.skill_id
            row.skill_version = task.skill_version
            row.plan_id = task.plan_id
            row.created_by = task.created_by
            row.meta_json = json.dumps(task.metadata, ensure_ascii=False, default=str)
        return task

    def get_task(self, task_id: str) -> AuditTask | None:
        with self.database.session() as session:
            row = session.get(TaskRow, task_id)
            return _task_from_row(row) if row else None

    def list_tasks(self, *, project_id: str | None = None) -> list[AuditTask]:
        with self.database.session() as session:
            stmt = select(TaskRow)
            if project_id:
                stmt = stmt.where(TaskRow.project_id == project_id)
            rows = session.scalars(stmt.order_by(TaskRow.updated_at.desc())).all()
            return [_task_from_row(row) for row in rows]

    # ---------- plans ----------

    def save_plan(self, plan: AuditPlan) -> AuditPlan:
        now = _iso(plan.created_at)
        with self.database.session() as session:
            row = session.get(PlanRow, plan.plan_id)
            if row is None:
                row = PlanRow(
                    plan_id=plan.plan_id,
                    task_id=plan.task_id,
                    skill_id=plan.skill_id,
                    skill_version=plan.skill_version,
                    payload_json=plan.model_dump_json(),
                    execution_order_json=json.dumps(plan.execution_order, ensure_ascii=False),
                    validated=1 if plan.validated else 0,
                    created_at=now,
                )
                session.add(row)
            else:
                row.task_id = plan.task_id
                row.skill_id = plan.skill_id
                row.skill_version = plan.skill_version
                row.payload_json = plan.model_dump_json()
                row.execution_order_json = json.dumps(plan.execution_order, ensure_ascii=False)
                row.validated = 1 if plan.validated else 0
                row.version = (row.version or 1) + 1

            existing = {
                step.step_id: step
                for step in session.scalars(
                    select(PlanStepRow).where(PlanStepRow.task_id == plan.task_id)
                ).all()
            }
            wanted = {step.step_id for step in plan.steps}
            for step_id, step_row in existing.items():
                if step_id not in wanted:
                    session.delete(step_row)

            for step in plan.steps:
                step_row = existing.get(step.step_id)
                payload = step.model_dump_json()
                if step_row is None:
                    step_row = PlanStepRow(
                        task_id=plan.task_id,
                        plan_id=plan.plan_id,
                        step_id=step.step_id,
                        procedure_id=step.procedure_id,
                        name=step.name,
                        status=step.status.value,
                        human_required=1 if step.human_required else 0,
                        mandatory=1 if step.mandatory else 0,
                        retry_count=step.retry_count,
                        dependencies_json=json.dumps(step.dependencies, ensure_ascii=False),
                        payload_json=payload,
                        updated_at=now,
                    )
                    session.add(step_row)
                else:
                    step_row.plan_id = plan.plan_id
                    step_row.procedure_id = step.procedure_id
                    step_row.name = step.name
                    step_row.status = step.status.value
                    step_row.human_required = 1 if step.human_required else 0
                    step_row.mandatory = 1 if step.mandatory else 0
                    step_row.retry_count = step.retry_count
                    step_row.dependencies_json = json.dumps(step.dependencies, ensure_ascii=False)
                    step_row.payload_json = payload
                    step_row.updated_at = now
                    step_row.version = (step_row.version or 1) + 1
        return plan

    def get_plan(self, plan_id: str) -> AuditPlan | None:
        with self.database.session() as session:
            row = session.get(PlanRow, plan_id)
            if row is None:
                return None
            return self._plan_from_rows(session, row)

    def get_task_plan(self, task_id: str) -> AuditPlan | None:
        with self.database.session() as session:
            row = session.scalars(
                select(PlanRow)
                .where(PlanRow.task_id == task_id)
                .order_by(PlanRow.created_at.desc())
            ).first()
            if row is None:
                return None
            return self._plan_from_rows(session, row)

    def _plan_from_rows(self, session, row: PlanRow) -> AuditPlan:
        plan = AuditPlan.model_validate_json(row.payload_json)
        step_rows = {
            step.step_id: step
            for step in session.scalars(
                select(PlanStepRow).where(
                    PlanStepRow.task_id == row.task_id,
                    PlanStepRow.plan_id == row.plan_id,
                )
            ).all()
        }
        if step_rows:
            overlaid: list[PlanStep] = []
            for step in plan.steps:
                step_row = step_rows.get(step.step_id)
                if step_row is None:
                    overlaid.append(step)
                    continue
                try:
                    stored = PlanStep.model_validate_json(step_row.payload_json)
                    stored = stored.model_copy(
                        update={
                            "status": StepStatus(step_row.status),
                            "retry_count": step_row.retry_count,
                        }
                    )
                    overlaid.append(stored)
                except Exception:
                    overlaid.append(step.model_copy(update={"status": StepStatus(step_row.status)}))
            plan.steps = overlaid
        return plan

    # ---------- state, runs and events ----------

    def record_state_change(self, change: StateChange) -> None:
        with self.database.session() as session:
            if change.object_type == "task":
                task_row = session.get(TaskRow, change.task_id)
                if task_row is None:
                    raise RepositoryError(f"任务不存在：{change.task_id}")
                task_row.status = change.to_status
                task_row.updated_at = _iso(change.created_at)
                task_row.version = (task_row.version or 1) + 1
            else:
                step_row = session.scalars(
                    select(PlanStepRow).where(
                        PlanStepRow.task_id == change.task_id,
                        PlanStepRow.step_id == change.object_id,
                    )
                ).first()
                if step_row is None:
                    raise RepositoryError(f"步骤不存在：{change.task_id}/{change.object_id}")
                step_row.status = change.to_status
                step_row.updated_at = _iso(change.created_at)
                step_row.version = (step_row.version or 1) + 1
            session.add(
                AuditEventRow(
                    task_id=change.task_id,
                    event=f"{change.object_type.upper()}_STATE_CHANGED",
                    actor=change.actor,
                    object_type=change.object_type,
                    object_id=change.object_id,
                    from_status=change.from_status,
                    to_status=change.to_status,
                    detail_json=json.dumps({"reason": change.reason}, ensure_ascii=False),
                    created_at=_iso(change.created_at),
                )
            )

    def record_tool_invocation(self, invocation: ToolInvocation) -> None:
        with self.database.session() as session:
            row = session.get(ToolRunRow, invocation.execution_id)
            if row is None:
                row = ToolRunRow(
                    execution_id=invocation.execution_id,
                    task_id=invocation.task_id,
                    procedure_id=invocation.procedure_id,
                    tool_name=invocation.tool_name,
                    arguments_json=json.dumps(invocation.arguments, ensure_ascii=False, default=str),
                    result_json=json.dumps(
                        {"source_files": invocation.source_files},
                        ensure_ascii=False,
                    ),
                    success=1 if invocation.success else 0,
                    error=invocation.error,
                    duration_ms=invocation.duration_ms,
                    created_at=invocation.created_at_ts or _iso(datetime.now().astimezone()),
                )
                session.add(row)
            else:
                row.success = 1 if invocation.success else 0
                row.error = invocation.error
                row.duration_ms = invocation.duration_ms
                row.arguments_json = json.dumps(invocation.arguments, ensure_ascii=False, default=str)
                row.result_json = json.dumps(
                    {"source_files": invocation.source_files},
                    ensure_ascii=False,
                )

    def add_audit_event(
        self,
        *,
        task_id: str | None,
        event: str,
        actor: str = "system",
        object_type: str = "",
        object_id: str = "",
        detail: dict | None = None,
    ) -> None:
        with self.database.session() as session:
            session.add(
                AuditEventRow(
                    task_id=task_id,
                    event=event,
                    actor=actor,
                    object_type=object_type,
                    object_id=object_id,
                    detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
                    created_at=_iso(datetime.now().astimezone()),
                )
            )

    def list_audit_events(self, task_id: str) -> list[dict]:
        with self.database.session() as session:
            rows = session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.task_id == task_id)
                .order_by(AuditEventRow.id)
            ).all()
            return [
                {
                    "event": row.event,
                    "actor": row.actor,
                    "object_type": row.object_type,
                    "object_id": row.object_id,
                    "from_status": row.from_status,
                    "to_status": row.to_status,
                    "detail": json.loads(row.detail_json or "{}"),
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    # ---------- approvals ----------

    def ensure_pending_approval(
        self,
        *,
        task_id: str,
        procedure_id: str,
        reason: str,
        requested_action: str,
    ) -> ApprovalRequest:
        with self.database.session() as session:
            existing = session.scalars(
                select(ApprovalRow)
                .where(
                    ApprovalRow.task_id == task_id,
                    ApprovalRow.procedure_id == procedure_id,
                    ApprovalRow.status.in_(
                        [ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value]
                    ),
                )
                .order_by(ApprovalRow.updated_at.desc())
            ).first()
            if existing:
                return _approval_from_row(existing)
            now = _iso(datetime.now().astimezone())
            row = ApprovalRow(
                approval_id=f"APR-{uuid4().hex[:12]}",
                task_id=task_id,
                procedure_id=procedure_id,
                reason=reason,
                requested_action=requested_action,
                status=ApprovalStatus.PENDING.value,
                comment="",
                evidence_ids_json="[]",
                attachments_json="[]",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return _approval_from_row(row)

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        with self.database.session() as session:
            row = session.get(ApprovalRow, approval_id)
            return _approval_from_row(row) if row else None

    def list_approvals(
        self,
        *,
        task_id: str | None = None,
        status: ApprovalStatus | None = None,
    ) -> list[ApprovalRequest]:
        with self.database.session() as session:
            stmt = select(ApprovalRow)
            if task_id:
                stmt = stmt.where(ApprovalRow.task_id == task_id)
            if status:
                stmt = stmt.where(ApprovalRow.status == status.value)
            rows = session.scalars(stmt.order_by(ApprovalRow.updated_at.desc())).all()
            return [_approval_from_row(row) for row in rows]

    def decide_approval(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        actor: str,
        comment: str = "",
        attachments: list[str] | None = None,
        evidence_ids: list[str] | None = None,
    ) -> ApprovalRequest:
        if status not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED):
            raise RepositoryError("人工审批只能设置为 APPROVED / REJECTED / EXPIRED")
        with self.database.session() as session:
            row = session.get(ApprovalRow, approval_id)
            if row is None:
                raise RepositoryError(f"审批单不存在：{approval_id}")
            row.status = status.value
            row.approved_by = actor
            row.comment = comment
            row.attachments_json = json.dumps(attachments or [], ensure_ascii=False)
            row.evidence_ids_json = json.dumps(evidence_ids or [], ensure_ascii=False)
            row.updated_at = _iso(datetime.now().astimezone())
            row.version = (row.version or 1) + 1
            session.flush()
            result = _approval_from_row(row)
            session.add(
                AuditEventRow(
                    task_id=row.task_id,
                    event="APPROVAL_DECIDED",
                    actor=actor,
                    object_type="approval",
                    object_id=approval_id,
                    from_status=ApprovalStatus.PENDING.value,
                    to_status=status.value,
                    detail_json=json.dumps({"comment": comment}, ensure_ascii=False),
                    created_at=row.updated_at,
                )
            )
            return result

    def approved_human_submissions(self, task_id: str) -> dict[str, HumanSubmission]:
        with self.database.session() as session:
            rows = session.scalars(
                select(ApprovalRow)
                .where(
                    ApprovalRow.task_id == task_id,
                    ApprovalRow.status == ApprovalStatus.APPROVED.value,
                )
                .order_by(ApprovalRow.updated_at.desc())
            ).all()
            result: dict[str, HumanSubmission] = {}
            for row in rows:
                if row.procedure_id in result:
                    continue
                attachments = json.loads(row.attachments_json or "[]")
                result[row.procedure_id] = HumanSubmission(
                    step_id=row.procedure_id,
                    actor=row.approved_by or "reviewer",
                    comment=row.comment or "人工审批通过",
                    evidence_files=attachments,
                )
            return result

    # ---------- evidence ----------

    def save_evidence(self, evidence: Evidence) -> Evidence:
        with self.database.session() as session:
            row = session.get(EvidenceRow, evidence.evidence_id)
            if row is None:
                row = EvidenceRow(
                    evidence_id=evidence.evidence_id,
                    task_id=evidence.task_id,
                    procedure_id=evidence.procedure_id,
                    kind=evidence.kind.value,
                    status=evidence.status.value,
                    source_file=evidence.source_file,
                    source_sha256=evidence.source_sha256,
                    tool_name=evidence.tool_name,
                    tool_arguments_json=json.dumps(evidence.tool_arguments, ensure_ascii=False, default=str),
                    result_file=evidence.result_file,
                    result_sha256=evidence.result_sha256,
                    conclusion=evidence.conclusion,
                    requires_human_review=1 if evidence.requires_human_review else 0,
                    reviewed_by=evidence.reviewed_by,
                    reviewed_at=_iso(evidence.reviewed_at) if evidence.reviewed_at else None,
                    payload_json=evidence.model_dump_json(),
                    created_at=_iso(evidence.created_at),
                )
                session.add(row)
            else:
                row.kind = evidence.kind.value
                row.status = evidence.status.value
                row.source_file = evidence.source_file
                row.source_sha256 = evidence.source_sha256
                row.tool_name = evidence.tool_name
                row.tool_arguments_json = json.dumps(evidence.tool_arguments, ensure_ascii=False, default=str)
                row.result_file = evidence.result_file
                row.result_sha256 = evidence.result_sha256
                row.conclusion = evidence.conclusion
                row.requires_human_review = 1 if evidence.requires_human_review else 0
                row.reviewed_by = evidence.reviewed_by
                row.reviewed_at = _iso(evidence.reviewed_at) if evidence.reviewed_at else None
                row.payload_json = evidence.model_dump_json()
        return evidence

    def evidence_exists(
        self,
        *,
        task_id: str,
        procedure_id: str,
        kind,
        source_sha256: str,
        tool_name: str,
    ) -> bool:
        with self.database.session() as session:
            row = session.scalars(
                select(EvidenceRow).where(
                    EvidenceRow.task_id == task_id,
                    EvidenceRow.procedure_id == procedure_id,
                    EvidenceRow.kind == kind.value,
                    EvidenceRow.source_sha256 == source_sha256,
                    EvidenceRow.tool_name == tool_name,
                )
            ).first()
            return row is not None

    def list_evidence(self, task_id: str) -> list[Evidence]:
        with self.database.session() as session:
            rows = session.scalars(
                select(EvidenceRow)
                .where(EvidenceRow.task_id == task_id)
                .order_by(EvidenceRow.created_at)
            ).all()
            return [_evidence_from_row(row) for row in rows]

    # ---------- artifacts ----------

    def save_artifact(self, artifact: ArtifactRecord) -> ArtifactRecord:
        with self.database.session() as session:
            row = session.get(ArtifactRow, artifact.artifact_id)
            if row is None:
                row = ArtifactRow(
                    artifact_id=artifact.artifact_id,
                    task_id=artifact.task_id,
                    kind=artifact.kind,
                    path=artifact.path,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                    template_version=artifact.template_version,
                    meta_json=json.dumps(artifact.metadata, ensure_ascii=False, default=str),
                    created_at=_iso(artifact.created_at),
                )
                session.add(row)
            else:
                row.kind = artifact.kind
                row.path = artifact.path
                row.sha256 = artifact.sha256
                row.size_bytes = artifact.size_bytes
                row.template_version = artifact.template_version
                row.meta_json = json.dumps(artifact.metadata, ensure_ascii=False, default=str)
        return artifact

    def list_artifacts(self, task_id: str) -> list[ArtifactRecord]:
        with self.database.session() as session:
            rows = session.scalars(
                select(ArtifactRow)
                .where(ArtifactRow.task_id == task_id)
                .order_by(ArtifactRow.created_at)
            ).all()
            return [_artifact_from_row(row) for row in rows]


def _iso(value: datetime) -> str:
    return value.isoformat()


def _project_from_row(row: ProjectRow) -> AuditProject:
    return AuditProject(
        project_id=row.project_id,
        name=row.name,
        client_label=row.client_label,
        period=row.period,
        created_by=row.created_by,
        created_at=datetime.fromisoformat(row.created_at),
        updated_at=datetime.fromisoformat(row.updated_at),
    )


def _task_from_row(row: TaskRow) -> AuditTask:
    return AuditTask(
        task_id=row.task_id,
        project_id=row.project_id,
        user_request=row.user_request,
        skill_id=row.skill_id,
        skill_version=row.skill_version,
        status=TaskStatus(row.status),
        workspace=row.workspace,
        plan_id=row.plan_id,
        created_by=row.created_by,
        created_at=datetime.fromisoformat(row.created_at),
        updated_at=datetime.fromisoformat(row.updated_at),
        metadata=json.loads(row.meta_json or "{}"),
    )


def _approval_from_row(row: ApprovalRow) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=row.approval_id,
        task_id=row.task_id,
        procedure_id=row.procedure_id,
        reason=row.reason,
        requested_action=row.requested_action,
        status=ApprovalStatus(row.status),
        approved_by=row.approved_by,
        comment=row.comment,
        evidence_ids=json.loads(row.evidence_ids_json or "[]"),
        attachments=json.loads(row.attachments_json or "[]"),
        created_at=datetime.fromisoformat(row.created_at),
        updated_at=datetime.fromisoformat(row.updated_at),
    )


def _evidence_from_row(row: EvidenceRow) -> Evidence:
    try:
        return Evidence.model_validate_json(row.payload_json)
    except Exception:
        from agent.models.enums import EvidenceKind, EvidenceStatus

        return Evidence(
            evidence_id=row.evidence_id,
            task_id=row.task_id,
            procedure_id=row.procedure_id,
            kind=EvidenceKind(row.kind),
            status=EvidenceStatus(row.status),
            source_file=row.source_file,
            source_sha256=row.source_sha256,
            tool_name=row.tool_name,
            tool_arguments=json.loads(row.tool_arguments_json or "{}"),
            result_file=row.result_file,
            result_sha256=row.result_sha256,
            conclusion=row.conclusion,
            requires_human_review=bool(row.requires_human_review),
            reviewed_by=row.reviewed_by,
            reviewed_at=datetime.fromisoformat(row.reviewed_at) if row.reviewed_at else None,
            created_at=datetime.fromisoformat(row.created_at),
        )


def _artifact_from_row(row: ArtifactRow) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=row.artifact_id,
        task_id=row.task_id,
        kind=row.kind,
        path=row.path,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        template_version=row.template_version,
        metadata=json.loads(row.meta_json or "{}"),
        created_at=datetime.fromisoformat(row.created_at),
    )


__all__ = ["AuditRepository", "RepositoryError"]
