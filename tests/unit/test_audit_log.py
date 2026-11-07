"""脱敏与结构化审计日志单测（PART 20 第 5 条）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.security.audit_log import (
    JsonLineAuditLogger,
    redact_text,
    redact_value,
)

pytestmark = pytest.mark.unit


class TestRedaction:
    @pytest.mark.parametrize(
        ("raw", "marker"),
        [
            ("账号 6222021234567890 已核对", "[ACCT]"),
            ("身份证 11010119900101123X", "[ID]"),
            ("联系电话 13800138000", "[PHONE]"),
            ("邮箱 auditor@example.com", "[EMAIL]"),
        ],
    )
    def test_patterns(self, raw: str, marker: str) -> None:
        out = redact_text(raw)
        assert marker in out
        assert out != raw

    def test_amount_not_mangled(self) -> None:
        # 金额含小数点，不能被账号规则吞掉
        out = redact_text("余额 11210000.00 元")
        assert "11210000.00" in out

    def test_sensitive_key_replaced_wholesale(self) -> None:
        out = redact_value({"api_key": "sk-live-abc", "amount": "100.00"})
        assert out["api_key"] == "[REDACTED]"
        assert out["amount"] == "100.00"

    def test_nested_structures(self) -> None:
        out = redact_value({"items": [{"phone": "13800138000"}]})
        assert out["items"][0]["phone"] == "[PHONE]"

    def test_non_string_preserved(self) -> None:
        assert redact_value(3) == 3
        assert redact_value(None) is None
        assert redact_value(True) is True


class TestJsonLineLogger:
    def test_writes_one_json_per_line(self, tmp_path: Path) -> None:
        log = JsonLineAuditLogger(tmp_path / "audit.jsonl", trace_id="TR-1")
        log.emit("TASK_CREATED", task_id="T1")
        log.emit("STEP_DONE", task_id="T1", step="P01")

        lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        rec = json.loads(lines[0])
        assert rec["event"] == "TASK_CREATED"
        assert rec["trace_id"] == "TR-1"
        assert "ts" in rec

    def test_pii_redacted_before_disk(self, tmp_path: Path) -> None:
        log = JsonLineAuditLogger(tmp_path / "audit.jsonl")
        log.emit("NOTE", text="账号 6222021234567890", phone="13800138000")
        content = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
        assert "6222021234567890" not in content
        assert "13800138000" not in content

    def test_trace_id_override_per_record(self, tmp_path: Path) -> None:
        log = JsonLineAuditLogger(tmp_path / "a.jsonl", trace_id="TR-1")
        rec = log.emit("X", trace_id="TR-2")
        assert rec["trace_id"] == "TR-2"
