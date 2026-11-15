"""Task application service: project/task lifecycle over the execution kernel."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from agent.application.dto import TaskBundle, TaskRunResult
from agent.config.settings import Settings
from agent.core.orchestrator import AgentOrchestrator
from agent.core.state_machine import TaskStateMachine
from agent.models.approval import ApprovalRequest
from agent.models.artifact import ArtifactRecord
from agent.models.base import utcnow
from agent.models.enums import ApprovalStatus, EvidenceKind, EvidenceStatus, StepStatus, TaskStatus
from agent.models.evidence import Evidence, ResultRef, SourceRef
from agent.models.execution import HumanSubmission
from agent.models.plan import AuditPlan
from agent.models.project import AuditProject
from agent.models.result import ToolResult
from agent.models.task import AuditTask
from agent.models.tool import ToolInvocation
from agent.output.workpaper import WorkpaperWriter
from agent.planning.planner import AuditPlanner
from agent.security.permissions import PermissionPolicy
from agent.security.workspace import SecurityError, Workspace, sha256_file
from agent.skills.router import SkillRouter
from agent.storage.database import Database
from agent.storage.repository import AuditRepository
from agent.tools.executor import ToolExecutor
from agent.tools.registry import ToolRegistry


class TaskApplicationError(RuntimeError):
    """The requested application action cannot be completed safely."""


class RouteConfirmationRequired(TaskApplicationError):
    """The lexical router found multiple or weak skill candidates."""

    def __init__(self, candidates: list[str], reason: str) -> None:
        self.candidates = candidates
        self.reason = reason
        super().__init__(reason)


class TaskApplicationService:
    """Coordinates persistence, workspace, planning and orchestration.

    This is intentionally host-neutral. CLI, REST, DSH and EXE adapters should
    call this service rather than reproducing lifecycle logic.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        tool_registry: ToolRegistry,
        skill_router: SkillRouter,
        planner: AuditPlanner,
        repository: AuditRepository | None = None,
        workpaper_writer: WorkpaperWriter | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.tool_registry = tool_registry
        self.skill_router = skill_router
        self.planner = planner
        self.repository = repository or AuditRepository(database)
        self.workpaper_writer = workpaper_writer or WorkpaperWriter()

    # ---------- project lifecycle ----------

    def create_project(
        self,
        *,
        name: str,
        client_label: str = "",
        period: str = "",
        project_id: str | None = None,
        created_by: str = "user",
    ) -> AuditProject:
        pid = project_id or f"PRJ-{uuid4().hex[:12]}"
        project = AuditProject(
            project_id=pid,
            name=name,
            client_label=client_label,
            period=period,
            created_by=created_by,
        )
        self.settings.ensure_dirs()
        created = self.repository.create_project(project)
        self.repository.add_audit_event(
            task_id=None,
            event="PROJECT_CREATED",
            actor=created_by,
            object_type="project",
            object_id=pid,
        )
        return created

    def get_project(self, project_id: str) -> AuditProject:
        project = self.repository.get_project(project_id)
        if project is None:
            raise TaskApplicationError(f"项目不存在：{project_id}")
        return project

    # ---------- task creation ----------

    def create_task(
        self,
        *,
        project_id: str,
        user_request: str,
        skill_id: str | None = None,
        provided_inputs: set[str] | None = None,
        active_conditions: set[str] | None = None,
        input_files: Mapping[str, Path] | None = None,
        task_id: str | None = None,
        created_by: str = "user",
    ) -> TaskBundle:
        project = self.get_project(project_id)
        resolved_skill = skill_id or self._route_skill(user_request)
        tid = task_id or f"TASK-{uuid4().hex[:12]}"

        workspace = Workspace.create(self.settings.workspace_path, project.project_id, tid)
        task = AuditTask(
            task_id=tid,
            project_id=project.project_id,
            user_request=user_request,
            skill_id=resolved_skill,
            status=TaskStatus.CREATED,
            workspace=str(workspace.root),
            created_by=created_by,
            metadata={
                "active_conditions": sorted(active_conditions or ()),
                "provided_inputs": sorted(provided_inputs or ()),
            },
        )
        self.repository.save_task(task)
        self.repository.add_audit_event(
            task_id=tid,
            event="TASK_CREATED",
            actor=created_by,
            object_type="task",
            object_id=tid,
        )

        imported = self._import_inputs(task, workspace, input_files or {})
        available_inputs = set(provided_inputs or ()) | set(imported)
        plan = self.planner.build_plan(
            task_id=tid,
            skill_id=resolved_skill,
            provided_inputs=available_inputs,
            active_conditions=set(active_conditions or ()),
        )

        task.skill_version = plan.skill_version
        task.plan_id = plan.plan_id
        task.metadata = {
            **task.metadata,
            "provided_inputs": sorted(available_inputs),
            "input_artifacts": {key: str(path) for key, path in imported.items()},
        }
        task.updated_at = utcnow()
        self.repository.save_task(task)
        self.repository.save_plan(plan)
        self.repository.add_audit_event(
            task_id=tid,
            event="PLAN_CREATED",
            actor=created_by,
            object_type="plan",
            object_id=plan.plan_id,
            detail={"skill_id": plan.skill_id, "steps": len(plan.steps)},
        )
        return TaskBundle(project=project, task=task, plan=plan)

    def get_task(self, task_id: str) -> AuditTask:
        task = self.repository.get_task(task_id)
        if task is None:
            raise TaskApplicationError(f"任务不存在：{task_id}")
        return task

    def get_plan(self, task_id: str) -> AuditPlan:
        plan = self.repository.get_task_plan(task_id)
        if plan is None:
            raise TaskApplicationError(f"任务没有已保存计划：{task_id}")
        return plan

    def list_tasks(self, project_id: str | None = None) -> list[AuditTask]:
        return self.repository.list_tasks(project_id=project_id)

    # ---------- inputs and artifacts ----------

    def _import_inputs(
        self,
        task: AuditTask,
        workspace: Workspace,
        input_files: Mapping[str, Path],
    ) -> dict[str, Path]:
        imported: dict[str, Path] = {}
        for logical_key, source in input_files.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", logical_key):
                raise TaskApplicationError(f"输入键必须为小写下划线格式：{logical_key!r}")
            source_path = Path(source).expanduser().resolve()
            if not source_path.is_file():
                raise TaskApplicationError(f"输入文件不存在：{source_path}")
            safe_name = f"{logical_key}__{source_path.name}"
            record = workspace.register_raw_file(source_path, relative_name=safe_name)
            absolute = workspace.root / record.relative_path
            imported[logical_key] = absolute
            self.repository.save_artifact(
                ArtifactRecord(
                    artifact_id=f"ART-{uuid4().hex[:12]}",
                    task_id=task.task_id,
                    kind="SOURCE_FILE",
                    path=str(absolute),
                    sha256=record.sha256,
                    size_bytes=record.size,
                    metadata={
                        "logical_input": logical_key,
                        "relative_path": record.relative_path,
                    },
                )
            )
        return imported

    def task_inputs(self, task_id: str) -> dict[str, Path]:
        artifacts = self.repository.list_artifacts(task_id)
        return {
            str(item.metadata["logical_input"]): Path(item.path)
            for item in artifacts
            if item.kind == "SOURCE_FILE" and item.metadata.get("logical_input")
        }

    # ---------- execution and recovery ----------

    async def run_task(
        self,
        task_id: str,
        *,
        tool_call_provider,
        permission_policy: PermissionPolicy | None = None,
        human_submissions: Mapping[str, HumanSubmission] | None = None,
        replanner=None,
        max_replans: int = 1,
    ) -> TaskRunResult:
        task = self.get_task(task_id)
        plan = self.get_plan(task_id)
        workspace = self._validated_workspace(task)
        policy = permission_policy or PermissionPolicy(
            allowed_tools=set(self.tool_registry.list_names()),
            max_tool_calls=self.settings.max_tool_calls,
            max_steps=self.settings.max_steps,
        )
        submissions = dict(human_submissions or {})
        if not submissions:
            submissions = self.repository.approved_human_submissions(task_id)

        self._record_human_evidence(task, workspace, submissions.values())
        executor = ToolExecutor(
            self.tool_registry,
            audit_sink=self.repository.record_tool_invocation,
            result_sink=lambda invocation, tool_result: self._record_tool_evidence(
                task,
                workspace,
                invocation,
                tool_result,
            ),
        )
        state_machine = TaskStateMachine(event_sink=self.repository.record_state_change)
        orchestrator = AgentOrchestrator(
            state_machine=state_machine,
            tool_executor=executor,
        )
        result = await orchestrator.execute(
            task,
            plan,
            permission_policy=policy,
            tool_call_provider=tool_call_provider,
            workspace_root=workspace.root,
            human_submissions=submissions,
            replanner=replanner,
            max_replans=max_replans,
        )

        final_plan = result.final_plan
        self.repository.save_task(task)
        self.repository.save_plan(final_plan)
        self._ensure_human_approvals(task, final_plan)
        pending = self.repository.list_approvals(
            task_id=task_id,
            status=ApprovalStatus.PENDING,
        )
        self.repository.add_audit_event(
            task_id=task_id,
            event=f"TASK_{task.status.value}",
            object_type="task",
            object_id=task_id,
            detail={"message": result.message, "replans": result.replans},
        )
        return TaskRunResult(
            task=task,
            plan=final_plan,
            result=result,
            pending_approvals=pending,
        )

    def _record_tool_evidence(
        self,
        task: AuditTask,
        workspace: Workspace,
        invocation: ToolInvocation,
        result: ToolResult,
    ) -> None:
        if not invocation.procedure_id:
            return
        source_path = self._first_existing_argument_file(invocation.arguments, workspace)
        source_sha = sha256_file(source_path) if source_path else None
        result_path = self._first_existing_evidence_file(result.evidence_files, workspace)
        result_sha = sha256_file(result_path) if result_path else None
        output = ResultRef(
            file=str(result_path) if result_path else None,
            sha256=result_sha,
            inline=None if result_path else result.result,
        )
        source = (
            SourceRef(file=str(source_path), sha256=source_sha)
            if source_path and source_sha
            else None
        )
        self.repository.save_evidence(
            Evidence(
                evidence_id=f"EVD-{uuid4().hex[:12]}",
                task_id=task.task_id,
                procedure_id=invocation.procedure_id,
                kind=EvidenceKind.TOOL_OUTPUT,
                status=EvidenceStatus.UNVERIFIED,
                source_file=str(source_path) if source_path else None,
                source_sha256=source_sha,
                tool_name=invocation.tool_name,
                tool_arguments=invocation.arguments,
                result_file=str(result_path) if result_path else None,
                result_sha256=result_sha,
                source=source,
                output=output,
                conclusion=result.error or ("工具执行成功" if result.success else "工具执行失败"),
                requires_human_review=result.requires_human_review,
            )
        )

    def _record_human_evidence(
        self,
        task: AuditTask,
        workspace: Workspace,
        submissions,
    ) -> None:
        for submission in submissions:
            for raw_path in submission.evidence_files:
                try:
                    path = workspace.resolve_inside(raw_path)
                except SecurityError as exc:
                    raise TaskApplicationError(f"人工证据路径越界：{raw_path}") from exc
                if not path.is_file():
                    raise TaskApplicationError(f"人工证据文件不存在：{path}")
                digest = sha256_file(path)
                if self.repository.evidence_exists(
                    task_id=task.task_id,
                    procedure_id=submission.step_id,
                    kind=EvidenceKind.HUMAN_ATTACHMENT,
                    source_sha256=digest,
                    tool_name="human_review",
                ):
                    continue
                self.repository.save_evidence(
                    Evidence(
                        evidence_id=f"EVD-{uuid4().hex[:12]}",
                        task_id=task.task_id,
                        procedure_id=submission.step_id,
                        kind=EvidenceKind.HUMAN_ATTACHMENT,
                        status=EvidenceStatus.UNVERIFIED,
                        source_file=str(path),
                        source_sha256=digest,
                        tool_name="human_review",
                        tool_arguments={"actor": submission.actor},
                        result_file=str(path),
                        result_sha256=digest,
                        source=SourceRef(file=str(path), sha256=digest),
                        output=ResultRef(file=str(path), sha256=digest),
                        conclusion=submission.comment or "人工提交证据",
                        requires_human_review=False,
                        reviewed_by=submission.actor,
                    )
                )

    @staticmethod
    def _first_existing_argument_file(arguments, workspace: Workspace) -> Path | None:
        for value in TaskApplicationService._walk_values(arguments):
            if not isinstance(value, str) or not value.strip():
                continue
            candidate = Path(value)
            if not candidate.suffix:
                continue
            try:
                resolved = workspace.resolve_inside(candidate)
            except SecurityError:
                continue
            if resolved.is_file():
                return resolved
        return None

    @staticmethod
    def _first_existing_evidence_file(paths: list[str], workspace: Workspace) -> Path | None:
        for value in paths:
            try:
                resolved = workspace.resolve_inside(value)
            except SecurityError:
                continue
            if resolved.is_file():
                return resolved
        return None

    @staticmethod
    def _walk_values(value):
        if isinstance(value, dict):
            for child in value.values():
                yield from TaskApplicationService._walk_values(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                yield from TaskApplicationService._walk_values(child)
        else:
            yield value

    def export_workpaper(
        self,
        task_id: str,
        *,
        prepared_by: str = "AuditOx Runtime",
        reviewer: str = "",
    ) -> ArtifactRecord:
        task = self.get_task(task_id)
        plan = self.get_plan(task_id)
        if plan.skill_id != "z-1-2-bank-deposits":
            raise TaskApplicationError(
                f"当前只实现了银行存款底稿生成器，收到技能：{plan.skill_id}"
            )
        workspace = self._validated_workspace(task)
        project = self.get_project(task.project_id)
        artifact = self.workpaper_writer.write_bank_deposits(
            workspace=workspace,
            project=project,
            task=task,
            plan=plan,
            evidence=self.repository.list_evidence(task_id),
            prepared_by=prepared_by,
            reviewer=reviewer,
        )
        self.repository.save_artifact(artifact)
        self.repository.add_audit_event(
            task_id=task_id,
            event="WORKPAPER_EXPORTED",
            actor=prepared_by,
            object_type="artifact",
            object_id=artifact.artifact_id,
            detail={"path": artifact.path, "sha256": artifact.sha256},
        )
        return artifact

    def submit_human_review(
        self,
        approval_id: str,
        *,
        approved: bool,
        actor: str,
        comment: str = "",
        attachments: list[str] | None = None,
    ) -> ApprovalRequest:
        return self.repository.decide_approval(
            approval_id,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            actor=actor,
            comment=comment,
            attachments=attachments or [],
        )

    def list_pending_approvals(self, task_id: str | None = None) -> list[ApprovalRequest]:
        return self.repository.list_approvals(task_id=task_id, status=ApprovalStatus.PENDING)

    def _ensure_human_approvals(self, task: AuditTask, plan: AuditPlan) -> None:
        if task.status is not TaskStatus.WAITING_HUMAN:
            return
        for step in plan.steps:
            if step.status is not StepStatus.WAITING_HUMAN:
                continue
            self.repository.ensure_pending_approval(
                task_id=task.task_id,
                procedure_id=step.step_id,
                reason=step.notes or f"步骤 {step.step_id} 需要人工处理",
                requested_action=f"请完成程序 {step.step_id}「{step.name}」并提交结论或证据",
            )

    def _validated_workspace(self, task: AuditTask) -> Workspace:
        path = Path(task.workspace).resolve()
        root = self.settings.workspace_path.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise TaskApplicationError(f"任务工作区越界：{path}") from exc
        return Workspace(path)

    def _route_skill(self, user_request: str) -> str:
        decision = self.skill_router.route(user_request)
        if decision.needs_confirmation or decision.skill_id is None:
            candidates = [item.skill_id for item in decision.candidates]
            raise RouteConfirmationRequired(candidates, decision.reason)
        return decision.skill_id


__all__ = [
    "RouteConfirmationRequired",
    "TaskApplicationError",
    "TaskApplicationService",
]
