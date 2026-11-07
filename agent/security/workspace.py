"""工作区隔离与路径安全（PART 20）。

核心威胁模型：技能库里存的是**运行时不可信输入**——
程序卡文本、dsl.json、用户上传文件名、外部 agent 传入的参数。
任何一个被用来拼路径，都可能读到工作区外的文件。

因此所有文件访问必须经过 :class:`Workspace`，它做三件事：
1. 把路径解析成真实绝对路径（``resolve()``，吃掉 ``..`` 与符号链接）；
2. 断言结果仍在工作区根内；
3. 对原始资料目录实施只读 + 哈希清单。
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

RAW_DIR = "01_原始资料"
WORKPAPER_DIR = "02_工作底稿"
ARTIFACT_DIR = "03_产出"
BACKUP_DIR = ".auditox_backups"
LOG_DIR = "04_日志"

CHUNK = 1024 * 1024


class SecurityError(RuntimeError):
    """安全策略拒绝。调用方不得 fallback 到不安全的路径。"""


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA256，避免大文件吃内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FileRecord:
    """原始资料的登记记录。"""

    relative_path: str
    sha256: str
    size: int


class Workspace:
    """一个任务的受控工作目录。

    目录布局（与技能包 SKILL.md 的约定一致）::

        <root>/<project_id>/<task_id>/
        ├── 01_原始资料/     只读，登记后不可写
        ├── 02_工作底稿/     产出底稿
        ├── 03_产出/         其他产出（冲突报告、证据清单）
        ├── 04_日志/         审计日志
        └── .auditox_backups/ 副本先行备份
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)

    # ---------- 创建与基础属性 ----------

    @classmethod
    def create(cls, base: Path, project_id: str, task_id: str) -> "Workspace":
        """按 ID 创建隔离目录。ID 合法性由调用方（模型层）先行校验。"""
        for ident in (project_id, task_id):
            _assert_safe_ident(ident)
        root = (base / project_id / task_id).resolve(strict=False)
        ws = cls(root)
        for sub in (RAW_DIR, WORKPAPER_DIR, ARTIFACT_DIR, LOG_DIR, BACKUP_DIR):
            (root / sub).mkdir(parents=True, exist_ok=True)
        return ws

    @property
    def raw_dir(self) -> Path:
        return self.root / RAW_DIR

    @property
    def workpaper_dir(self) -> Path:
        return self.root / WORKPAPER_DIR

    @property
    def artifact_dir(self) -> Path:
        return self.root / ARTIFACT_DIR

    @property
    def log_dir(self) -> Path:
        return self.root / LOG_DIR

    @property
    def backup_dir(self) -> Path:
        return self.root / BACKUP_DIR

    # ---------- 路径解析（唯一入口） ----------

    def resolve_inside(self, candidate: str | Path) -> Path:
        """把候选路径解析为工作区内的真实路径。

        拒绝：绝对路径逃逸、``..`` 上跳、符号链接指向外部、NUL 字节。
        """
        raw = str(candidate)
        if "\x00" in raw:
            raise SecurityError("路径包含 NUL 字节")
        p = Path(raw)
        target = (p if p.is_absolute() else self.root / p)
        resolved = target.resolve(strict=False)
        if not _is_within(resolved, self.root):
            raise SecurityError(f"路径越界被拒绝：{raw} → {resolved}")
        return resolved

    def resolve_for_write(self, candidate: str | Path) -> Path:
        """写盘前的路径检查（PART 20 第 15 条：输出前检查目标路径）。

        额外约束：不允许写进原始资料目录——原始资料只读是硬要求。
        """
        resolved = self.resolve_inside(candidate)
        if _is_within(resolved, self.raw_dir):
            raise SecurityError(f"原始资料目录只读，拒绝写入：{resolved}")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    # ---------- 原始资料登记与只读 ----------

    def register_raw_file(self, source: Path, *, relative_name: str | None = None) -> FileRecord:
        """复制一份原始资料进工作区并登记哈希。

        复制而非引用：原始目录可能被外部改动，工作区必须持有快照，
        否则事后无法证明"审计时看到的到底是哪个版本"。
        """
        src = Path(source).resolve()
        if not src.is_file():
            raise SecurityError(f"待登记文件不存在：{src}")
        name = relative_name or src.name
        if Path(name).name != name:
            raise SecurityError(f"原始资料文件名不得包含目录分隔符：{name!r}")
        dest = self.resolve_inside(self.raw_dir / name)
        if dest.exists():
            raise SecurityError(f"原始资料同名文件已存在，拒绝覆盖：{dest.name}")
        shutil.copy2(src, dest)
        _make_readonly(dest)
        return FileRecord(
            relative_path=str(dest.relative_to(self.root)).replace(os.sep, "/"),
            sha256=sha256_file(dest),
            size=dest.stat().st_size,
        )

    def list_raw_files(self) -> list[FileRecord]:
        """遍历原始资料并重算哈希，用于检测执行期被篡改（测试场景 T15）。"""
        records: list[FileRecord] = []
        if not self.raw_dir.is_dir():
            return records
        for p in sorted(self.raw_dir.rglob("*")):
            if p.is_file():
                records.append(
                    FileRecord(
                        relative_path=str(p.relative_to(self.root)).replace(os.sep, "/"),
                        sha256=sha256_file(p),
                        size=p.stat().st_size,
                    )
                )
        return records

    def verify_raw_unchanged(self, expected: dict[str, str]) -> list[str]:
        """比对登记时的哈希与实际哈希，返回被改动/丢失的相对路径列表。"""
        actual = {r.relative_path: r.sha256 for r in self.list_raw_files()}
        changed: list[str] = []
        for rel, digest in expected.items():
            if rel not in actual:
                changed.append(f"{rel}（缺失）")
            elif actual[rel] != digest:
                changed.append(f"{rel}（哈希不符）")
        return changed

    # ---------- 副本先行 ----------

    def backup(self, target: Path) -> Path:
        """修改既有文件前先建副本（底稿制式规定的「副本先行」）。"""
        resolved = self.resolve_inside(target)
        if not resolved.is_file():
            raise SecurityError(f"待备份文件不存在：{resolved}")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = _timestamp_slug()
        dest = self.backup_dir / f"{resolved.stem}.{stamp}.bak{resolved.suffix}"
        shutil.copy2(resolved, dest)
        return dest


def _timestamp_slug() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _assert_safe_ident(ident: str) -> None:
    if not ident or ident in (".", ".."):
        raise SecurityError(f"非法标识符：{ident!r}")
    for bad in ("/", "\\", "\x00", ":"):
        if bad in ident:
            raise SecurityError(f"标识符含非法字符 {bad!r}：{ident!r}")


def _make_readonly(path: Path) -> None:
    """尽力设置只读位。

    Windows 上 ``chmod`` 只影响只读位，对目录/ACL 无效；
    真正的隔离靠 :meth:`Workspace.resolve_for_write`，此处是第二道防线。
    """
    try:
        mode = path.stat().st_mode
        path.chmod(mode & ~0o222)
    except OSError:
        pass
