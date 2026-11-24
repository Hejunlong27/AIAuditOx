"""Runtime consumption of external skill fact sources and generated indexes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.skills import SkillLoader, SkillRegistry
from tools.build_index import main as build_index_main

pytestmark = pytest.mark.unit


def test_build_index_supports_external_skills_dir(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skill-library"
    package = skills_dir / "demo-skill"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: 演示技能\nversion: 1.0.0\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    output = tmp_path / "runtime" / "skills.json"

    assert build_index_main(["--skills-dir", str(skills_dir), "--out", str(output)]) == 0
    index = json.loads(output.read_text(encoding="utf-8"))
    assert index["count"] == 1
    assert index["skills"][0]["id"] == "demo-skill"

    registry = SkillRegistry(
        Path(__file__).resolve().parents[2],
        skills_dir=skills_dir,
        registry_file=output,
    ).load()
    assert registry.list_ids() == ["demo-skill"]
    assert registry.get_skill_path("demo-skill") == package.resolve()


def test_external_fact_source_index_is_current(repo_root: Path) -> None:
    fact_root = repo_root.parent / "skill-library"
    index_path = repo_root / "registry" / "skill-library.json"
    if not fact_root.is_dir() or not index_path.is_file():
        pytest.skip("需要统一工作区中的 skill-library 及已生成的 Runtime 索引")

    expected = sorted(
        p.name for p in fact_root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
    )
    registry = SkillRegistry(
        repo_root,
        skills_dir=fact_root,
        registry_file=index_path,
    ).load()
    assert registry.list_ids() == expected
    assert "audit-workpaper-reverse-engineering" in registry.list_ids()

    loader = SkillLoader(repo_root, registry)
    loaded = loader.load_skill("audit-workpaper-reverse-engineering")
    assert loaded.frontmatter["version"] == "1.0.1"
    assert loaded.root.is_relative_to(fact_root.resolve())
