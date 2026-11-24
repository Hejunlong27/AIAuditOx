"""Skill-specific adapters that convert normalized task inputs into tool calls."""

from agent.adapters.base import AdapterError, AutoToolCallProvider, SkillAdapter
from agent.adapters.registry import AdapterRegistry

__all__ = [
    "AdapterError",
    "AdapterRegistry",
    "AutoToolCallProvider",
    "SkillAdapter",
]
