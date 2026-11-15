"""Typer CLI for the local AuditOx runtime."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from agent.application import JsonToolCallProvider, TaskApplicationService
from agent.config.settings import Settings
from agent.planning import AuditPlanner, SkillValidator
from agent.skills import SkillLoader, SkillRegistry
from agent.skills.router import SkillRouter
from agent.storage.database import Database
from agent.storage.repository import AuditRepository
from agent.tools import NodeToolBridge, ToolRegistry, register_node_core_tools


app = typer.Typer(
    name="auditox",
    help="审小牛 AuditOx 本地审计 Agent Runtime",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
project_app = typer.Typer(help="项目管理", no_args_is_help=True)
task_app = typer.Typer(help="审计任务", no_args_is_help=True)
approval_app = typer.Typer(help="人工审批", no_args_is_help=True)
workpaper_app = typer.Typer(help="底稿管理", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(task_app, name="task")
app.add_typer(approval_app, name="approval")
app.add_typer(workpaper_app, name="workpaper")


@dataclass(frozen=True)
class CliState:
    settings: Settings


@app.callback()
def root(
    ctx: typer.Context,
    repo_root: Path = typer.Option(
        Path(__file__).resolve().parents[1],
        "--repo-root",
        help="Agent Runtime 仓库根目录",
    ),
    data_root: Path | None = typer.Option(None, "--data-root", help="运行数据目录"),
    workspace_root: Path | None = typer.Option(None, "--workspace-root", help="任务工作区根目录"),
    database_url: str = typer.Option("", "--database-url", help="覆盖 SQLite/PostgreSQL URL"),
) -> None:
    settings = Settings(
        repo_root=repo_root.resolve(),
        data_root=data_root,
        workspace_root=workspace_root,
        database_url=database_url,
    )
    settings.ensure_dirs()
    ctx.obj = CliState(settings=settings)


def _emit(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _database(settings: Settings) -> Database:
    database = Database(settings.resolved_database_url)
    database.create_all()
    return database


def _sync_service(settings: Settings, tool_registry: ToolRegistry | None = None) -> TaskApplicationService:
    database = _database(settings)
    registry = tool_registry or ToolRegistry()
    skill_registry = SkillRegistry(settings.repo_root).load()
    loader = SkillLoader(settings.repo_root, skill_registry)
    validator = SkillValidator(
        loader,
        available_tools=set(registry.list_names()) if registry.list_names() else None,
    )
    planner = AuditPlanner(validator, config_root=settings.repo_root / "agent" / "config" / "procedures")
    return TaskApplicationService(
        settings=settings,
        database=database,
        tool_registry=registry,
        skill_router=SkillRouter(skill_registry),
        planner=planner,
    )


async def _async_service(settings: Settings):
    bridge = NodeToolBridge(settings.repo_root.parent)
    registry = ToolRegistry()
    try:
        await register_node_core_tools(registry, bridge)
        skill_registry = SkillRegistry(settings.repo_root).load()
        loader = SkillLoader(settings.repo_root, skill_registry)
        validator = SkillValidator(loader, available_tools=set(registry.list_names()))
        planner = AuditPlanner(
            validator,
            config_root=settings.repo_root / "agent" / "config" / "procedures",
        )
        database = _database(settings)
        service = TaskApplicationService(
            settings=settings,
            database=database,
            tool_registry=registry,
            skill_router=SkillRouter(skill_registry),
            planner=planner,
        )
        yield service
    finally:
        await bridge.close()


# ---------- project ----------

@project_app.command("create")
def project_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="项目名称"),
    client_label: str = typer.Option("", "--client", help="被审计单位"),
    period: str = typer.Option("", "--period", help="审计期间"),
    project_id: str | None = typer.Option(None, "--id", help="指定项目 ID"),
) -> None:
    service = _sync_service(ctx.obj.settings)
    _emit(
        service.create_project(
            name=name,
            client_label=client_label,
            period=period,
            project_id=project_id,
        )
    )


@project_app.command("list")
def project_list(ctx: typer.Context) -> None:
    repository = AuditRepository(_database(ctx.obj.settings))
    _emit([item.model_dump(mode="json") for item in repository.list_projects()])


# ---------- tasks ----------

@task_app.command("create")
def task_create(
    ctx: typer.Context,
    project_id: str = typer.Option(..., "--project", help="项目 ID"),
    request: str = typer.Option(..., "--request", help="审计请求"),
    skill_id: str | None = typer.Option(None, "--skill", help="显式技能 ID"),
    input_file: list[str] = typer.Option([], "--input", help="逻辑输入键=文件路径，可重复"),
    provided_input: list[str] = typer.Option([], "--provided", help="只声明已提供的输入键，可重复"),
    active_condition: list[str] = typer.Option([], "--condition", help="激活条件程序 ID，可重复"),
    task_id: str | None = typer.Option(None, "--id", help="指定任务 ID"),
) -> None:
    settings: Settings = ctx.obj.settings
    input_files: dict[str, Path] = {}
    for item in input_file:
        key, separator, raw_path = item.partition("=")
        if not separator or not key or not raw_path:
            raise typer.BadParameter("--input 必须是 逻辑键=文件路径")
        input_files[key] = Path(raw_path)

    async def action() -> None:
        async for service in _async_service(settings):
            bundle = service.create_task(
                project_id=project_id,
                user_request=request,
                skill_id=skill_id,
                provided_inputs=set(provided_input),
                active_conditions=set(active_condition),
                input_files=input_files,
                task_id=task_id,
            )
            _emit(bundle)

    asyncio.run(action())


@task_app.command("list")
def task_list(
    ctx: typer.Context,
    project_id: str | None = typer.Option(None, "--project", help="按项目筛选"),
) -> None:
    repository = AuditRepository(_database(ctx.obj.settings))
    _emit([item.model_dump(mode="json") for item in repository.list_tasks(project_id=project_id)])


@task_app.command("show")
def task_show(ctx: typer.Context, task_id: str = typer.Argument(...)) -> None:
    service = _sync_service(ctx.obj.settings)
    _emit({"task": service.get_task(task_id), "plan": service.get_plan(task_id)})


@task_app.command("run")
def task_run(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    calls_file: Path = typer.Option(..., "--calls-file", help="按程序提供工具调用的 JSON 文件"),
    max_replans: int = typer.Option(1, "--max-replans", min=0, max=5),
) -> None:
    settings: Settings = ctx.obj.settings
    provider = JsonToolCallProvider.from_file(calls_file)

    async def action() -> None:
        async for service in _async_service(settings):
            result = await service.run_task(
                task_id,
                tool_call_provider=provider,
                max_replans=max_replans,
            )
            _emit(result)

    asyncio.run(action())


# ---------- approvals ----------

@approval_app.command("list")
def approval_list(
    ctx: typer.Context,
    task_id: str | None = typer.Option(None, "--task", help="按任务筛选"),
) -> None:
    repository = AuditRepository(_database(ctx.obj.settings))
    _emit([item.model_dump(mode="json") for item in repository.list_approvals(task_id=task_id)])


@approval_app.command("approve")
def approval_approve(
    ctx: typer.Context,
    approval_id: str = typer.Argument(...),
    actor: str = typer.Option(..., "--actor"),
    comment: str = typer.Option("", "--comment"),
    attachment: list[str] = typer.Option([], "--attachment", help="证据文件路径，可重复"),
) -> None:
    repository = AuditRepository(_database(ctx.obj.settings))
    from agent.models.enums import ApprovalStatus

    _emit(
        repository.decide_approval(
            approval_id,
            status=ApprovalStatus.APPROVED,
            actor=actor,
            comment=comment,
            attachments=attachment,
        )
    )


@approval_app.command("reject")
def approval_reject(
    ctx: typer.Context,
    approval_id: str = typer.Argument(...),
    actor: str = typer.Option(..., "--actor"),
    comment: str = typer.Option("", "--comment"),
) -> None:
    repository = AuditRepository(_database(ctx.obj.settings))
    from agent.models.enums import ApprovalStatus

    _emit(
        repository.decide_approval(
            approval_id,
            status=ApprovalStatus.REJECTED,
            actor=actor,
            comment=comment,
        )
    )


# ---------- workpaper ----------

@workpaper_app.command("export")
def workpaper_export(
    ctx: typer.Context,
    task_id: str = typer.Argument(...),
    prepared_by: str = typer.Option("AuditOx Runtime", "--prepared-by"),
    reviewer: str = typer.Option("", "--reviewer"),
) -> None:
    service = _sync_service(ctx.obj.settings)
    _emit(
        service.export_workpaper(
            task_id,
            prepared_by=prepared_by,
            reviewer=reviewer,
        )
    )


if __name__ == "__main__":
    app()
