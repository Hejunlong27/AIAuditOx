"""工具注册表与能力可用性解析。"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.models.enums import ToolRequirementLevel
from agent.models.tool import ToolRequirement, ToolSpec
from agent.tools.base import ToolHandler


class ToolCapabilityError(RuntimeError):
    """技能所需能力不足，不能安全执行。"""


@dataclass(frozen=True)
class ToolRegistration:
    spec: ToolSpec
    handler: ToolHandler = field(compare=False, repr=False)


@dataclass(frozen=True)
class CapabilityResolution:
    """一组工具能力需求的解析结果。"""

    available: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()
    missing_preferred: tuple[str, ...] = ()
    missing_optional: tuple[str, ...] = ()
    fallbacks: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def can_run(self) -> bool:
        if self.missing_required:
            return False
        return all(name in self.fallbacks for name in self.missing_preferred)

    @property
    def degraded(self) -> bool:
        return bool(self.warnings)


class ToolRegistry:
    """进程级工具注册表；名称唯一，返回工具契约和实现。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler, *, replace: bool = False) -> None:
        if spec.name in self._tools and not replace:
            raise ValueError(f"工具已注册：{spec.name}")
        self._tools[spec.name] = ToolRegistration(spec=spec, handler=handler)

    def get(self, name: str) -> ToolRegistration:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"未注册的工具：{name}") from None

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_names(self) -> list[str]:
        return sorted(self._tools)

    def list_specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in self.list_names()]

    def resolve(self, requirements: list[ToolRequirement]) -> CapabilityResolution:
        available: list[str] = []
        missing_required: list[str] = []
        missing_preferred: list[str] = []
        missing_optional: list[str] = []
        fallbacks: dict[str, str] = {}
        warnings: list[str] = []

        for requirement in requirements:
            if self.has(requirement.name):
                available.append(requirement.name)
                continue
            if requirement.level is ToolRequirementLevel.REQUIRED:
                missing_required.append(requirement.name)
            elif requirement.level is ToolRequirementLevel.PREFERRED:
                if requirement.fallback:
                    missing_preferred.append(requirement.name)
                    fallbacks[requirement.name] = requirement.fallback
                    warnings.append(
                        f"工具 {requirement.name} 不可用，降级使用 {requirement.fallback}"
                    )
                else:
                    missing_preferred.append(requirement.name)
            else:
                missing_optional.append(requirement.name)
                warnings.append(f"可选工具 {requirement.name} 不可用")

        return CapabilityResolution(
            available=tuple(sorted(set(available))),
            missing_required=tuple(sorted(set(missing_required))),
            missing_preferred=tuple(sorted(set(missing_preferred))),
            missing_optional=tuple(sorted(set(missing_optional))),
            fallbacks=fallbacks,
            warnings=tuple(warnings),
        )

    def require(self, requirements: list[ToolRequirement]) -> CapabilityResolution:
        resolution = self.resolve(requirements)
        if not resolution.can_run:
            missing = resolution.missing_required + resolution.missing_preferred
            raise ToolCapabilityError(f"缺少必需工具能力：{', '.join(missing)}")
        return resolution
