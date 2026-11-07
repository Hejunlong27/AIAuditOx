"""计划与步骤模型（PART 5.2）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from agent.models.base import AuditModel, utcnow
from agent.models.enums import StepStatus


class PlanStep(AuditModel):
    """DAG 中的一个执行节点（对应一张程序卡）。"""

    step_id: str = Field(min_length=1, description="计划内唯一，如 P01")
    procedure_id: str = Field(pattern=r"^[A-Z]\d{1,3}$")
    name: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list, description="依赖的 step_id")
    required_inputs: list[str] = Field(default_factory=list, description="输入资料键（缺失则阻塞）")
    required_tools: list[str] = Field(default_factory=list)
    human_required: bool = False
    condition: str | None = None
    mandatory: bool = False
    status: StepStatus = StepStatus.PENDING
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)
    workpaper_index: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _self_dependency(self) -> "PlanStep":
        if self.step_id in self.dependencies:
            raise ValueError(f"步骤 {self.step_id} 不能依赖自身")
        return self

    @property
    def retryable(self) -> bool:
        return self.retry_count < self.max_retries


class AuditPlan(AuditModel):
    """一次任务的完整执行计划。"""

    plan_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    skill_version: str = Field(default="")
    steps: list[PlanStep] = Field(default_factory=list)
    execution_order: list[list[str]] = Field(
        default_factory=list,
        description="拓扑分层：同一层可并行，层间串行",
    )
    missing_inputs: list[str] = Field(default_factory=list)
    human_tasks: list[str] = Field(default_factory=list, description="需人工参与的 step_id")
    conditional_tasks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    validated: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_step_ids(self) -> "AuditPlan":
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            dupes = sorted({x for x in ids if ids.count(x) > 1})
            raise ValueError(f"step_id 重复：{dupes}")
        return self

    def step(self, step_id: str) -> PlanStep:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        raise KeyError(f"计划中不存在步骤 {step_id}")

    @property
    def mandatory_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.mandatory]
