"""核心数据模型单测（PART 5）。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agent.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditPlan,
    AuditTask,
    Evidence,
    EvidenceKind,
    ExecutionMode,
    ExecutionPolicy,
    PlanStep,
    ProcedureDefinition,
    SourceRef,
    StepStatus,
    TaskStatus,
    ToolResult,
    to_money,
)

pytestmark = pytest.mark.unit


class TestAuditTask:
    def test_minimal_task(self) -> None:
        t = AuditTask(
            task_id="T1", project_id="P1", user_request="银行存款审计", workspace="/tmp/ws"
        )
        assert t.status is TaskStatus.CREATED
        assert t.created_at.tzinfo is not None

    def test_task_id_rejects_path_separator(self) -> None:
        with pytest.raises(ValidationError, match="标识符不得包含"):
            AuditTask(
                task_id="../escape", project_id="P1", user_request="x", workspace="/tmp"
            )

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="必须带时区"):
            AuditTask(
                task_id="T1",
                project_id="P1",
                user_request="x",
                workspace="/tmp",
                created_at=datetime(2026, 1, 1),
            )

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTask(
                task_id="T1",
                project_id="P1",
                user_request="x",
                workspace="/tmp",
                unexpected="boom",
            )


class TestExecutionPolicy:
    def test_human_flag_requires_non_auto_mode(self) -> None:
        with pytest.raises(ValidationError, match="自相矛盾"):
            ExecutionPolicy(human_confirmation=True, mode=ExecutionMode.AUTO)

    def test_requires_human_property(self) -> None:
        p = ExecutionPolicy(human_judgment=True, mode=ExecutionMode.AUTO_WITH_JUDGMENT)
        assert p.requires_human is True

    def test_auto_policy(self) -> None:
        p = ExecutionPolicy(automated_execution=True, mode=ExecutionMode.AUTO)
        assert p.requires_human is False


class TestProcedureDefinition:
    def test_valid_procedure(self) -> None:
        p = ProcedureDefinition(id="P01", name="余额明细表编制", tools=["recalc_check"])
        assert p.mandatory is False
        assert p.dependencies == []

    def test_bad_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProcedureDefinition(id="X-1", name="bad")

    def test_g_series_id_accepted(self) -> None:
        # 规范型技能包用 G0/G1，不能只放行 P 开头
        assert ProcedureDefinition(id="G1", name="制式检查").id == "G1"

    def test_self_dependency_rejected(self) -> None:
        with pytest.raises(ValidationError, match="不能依赖自身"):
            ProcedureDefinition(id="P01", name="x", dependencies=["P01"])


class TestPlan:
    def _step(self, sid: str, deps: list[str] | None = None) -> PlanStep:
        return PlanStep(step_id=sid, procedure_id=sid, name=sid, dependencies=deps or [])

    def test_duplicate_step_ids_rejected(self) -> None:
        with pytest.raises(ValidationError, match="step_id 重复"):
            AuditPlan(
                plan_id="PL1",
                task_id="T1",
                skill_id="s",
                steps=[self._step("P01"), self._step("P01")],
            )

    def test_step_lookup_and_mandatory_flag(self) -> None:
        plan = AuditPlan(
            plan_id="PL1",
            task_id="T1",
            skill_id="s",
            steps=[self._step("P01"), PlanStep(step_id="P05", procedure_id="P05", name="函证", mandatory=True)],
        )
        assert plan.step("P05").mandatory
        assert [s.step_id for s in plan.mandatory_steps] == ["P05"]
        with pytest.raises(KeyError):
            plan.step("P99")

    def test_retryable_boundary(self) -> None:
        s = PlanStep(step_id="P01", procedure_id="P01", name="x", retry_count=2, max_retries=2)
        assert s.retryable is False


class TestEvidence:
    def test_traceable_requires_source_hash(self) -> None:
        ev = Evidence(
            evidence_id="E1",
            task_id="T1",
            procedure_id="P01",
            tool_name="recalc_check",
            source_file="01_原始资料/accounts.csv",
            result_file="02_工作底稿/out.json",
        )
        assert ev.traceable is False  # 缺 sha256

    def test_traceable_with_full_chain(self) -> None:
        digest = "a" * 64
        ev = Evidence(
            evidence_id="E1",
            task_id="T1",
            procedure_id="P01",
            tool_name="recalc_check",
            source_file="01_原始资料/accounts.csv",
            source_sha256=digest,
            result_file="02_工作底稿/out.json",
            kind=EvidenceKind.TOOL_OUTPUT,
        )
        assert ev.traceable is True

    def test_sha256_format_enforced(self) -> None:
        with pytest.raises(ValidationError, match="64 位小写十六进制"):
            SourceRef(file="a.csv", sha256="not-a-hash")

    def test_source_ref_accepts_location(self) -> None:
        ref = SourceRef(
            file="a.xlsx", sha256="b" * 64, sheet="Z-1-2-01", row_range="5-28", columns=["账户"]
        )
        assert ref.sheet == "Z-1-2-01"
        assert ref.page is None


class TestApproval:
    def test_decided_without_actor_rejected(self) -> None:
        with pytest.raises(ValidationError, match="未记录操作人"):
            ApprovalRequest(
                approval_id="A1",
                task_id="T1",
                procedure_id="P05",
                reason="函证需人工",
                requested_action="寄发询证函",
                status=ApprovalStatus.APPROVED,
            )

    def test_pending_is_not_decided(self) -> None:
        a = ApprovalRequest(
            approval_id="A1",
            task_id="T1",
            procedure_id="P05",
            reason="函证需人工",
            requested_action="寄发询证函",
        )
        assert a.pending is True


class TestToolResult:
    def test_ok_helper(self) -> None:
        r = ToolResult.ok("recalc_check", {"diff": "0.00"}, evidence_files=["a.json"])
        assert r.success and r.evidence_files == ["a.json"]

    def test_fail_helper(self) -> None:
        r = ToolResult.fail("excel_read", "文件不存在")
        assert r.success is False and r.error == "文件不存在"


class TestMoney:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("11210000.00", Decimal("11210000.00")),
            ("11,210,000.00", Decimal("11210000.00")),
            (3500000, Decimal("3500000")),
            (0.1, Decimal("0.1")),
        ],
    )
    def test_parse(self, raw: object, expected: Decimal) -> None:
        assert to_money(raw) == expected

    def test_float_binary_error_avoided(self) -> None:
        # 0.1 + 0.2 用 float 会得到 0.30000000000000004
        total = to_money(0.1) + to_money(0.2)
        assert str(total) == "0.3"

    def test_reject_blank_and_bool(self) -> None:
        with pytest.raises(ValueError):
            to_money("   ")
        with pytest.raises(ValueError):
            to_money(True)


class TestTimezones:
    def test_utcnow_is_aware(self) -> None:
        from agent.models.base import utcnow

        ts = utcnow()
        assert ts.tzinfo == timezone.utc
        assert isinstance(ts, datetime)
