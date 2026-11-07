"""配置层单测：路径派生与会话级隔离。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.config.settings import Settings

pytestmark = pytest.mark.unit


def test_default_paths_derive_from_repo_root(repo_root: Path) -> None:
    s = Settings(repo_root=repo_root)
    assert s.skills_path == (repo_root / "skills").resolve()
    assert s.registry_file == (repo_root / "registry" / "skills.json").resolve()
    assert s.data_path == (repo_root / "storage").resolve()


def test_override_data_root(tmp_path: Path) -> None:
    s = Settings(data_root=tmp_path / "d")
    assert s.data_path == (tmp_path / "d").resolve()


def test_sqlite_url_derived_from_data_root(tmp_path: Path) -> None:
    s = Settings(data_root=tmp_path / "d", database_url="")
    assert s.resolved_database_url.startswith("sqlite:///")
    assert s.resolved_database_url.endswith("auditox.db")


def test_explicit_database_url_wins(tmp_path: Path) -> None:
    s = Settings(data_root=tmp_path / "d", database_url="postgresql+psycopg://u@h/db")
    assert s.resolved_database_url == "postgresql+psycopg://u@h/db"


def test_network_and_shell_default_off() -> None:
    s = Settings()
    assert s.allow_network is False
    assert s.allow_shell is False


def test_ensure_dirs(tmp_path: Path) -> None:
    s = Settings(
        data_root=tmp_path / "d",
        workspace_root=tmp_path / "w",
        artifacts_root=tmp_path / "a",
    )
    s.ensure_dirs()
    assert (tmp_path / "d").is_dir()
    assert (tmp_path / "w").is_dir()
    assert (tmp_path / "a").is_dir()


def test_max_steps_bounds() -> None:
    with pytest.raises(ValueError):
        Settings(max_steps=0)
