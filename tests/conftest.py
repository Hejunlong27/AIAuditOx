"""pytest 共享夹具。

原则：测试**不共享全局状态**。每个用例拿独立的临时目录与独立的数据库，
避免 SQLite 文件锁与残留数据造成的偶发失败。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.config.settings import Settings  # noqa: E402
from agent.models import AuditTask, TaskStatus  # noqa: E402
from agent.security.workspace import Workspace  # noqa: E402
from agent.storage.database import Database  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def tmp_settings(tmp_path: Path) -> Settings:
    """指向临时目录的设置，绝不污染仓库内的 storage/。"""
    return Settings(
        repo_root=REPO_ROOT,
        data_root=tmp_path / "storage",
        workspace_root=tmp_path / "workspaces",
        artifacts_root=tmp_path / "artifacts",
        database_url="",
    )


@pytest.fixture()
def db(tmp_settings: Settings) -> Database:
    tmp_settings.ensure_dirs()
    database = Database(tmp_settings.resolved_database_url)
    database.create_all()
    yield database
    database.dispose()


@pytest.fixture()
def workspace(tmp_settings: Settings) -> Workspace:
    return Workspace.create(tmp_settings.workspace_path, "PRJ-TEST", "TASK-0001")


@pytest.fixture()
def sample_task(workspace: Workspace) -> AuditTask:
    return AuditTask(
        task_id="TASK-0001",
        project_id="PRJ-TEST",
        user_request="对某公司 2026 年度银行存款执行审计程序",
        skill_id="z-1-2-bank-deposits",
        skill_version="1.0.0",
        status=TaskStatus.CREATED,
        workspace=str(workspace.root),
    )


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """一份最小的银行账户余额明细 CSV（UTF-8 BOM，模拟 Excel 导出）。"""
    p = tmp_path / "accounts.csv"
    p.write_text(
        "账户ID,开户银行,账号,账户性质,币种,原币金额,账面汇率,账面RMB,对账单RMB,是否受限\n"
        "A001,工商银行XX支行,6222****0001,基本户,RMB,3500000.00,1.0000,3500000.00,3500000.00,否\n"
        "A002,招商银行XX支行,6222****0023,一般户,RMB,2000000.00,1.0000,2000000.00,2060000.00,否\n",
        encoding="utf-8-sig",
    )
    return p
