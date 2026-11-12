#!/usr/bin/env python3
"""Audit tool reuse across the skill library and centralized AuditOx tools.

This is a development-time inventory tool, not a second runtime registry.
It reports how skill dsl.json files use centralized tools and where skill-local
Python scripts still exist, so consolidation decisions can be evidence-based.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TOOL_RE = re.compile(r"defineTool\(\{\s*name:\s*'([^']+)'", re.S)


def _project_root_default() -> Path:
    # <project>/agent-runtime/tools/audit_tool_usage.py
    return Path(__file__).resolve().parents[2]


def _read_central_tools(tool_source: Path) -> list[str]:
    if not tool_source.is_file():
        raise FileNotFoundError(f"中心工具入口不存在：{tool_source}")
    source = tool_source.read_text(encoding="utf-8")
    return sorted(set(TOOL_RE.findall(source)))


def _script_files(skill_dir: Path) -> list[str]:
    scripts: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in {".py", ".js", ".mjs", ".ps1", ".bat", ".cmd"}:
            scripts.append(path.relative_to(skill_dir).as_posix())
    return scripts


def scan(project_root: Path) -> dict[str, Any]:
    """Return a deterministic inventory without writing project files."""
    project_root = project_root.resolve()
    skill_library = project_root / "skill-library"
    tool_source = project_root / "skill-tools" / "auditox-tools" / "src" / "index.js"
    if not skill_library.is_dir():
        raise FileNotFoundError(f"技能库不存在：{skill_library}")

    central_tools = _read_central_tools(tool_source)
    central_set = set(central_tools)
    references: Counter[str] = Counter()
    by_skill: dict[str, dict[str, Any]] = {}
    missing: dict[str, list[str]] = defaultdict(list)

    for skill_dir in sorted(skill_library.iterdir(), key=lambda p: p.name):
        if not skill_dir.is_dir():
            continue
        scripts = _script_files(skill_dir)
        dsl_path = skill_dir / "dsl.json"
        skill_tools: list[str] = []
        procedure_refs: list[dict[str, Any]] = []
        if dsl_path.is_file():
            raw = json.loads(dsl_path.read_text(encoding="utf-8"))
            for procedure in raw.get("procedures", []):
                tools = [str(t) for t in (procedure.get("tools") or [])]
                for tool in tools:
                    references[tool] += 1
                    skill_tools.append(tool)
                    if tool not in central_set:
                        missing[tool].append(f"{skill_dir.name}:{procedure.get('id', '?')}")
                procedure_refs.append({"procedure_id": procedure.get("id", ""), "tools": tools})
        if skill_tools or scripts:
            by_skill[skill_dir.name] = {
                "tool_references": skill_tools,
                "unique_tools": sorted(set(skill_tools)),
                "procedures": procedure_refs,
                "local_scripts": scripts,
            }

    referenced = set(references)
    return {
        "project_root": str(project_root),
        "skill_library": str(skill_library),
        "central_tool_source": str(tool_source),
        "central_tools": central_tools,
        "summary": {
            "central_tool_count": len(central_tools),
            "referenced_tool_count": len(referenced),
            "tool_reference_count": sum(references.values()),
            "skills_with_tool_or_script": len(by_skill),
            "missing_tool_count": len(missing),
        },
        "tool_references": dict(sorted(references.items(), key=lambda item: (-item[1], item[0]))),
        "missing_tools": {name: refs for name, refs in sorted(missing.items())},
        "unused_central_tools": sorted(central_set - referenced),
        "by_skill": by_skill,
    }


def _print_human(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"项目：{report['project_root']}")
    print(f"中心工具：{summary['central_tool_count']} 个")
    print(
        f"技能引用：{summary['referenced_tool_count']} 个工具，"
        f"共 {summary['tool_reference_count']} 次"
    )
    print(f"缺失工具：{summary['missing_tool_count']} 个")
    print("\n引用频次：")
    for name, count in report["tool_references"].items():
        print(f"  {count:4d}  {name}")
    print("\n未被 DSL 引用的中心工具：")
    for name in report["unused_central_tools"]:
        print(f"  - {name}")
    if report["missing_tools"]:
        print("\nDSL 引用但中心工具中不存在：")
        for name, refs in report["missing_tools"].items():
            print(f"  - {name}: {', '.join(refs)}")
    print("\n含工具引用或本地脚本的技能：")
    for skill, row in report["by_skill"].items():
        print(
            f"  - {skill}: tools={len(row['unique_tools'])}, "
            f"references={len(row['tool_references'])}, scripts={len(row['local_scripts'])}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="审计技能库对中心工具的复用情况")
    parser.add_argument("--project-root", type=Path, default=_project_root_default())
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--fail-on-missing", action="store_true", help="发现缺失工具时返回 1")
    args = parser.parse_args(argv)

    report = scan(args.project_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    if args.fail_on_missing and report["missing_tools"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
