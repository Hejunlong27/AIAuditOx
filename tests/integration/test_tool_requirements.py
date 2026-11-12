"""Runtime 侧辅助技能能力清单的双模式验收。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools import ToolRegistry, load_tool_requirements

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_AVAILABLE = (
    (PROJECT_ROOT / 'skill-library').is_dir()
    and (PROJECT_ROOT / 'skill-tools' / 'auditox-tools').is_dir()
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not WORKSPACE_AVAILABLE, reason='需要统一工作区中的 skill-library/skill-tools'),
]

SKILLS = [
    "confirmation-address-auditor",
    "doc-ocr-extract",
    "financial-statement-analysis",
    "heavy-asset-financial-analysis",
    "universal-annual-audit",
]


def test_auxiliary_skill_requirements_allow_standalone_fallback(repo_root: Path) -> None:
    project_root = repo_root.parent
    skill_root = project_root / "skill-library"
    override = repo_root / "config" / "skill-tool-requirements.json"
    registry = ToolRegistry()

    for skill_id in SKILLS:
        manifest = load_tool_requirements(
            skill_root / skill_id,
            override_file=override,
        )
        assert manifest.requirements, skill_id
        resolution = registry.resolve(manifest.requirements)
        assert resolution.can_run is True, skill_id
        assert not resolution.missing_required, skill_id
        assert all(
            name in resolution.fallbacks for name in resolution.missing_preferred
        ), skill_id
