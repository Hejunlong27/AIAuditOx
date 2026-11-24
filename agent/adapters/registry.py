"""Registry of deterministic skill adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from agent.adapters.bank_deposits import BankDepositsAdapter
from agent.adapters.base import AdapterError, AutoToolCallProvider, SkillAdapter


class AdapterRegistry:
    """Create the appropriate adapter for a skill id."""

    def __init__(self) -> None:
        self._factories = {
            BankDepositsAdapter.skill_id: BankDepositsAdapter,
        }

    def build(self, skill_id: str, inputs: Mapping[str, Path]) -> AutoToolCallProvider:
        factory = self._factories.get(skill_id)
        if factory is None:
            available = "、".join(sorted(self._factories))
            raise AdapterError(
                f"技能 {skill_id!r} 尚无自动输入适配器；已支持：{available}"
            )
        adapter: SkillAdapter = factory(inputs)
        return AutoToolCallProvider(adapter)

    def supported_skills(self) -> list[str]:
        return sorted(self._factories)


__all__ = ["AdapterError", "AdapterRegistry", "AutoToolCallProvider"]
