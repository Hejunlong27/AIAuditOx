"""工具使用审计器的单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from tools.audit_tool_usage import scan


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_scan_reports_references_unused_and_missing(tmp_path: Path) -> None:
    skill = tmp_path / "skill-library" / "demo-skill"
    _write(
        skill / "dsl.json",
        json.dumps(
            {
                "skill_id": "demo-skill",
                "procedures": [
                    {"id": "P01", "tools": ["recalc_check", "missing_tool"]},
                    {"id": "P02", "tools": ["recalc_check"]},
                ],
            }
        ),
    )
    _write(skill / "scripts" / "run.py", "print('demo')\n")
    _write(
        tmp_path / "skill-tools" / "auditox-tools" / "src" / "index.js",
        "defineTool({ name: 'recalc_check' });\ndefineTool({ name: 'unused_tool' });\n",
    )

    report = scan(tmp_path)

    assert report["summary"] == {
        "central_tool_count": 2,
        "referenced_tool_count": 2,
        "tool_reference_count": 3,
        "skills_with_tool_or_script": 1,
        "missing_tool_count": 1,
    }
    assert report["tool_references"] == {"recalc_check": 2, "missing_tool": 1}
    assert report["missing_tools"] == {"missing_tool": ["demo-skill:P01"]}
    assert report["unused_central_tools"] == ["unused_tool"]
    assert report["by_skill"]["demo-skill"]["local_scripts"] == ["scripts/run.py"]


def test_scan_rejects_missing_skill_library(tmp_path: Path) -> None:
    try:
        scan(tmp_path)
    except FileNotFoundError as exc:
        assert "技能库不存在" in str(exc)
    else:
        raise AssertionError("缺少技能库时应报错")
