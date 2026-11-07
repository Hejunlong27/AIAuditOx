"""工作区隔离与路径安全单测（PART 20）。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent.security.permissions import PermissionDenied, PermissionPolicy, ShellGuard
from agent.security.workspace import (
    RAW_DIR,
    SecurityError,
    Workspace,
    sha256_file,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def ws(tmp_path: Path) -> Workspace:
    return Workspace.create(tmp_path, "PRJ-1", "TASK-1")


class TestWorkspaceLayout:
    def test_directories_created(self, ws: Workspace) -> None:
        for d in (ws.raw_dir, ws.workpaper_dir, ws.artifact_dir, ws.log_dir, ws.backup_dir):
            assert d.is_dir(), d

    def test_rejects_unsafe_ident(self, tmp_path: Path) -> None:
        with pytest.raises(SecurityError):
            Workspace.create(tmp_path, "PRJ", "../escape")
        with pytest.raises(SecurityError):
            Workspace.create(tmp_path, "PRJ", "a/b")


class TestPathTraversal:
    def test_parent_escape_blocked(self, ws: Workspace) -> None:
        with pytest.raises(SecurityError, match="越界"):
            ws.resolve_inside("../../etc/passwd")

    def test_absolute_escape_blocked(self, ws: Workspace, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside.txt"
        with pytest.raises(SecurityError, match="越界"):
            ws.resolve_inside(outside)

    def test_inside_relative_ok(self, ws: Workspace) -> None:
        p = ws.resolve_inside("02_工作底稿/a.xlsx")
        assert str(p).startswith(str(ws.root))

    def test_nul_byte_blocked(self, ws: Workspace) -> None:
        with pytest.raises(SecurityError, match="NUL"):
            ws.resolve_inside("02_工作底稿/a\x00b.xlsx")

    def test_dotdot_that_stays_inside_is_allowed(self, ws: Workspace) -> None:
        # a/../b 归一化后仍在工作区内，不应误伤
        assert ws.resolve_inside("02_工作底稿/../03_产出/x.json").parent == ws.artifact_dir


class TestRawReadOnly:
    def test_write_into_raw_rejected(self, ws: Workspace) -> None:
        with pytest.raises(SecurityError, match="只读"):
            ws.resolve_for_write(f"{RAW_DIR}/evil.csv")

    def test_register_raw_file_copies_and_hashes(self, ws: Workspace, sample_csv: Path) -> None:
        rec = ws.register_raw_file(sample_csv)
        assert rec.sha256 == sha256_file(sample_csv)
        assert (ws.raw_dir / sample_csv.name).is_file()
        # 源文件与副本内容一致
        assert sha256_file(ws.raw_dir / sample_csv.name) == sha256_file(sample_csv)

    def test_register_rejects_name_with_separator(self, ws: Workspace, sample_csv: Path) -> None:
        with pytest.raises(SecurityError, match="目录分隔符"):
            ws.register_raw_file(sample_csv, relative_name="sub/accounts.csv")

    def test_duplicate_registration_rejected(self, ws: Workspace, sample_csv: Path) -> None:
        ws.register_raw_file(sample_csv)
        with pytest.raises(SecurityError, match="拒绝覆盖"):
            ws.register_raw_file(sample_csv)

    def test_tamper_detection(self, ws: Workspace, sample_csv: Path) -> None:
        rec = ws.register_raw_file(sample_csv)
        expected = {rec.relative_path: rec.sha256}
        assert ws.verify_raw_unchanged(expected) == []

        target = ws.root / rec.relative_path
        os.chmod(target, 0o644)  # 绕过只读位，模拟外部篡改
        target.write_text("篡改", encoding="utf-8")
        problems = ws.verify_raw_unchanged(expected)
        assert len(problems) == 1 and "哈希不符" in problems[0]

    def test_missing_raw_detected(self, ws: Workspace, sample_csv: Path) -> None:
        rec = ws.register_raw_file(sample_csv)
        target = ws.root / rec.relative_path
        os.chmod(target, 0o644)  # 只读位会阻止删除，先解除——这本身说明防护生效
        target.unlink()
        problems = ws.verify_raw_unchanged({rec.relative_path: rec.sha256})
        assert problems and "缺失" in problems[0]


class TestBackup:
    def test_backup_creates_copy(self, ws: Workspace) -> None:
        target = ws.workpaper_dir / "wp.xlsx"
        target.write_text("v1", encoding="utf-8")
        bak = ws.backup(target)
        assert bak.is_file() and bak.parent == ws.backup_dir
        assert bak.read_text(encoding="utf-8") == "v1"

    def test_backup_missing_file_rejected(self, ws: Workspace) -> None:
        with pytest.raises(SecurityError, match="不存在"):
            ws.backup(ws.workpaper_dir / "nope.xlsx")


class TestPermissionPolicy:
    def test_unlisted_tool_denied(self) -> None:
        policy = PermissionPolicy(allowed_tools={"recalc_check"})
        with pytest.raises(PermissionDenied, match="不在白名单"):
            policy.check_tool("excel_read", ToolRiskLevelForTest.READ_ONLY)

    def test_listed_tool_allowed(self) -> None:
        policy = PermissionPolicy(allowed_tools={"recalc_check"})
        policy.check_tool("recalc_check", ToolRiskLevelForTest.READ_ONLY)
        assert policy.call_count == 0  # check 不计数，record 才计数

    def test_call_budget_enforced(self) -> None:
        policy = PermissionPolicy(allowed_tools={"a"}, max_tool_calls=1)
        policy.record_call()
        with pytest.raises(PermissionDenied, match="次数已达上限"):
            policy.check_tool("a", ToolRiskLevelForTest.READ_ONLY)

    def test_external_io_blocked_by_default(self) -> None:
        policy = PermissionPolicy(allowed_tools={"web"})
        with pytest.raises(PermissionDenied, match="外部网络"):
            policy.check_tool("web", ToolRiskLevelForTest.EXTERNAL_IO)

    def test_destructive_always_blocked(self) -> None:
        policy = PermissionPolicy(allowed_tools={"rm"}, allow_network=True)
        with pytest.raises(PermissionDenied, match="破坏性"):
            policy.check_tool("rm", ToolRiskLevelForTest.DESTRUCTIVE)

    def test_shell_guard_refuses(self) -> None:
        with pytest.raises(PermissionDenied):
            ShellGuard.run_or_refuse("dir")


# 延迟导入，避免测试文件顶部与 agent 包产生导入顺序耦合
from agent.models.enums import ToolRiskLevel as ToolRiskLevelForTest  # noqa: E402
