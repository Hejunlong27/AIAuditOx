"""Build executable audit plans from validated procedure definitions."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from agent.models.enums import ExecutionMode, StepStatus
from agent.models.plan import AuditPlan, PlanStep
from agent.planning.dag import topological_layers
from agent.planning.validator import SkillValidationResult, SkillValidator


class PlanningError(RuntimeError):
    """The validated procedures cannot be converted into a safe plan."""


class AuditPlanner:
    """Topological planner for one skill execution."""

    DEFAULT_CONFIG_FILES = {
        "z-1-2-bank-deposits": "bank_deposits.yaml",
    }

    def __init__(
        self,
        validator: SkillValidator,
        *,
        config_root: Path | None = None,
        config_files: dict[str, str] | None = None,
    ) -> None:
        self.validator = validator
        self.config_root = Path(config_root or (Path(__file__).resolve().parents[1] / "config" / "procedures"))
        self.config_files = {**self.DEFAULT_CONFIG_FILES, **(config_files or {})}

    def build_plan(
        self,
        *,
        task_id: str,
        skill_id: str,
        provided_inputs: set[str] | None = None,
        active_conditions: set[str] | None = None,
    ) -> AuditPlan:
        provided = set(provided_inputs or ())
        active = set(active_conditions or ())
        filename = self.config_files.get(skill_id)
        if filename is None:
            raise PlanningError(f"技能 {skill_id} 没有 runtime procedure config")
        config_path = self.config_root / filename
        if not config_path.is_file():
            raise PlanningError(f"程序依赖配置不存在：{config_path}")

        validation = self.validator.validate(skill_id, config_path)
        steps: list[PlanStep] = []
        missing_all: set[str] = set()
        human_tasks: list[str] = []
        conditional_tasks: list[str] = []
        active_auto: dict[str, list[str]] = {}

        for procedure_id, procedure in validation.procedures.items():
            condition_enabled = procedure.enabled_when is None or procedure_id in active
            missing = sorted(set(procedure.required_inputs) - provided)
            if procedure.enabled_when is not None:
                conditional_tasks.append(procedure_id)
            if not condition_enabled:
                status = StepStatus.SKIPPED_NOT_APPLICABLE
                note = f"条件未激活：{procedure.enabled_when}"
            elif missing:
                missing_all.update(missing)
                status = StepStatus.BLOCKED
                note = "缺少输入：" + "、".join(missing)
            elif procedure.execution_policy.mode in (ExecutionMode.HUMAN_LED, ExecutionMode.HUMAN_ONLY):
                status = StepStatus.WAITING_HUMAN
                note = "人工主导程序"
            else:
                status = StepStatus.PENDING
                note = ""

            human = procedure.execution_policy.requires_human
            if condition_enabled and human:
                human_tasks.append(procedure_id)

            steps.append(
                PlanStep(
                    step_id=procedure_id,
                    procedure_id=procedure_id,
                    name=procedure.name,
                    dependencies=list(procedure.dependencies),
                    required_inputs=list(procedure.required_inputs),
                    missing_inputs=missing,
                    required_tools=list(procedure.tools),
                    human_required=human,
                    execution_mode=procedure.execution_policy.mode,
                    condition=procedure.enabled_when,
                    mandatory=procedure.mandatory or procedure.execution_policy.mandatory,
                    status=status,
                    workpaper_index=procedure.workpaper_index,
                    notes=note,
                )
            )

            if (
                condition_enabled
                and procedure.execution_policy.mode not in (
                    ExecutionMode.HUMAN_LED,
                    ExecutionMode.HUMAN_ONLY,
                )
            ):
                active_auto[procedure_id] = list(procedure.dependencies)

        for node, deps in active_auto.items():
            outside = [dep for dep in deps if dep not in active_auto]
            if outside:
                raise PlanningError(
                    f"自动程序 {node} 依赖了未进入自动执行图的程序：{', '.join(outside)}"
                )
        try:
            execution_order = topological_layers(active_auto)
        except ValueError as exc:
            raise PlanningError(str(exc)) from exc

        warnings = list(validation.warnings)
        if missing_all:
            warnings.append("存在未提供输入，相关步骤已标记 BLOCKED")
        skipped_conditions = sorted(set(conditional_tasks) - active)
        if skipped_conditions:
            warnings.append("条件程序未激活：" + "、".join(skipped_conditions))

        return AuditPlan(
            plan_id=f"PLAN-{uuid4().hex[:12]}",
            task_id=task_id,
            skill_id=skill_id,
            skill_version=validation.skill_version,
            steps=steps,
            execution_order=execution_order,
            missing_inputs=sorted(missing_all),
            human_tasks=human_tasks,
            conditional_tasks=conditional_tasks,
            validated=True,
            warnings=warnings,
        )
