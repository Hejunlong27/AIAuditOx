"""核心 Python 能力在技能脚本中的导入与语义验收。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_AVAILABLE = (
    (PROJECT_ROOT / 'skill-library').is_dir()
    and (PROJECT_ROOT / 'skill-tools' / 'auditox-tools').is_dir()
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not WORKSPACE_AVAILABLE, reason='需要统一工作区中的 skill-library/skill-tools'),
]


def test_universal_and_heavy_skills_use_shared_core(repo_root: Path) -> None:
    project_root = repo_root.parent
    universal_scripts = project_root / "skill-library" / "universal-annual-audit" / "scripts"
    heavy_scripts = project_root / "skill-library" / "heavy-asset-financial-analysis" / "scripts"

    sys.path.insert(0, str(universal_scripts))
    try:
        import calculate_financial_ratios as universal
    finally:
        sys.path.remove(str(universal_scripts))

    sys.path.insert(0, str(heavy_scripts))
    try:
        import fin_metrics as heavy
    finally:
        sys.path.remove(str(heavy_scripts))

    assert universal.parse_number("1,234.5") == (1234.5, "")
    assert universal.parse_number("（100）") == (-100.0, "")
    assert universal.normalize_label(" 营业 收入（元） ") == "营业收入"
    assert universal._safe_div(10, 4, digits=4) == 2.5
    assert universal.yoy(
        {"营业收入": {"2024": 100.0, "2025": 120.0}},
        "营业收入",
        "2025",
        "2024",
    ) == pytest.approx(0.2)

    assert heavy.div(10, 4) == 2.5
    assert heavy.yoy(120, 100) == pytest.approx(0.2)
    assert heavy.yoy(50, -100) == pytest.approx(-1.5)
