"""技能层：注册表、加载器、解析器、路由。

纯只读层——运行时通过本包发现与理解技能，绝不修改 ``skills/`` 内容。
"""

from __future__ import annotations

from agent.skills.loader import LoadedSkill, SkillLoader
from agent.skills.parser import (
    DSLParser,
    DispatchRow,
    DispatchTableParser,
    infer_policy,
    merge_procedure,
    parse_frontmatter,
)
from agent.skills.registry import SkillEntry, SkillRegistry
from agent.skills.router import RouteCandidate, RouteDecision, SkillRouter

__all__ = [
    "DSLParser",
    "DispatchRow",
    "DispatchTableParser",
    "LoadedSkill",
    "RouteCandidate",
    "RouteDecision",
    "SkillEntry",
    "SkillLoader",
    "SkillRegistry",
    "SkillRouter",
    "infer_policy",
    "merge_procedure",
    "parse_frontmatter",
]
