"""技能工具能力清单生成器测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.sync_skill_tool_requirements import sync


def test_sync_check_then_write(tmp_path: Path) -> None:
    config = tmp_path / "agent-runtime" / "config" / "skill-tool-requirements.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "skills": {
                    "demo": [
                        {
                            "name": "excel_read",
                            "level": "preferred",
                            "fallback": "skill_local",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    skill = tmp_path / "skill-library" / "demo"
    skill.mkdir(parents=True)

    pending = sync(tmp_path)
    assert len(pending) == 1
    assert pending[0][0] == skill / "tool-requirements.json"
    assert not pending[0][0].exists()

    written = sync(tmp_path, write=True)
    assert len(written) == 1
    generated = json.loads((skill / "tool-requirements.json").read_text(encoding="utf-8"))
    assert generated == {
        "schemaVersion": 1,
        "requirements": [
            {"name": "excel_read", "level": "preferred", "fallback": "skill_local"}
        ],
    }
    assert sync(tmp_path) == []


def test_sync_rejects_missing_skill(tmp_path: Path) -> None:
    config = tmp_path / "agent-runtime" / "config" / "skill-tool-requirements.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"schemaVersion": 1, "skills": {"missing": []}}),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="技能包不存在"):
        sync(tmp_path)
