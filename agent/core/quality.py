"""Procedure-level quality gates used before a plan step can be closed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from agent.models.enums import FailureClass
from agent.models.execution import HumanSubmission, QualityDecision
from agent.models.plan import PlanStep
from agent.models.result import ToolResult


@dataclass(frozen=True)
class QualityContext:
    """All evidence available for one procedure quality decision."""

    task_id: str
    skill_id: str
    step: PlanStep
    tool_results: Sequence[ToolResult]
    human_submission: HumanSubmission | None


class ProcedureQualityGate(Protocol):
    """Extension point for programme-card-specific quality checks."""

    async def evaluate(self, context: QualityContext) -> QualityDecision:
        """Return exactly one of pass, retry, human escalation, or terminal failure."""


class DefaultProcedureQualityGate:
    """Conservative built-in gate.

    Tool failures take precedence over human review. A successful tool run can
    still require human review when either the tool marks its output for review
    or the procedure itself requires human confirmation/judgment.
    """

    async def evaluate(self, context: QualityContext) -> QualityDecision:
        failures = [result for result in context.tool_results if not result.success]
        if failures:
            classes = {result.failure_class or FailureClass.TERMINAL for result in failures}
            details = "；".join(result.error or result.tool_name for result in failures)
            if FailureClass.NEED_HUMAN in classes:
                return QualityDecision.human(f"工具要求人工处理：{details}")
            if FailureClass.RETRYABLE in classes:
                return QualityDecision.retry(f"工具可重试失败：{details}")
            return QualityDecision.fail(f"工具终止失败：{details}")

        requires_review = any(result.requires_human_review for result in context.tool_results)
        if context.human_submission is None and (requires_review or context.step.human_required):
            reason = "工具结果要求人工复核" if requires_review else "程序执行方式要求人工确认或判断"
            return QualityDecision.human(reason)

        if context.human_submission is not None:
            return QualityDecision.pass_(
                f"人工材料已提交：{context.human_submission.actor}"
            )
        return QualityDecision.pass_("工具结果通过程序级质量门")


__all__ = [
    "DefaultProcedureQualityGate",
    "ProcedureQualityGate",
    "QualityContext",
]