#!/usr/bin/env python3
"""Generate per-skill tool-requirements.json from the central Runtime config.

The central config is the source of truth. Skill-local manifests are generated
release artifacts that make standalone skill packages self-describing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "agent-runtime" / "config" / "skill-tool-requirements.json"
    if not path.is_file():
        raise FileNotFoundError(f"工具能力配置不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schemaVersion", 0)) != 1:
        raise ValueError(f"不支持的工具能力配置版本：{data.get('schemaVersion')}")
    skills = data.get("skills")
    if not isinstance(skills, dict):
        raise ValueError("工具能力配置缺少 skills 对象")
    return data


def render_manifest(requirements: list[dict[str, Any]]) -> str:
    payload = {
        "schemaVersion": 1,
        "requirements": requirements,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def sync(project_root: Path, *, write: bool = False) -> list[tuple[Path, str]]:
    """Return changed targets and optionally write generated manifests."""
    config = load_config(project_root)
    changes: list[tuple[Path, str]] = []
    for skill_id, requirements in sorted(config["skills"].items()):
        skill_dir = project_root / "skill-library" / skill_id
        if not skill_dir.is_dir():
            raise FileNotFoundError(f"技能包不存在：{skill_dir}")
        target = skill_dir / "tool-requirements.json"
        content = render_manifest(requirements)
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current != content:
            changes.append((target, content))
            if write:
                target.write_text(content, encoding="utf-8", newline="")
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步技能包 tool-requirements.json")
    parser.add_argument("--project-root", type=Path, default=_default_project_root())
    parser.add_argument("--write", action="store_true", help="写入生成物；缺省只检查")
    args = parser.parse_args(argv)

    changes = sync(args.project_root.resolve(), write=args.write)
    if changes:
        action = "已写入" if args.write else "待更新"
        for path, _content in changes:
            print(f"[{action}] {path}")
        return 0 if args.write else 1
    print("工具能力清单已一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
