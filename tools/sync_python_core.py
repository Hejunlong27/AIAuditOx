#!/usr/bin/env python3
"""Generate skill-local auditox_common copies from the canonical Python core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _source_files(core_root: Path) -> dict[Path, bytes]:
    source = core_root / "src" / "auditox_common"
    if not source.is_dir():
        raise FileNotFoundError(f"Python 核心源码不存在：{source}")
    return {
        path.relative_to(source): path.read_bytes()
        for path in sorted(source.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def _consumers(project_root: Path) -> list[str]:
    path = project_root / "agent-runtime" / "config" / "python-core-consumers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schemaVersion", 0)) != 1:
        raise ValueError("python-core-consumers.json 版本不受支持")
    skills = data.get("skills")
    if not isinstance(skills, list) or not skills:
        raise ValueError("python-core-consumers.json 缺少 skills")
    return [str(item) for item in skills]


def sync(project_root: Path, *, write: bool = False) -> list[tuple[Path, bytes]]:
    core_root = project_root / "skill-tools" / "auditox-python-core"
    files = _source_files(core_root)
    changes: list[tuple[Path, bytes]] = []
    for skill_id in _consumers(project_root):
        skill_dir = project_root / "skill-library" / skill_id
        if not skill_dir.is_dir():
            raise FileNotFoundError(f"技能包不存在：{skill_dir}")
        target_root = skill_dir / "scripts" / "auditox_common"
        for relative, content in files.items():
            target = target_root / relative
            current = target.read_bytes() if target.is_file() else None
            if current != content:
                changes.append((target, content))
                if write:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步技能包内 auditox_common 兼容副本")
    parser.add_argument("--project-root", type=Path, default=_default_project_root())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    changes = sync(args.project_root.resolve(), write=args.write)
    if changes:
        action = "已写入" if args.write else "待更新"
        for path, _content in changes:
            print(f"[{action}] {path}")
        return 0 if args.write else 1
    print("Python 共享核心副本已一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
