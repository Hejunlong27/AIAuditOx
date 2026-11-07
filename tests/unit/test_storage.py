"""数据库层单测（PART 16）：9 张表、外键、乐观锁、事务。"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

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

pytestmark = pytest.mark.unit

EXPECTED_TABLES = {
    "projects",
    "tasks",
    "plans",
    "plan_steps",
    "tool_runs",
    "evidences",
    "approvals",
    "artifacts",
    "audit_events",
}


def _project(db: Database, pid: str = "PRJ-1") -> None:
    now = "2026-11-07T00:00:00+00:00"
    with db.session() as s:
        s.add(ProjectRow(project_id=pid, name="测试项目", created_at=now, updated_at=now))


def _task(db: Database, tid: str = "T1", pid: str = "PRJ-1") -> None:
    now = "2026-11-07T00:00:00+00:00"
    with db.session() as s:
        s.add(
            TaskRow(
                task_id=tid,
                project_id=pid,
                user_request="银行存款审计",
                status="CREATED",
                workspace="/tmp/ws",
                created_at=now,
                updated_at=now,
            )
        )


class TestSchema:
    def test_all_nine_tables_created(self, db: Database) -> None:
        names = set(inspect(db.engine).get_table_names())
        assert EXPECTED_TABLES.issubset(names), EXPECTED_TABLES - names

    def test_foreign_keys_are_declared(self, db: Database) -> None:
        fks = inspect(db.engine).get_foreign_keys("tasks")
        assert any(fk["referred_table"] == "projects" for fk in fks)

    def test_indexes_exist(self, db: Database) -> None:
        indexes = inspect(db.engine).get_indexes("tasks")
        assert any(i["name"] == "ix_tasks_project_status" for i in indexes)

    def test_plan_steps_unique_constraint(self, db: Database) -> None:
        uniques = inspect(db.engine).get_unique_constraints("plan_steps")
        assert any(u["name"] == "uq_plan_steps_task_step" for u in uniques)


class TestConstraints:
    def test_foreign_key_enforced(self, db: Database) -> None:
        now = "2026-11-07T00:00:00+00:00"
        with pytest.raises(IntegrityError):
            with db.session() as s:
                s.add(
                    TaskRow(
                        task_id="ORPHAN",
                        project_id="NO-SUCH-PROJECT",
                        user_request="x",
                        status="CREATED",
                        workspace="/tmp",
                        created_at=now,
                        updated_at=now,
                    )
                )

    def test_duplicate_step_rejected(self, db: Database) -> None:
        _project(db)
        _task(db)
        now = "2026-11-07T00:00:00+00:00"
        with db.session() as s:
            s.add(
                PlanStepRow(
                    task_id="T1", step_id="P01", procedure_id="P01", name="a",
                    status="PENDING", updated_at=now,
                )
            )
        with pytest.raises(IntegrityError):
            with db.session() as s:
                s.add(
                    PlanStepRow(
                        task_id="T1", step_id="P01", procedure_id="P01", name="dup",
                        status="PENDING", updated_at=now,
                    )
                )


class TestTransactions:
    def test_rollback_on_exception(self, db: Database) -> None:
        now = "2026-11-07T00:00:00+00:00"
        with pytest.raises(RuntimeError):
            with db.session() as s:
                s.add(ProjectRow(project_id="PRJ-X", name="x", created_at=now, updated_at=now))
                raise RuntimeError("boom")
        with db.session() as s:
            assert s.get(ProjectRow, "PRJ-X") is None

    def test_commit_persists(self, db: Database) -> None:
        _project(db, "PRJ-KEEP")
        with db.session() as s:
            assert s.get(ProjectRow, "PRJ-KEEP") is not None


class TestOptimisticLock:
    def test_version_mismatch_detected(self, db: Database) -> None:
        """并发更新：用 version 做条件更新，第二次必须影响 0 行。"""
        _project(db, "PRJ-LOCK")
        with db.session() as s:
            row = s.get(ProjectRow, "PRJ-LOCK")
            assert row.version == 1
            row.name = "改名A"
            row.version += 1
        # 模拟另一个持有旧 version=1 的写入方
        with db.session() as s:
            result = s.execute(
                text(
                    "UPDATE projects SET name=:n, version=version+1 "
                    "WHERE project_id=:p AND version=:v"
                ),
                {"n": "改名B", "p": "PRJ-LOCK", "v": 1},
            )
            assert result.rowcount == 0, "旧版本更新必须失败"
        with db.session() as s:
            assert s.get(ProjectRow, "PRJ-LOCK").name == "改名A"


class TestAllTablesWritable:
    def test_write_one_row_each(self, db: Database) -> None:
        now = "2026-11-07T00:00:00+00:00"
        _project(db)
        _task(db)
        with db.session() as s:
            s.add(PlanRow(plan_id="PL1", task_id="T1", skill_id="s", created_at=now))
            s.add(
                PlanStepRow(
                    task_id="T1", plan_id="PL1", step_id="P01", procedure_id="P01",
                    name="余额表", status="PENDING", updated_at=now,
                )
            )
            s.add(
                ToolRunRow(
                    execution_id="X1", task_id="T1", tool_name="recalc_check", created_at=now
                )
            )
            s.add(
                EvidenceRow(
                    evidence_id="E1", task_id="T1", procedure_id="P01",
                    tool_name="recalc_check", created_at=now,
                )
            )
            s.add(
                ApprovalRow(
                    approval_id="A1", task_id="T1", procedure_id="P05",
                    reason="函证", requested_action="寄发", status="PENDING",
                    created_at=now, updated_at=now,
                )
            )
            s.add(
                ArtifactRow(
                    artifact_id="AR1", task_id="T1", kind="workpaper",
                    path="/tmp/a.xlsx", sha256="c" * 64, created_at=now,
                )
            )
            s.add(AuditEventRow(task_id="T1", event="TASK_CREATED", created_at=now))
        with db.session() as s:
            counts = {
                name: s.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
                for name in EXPECTED_TABLES
            }
        assert all(v >= 1 for v in counts.values()), counts


class TestPragmas:
    def test_foreign_keys_pragma_on(self, db: Database) -> None:
        with db.session() as s:
            assert s.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    def test_wal_mode(self, db: Database) -> None:
        with db.session() as s:
            assert s.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
