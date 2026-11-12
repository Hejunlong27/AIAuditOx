"""Python 共享核心 vendoring 测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.sync_python_core import sync


def test_sync_check_then_write(tmp_path: Path) -> None:
    source = tmp_path / "skill-tools" / "auditox-python-core" / "src" / "auditox_common"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source / "numeric.py").write_text("def f(): return 1\n", encoding="utf-8")
    skill = tmp_path / "skill-library" / "demo" / "scripts"
    skill.mkdir(parents=True)
    config = tmp_path / "agent-runtime" / "config" / "python-core-consumers.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"schemaVersion": 1, "skills": ["demo"]}),
        encoding="utf-8",
    )

    pending = sync(tmp_path)
    assert len(pending) == 2
    assert sync(tmp_path, write=True)
    assert (skill / "auditox_common" / "__init__.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert sync(tmp_path) == []


def test_sync_rejects_missing_skill(tmp_path: Path) -> None:
    source = tmp_path / "skill-tools" / "auditox-python-core" / "src" / "auditox_common"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    config = tmp_path / "agent-runtime" / "config" / "python-core-consumers.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"schemaVersion": 1, "skills": ["missing"]}),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="技能包不存在"):
        sync(tmp_path)
