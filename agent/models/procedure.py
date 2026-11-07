"""审计程序定义与执行策略（PART 5.3 / PART 11.3）。

真实技能库里的 ``dsl.json`` 只提供 ``id / name / tools / human``，
认定、产出索引、强制标记、依赖关系都要从 SKILL.md 分派表与运行时配置补齐。
本模块的 :class:`ProcedureDefinition` 是**三源合并后的结果**，
``sources`` 记录每个字段来自哪个源，保证可追溯、可解释。
"""

from __future__ import annotations

from pydantic import Field, model_validator

from agent.models.base import AuditModel
from agent.models.enums import ConflictSeverity, ExecutionMode


class ExecutionPolicy(AuditModel):
    """统一执行策略（PART 11.3 第 4 条）。

    设计要点：这里**只做加法不做减法**。任一来源认为需要人工，
    本对象就必须体现人工要求，避免"用 DSL 的 human=false 覆盖 SKILL.md 的
    人工判断要求"这类降级。
    """

    automated_execution: bool = False
    human_confirmation: bool = False
    human_judgment: bool = False
    mandatory: bool = False
    conditional: bool = False
    mode: ExecutionMode = ExecutionMode.AUTO
    rationale: list[str] = Field(default_factory=list, description="策略推导依据，逐条可读")

    @property
    def requires_human(self) -> bool:
        """是否必须有人参与（确认或判断任一）。"""
        return self.human_confirmation or self.human_judgment

    @model_validator(mode="after")
    def _human_mode_consistency(self) -> "ExecutionPolicy":
        # 有人在环却标 AUTO 属自相矛盾，直接拒收，避免下游误判
        if self.requires_human and self.mode is ExecutionMode.AUTO:
            raise ValueError(
                "policy 要求人工确认/判断，但 mode=AUTO，自相矛盾；"
                "请设为 AUTO_WITH_CONFIRM / AUTO_WITH_JUDGMENT / HUMAN_LED"
            )
        return self


class ProcedureDefinition(AuditModel):
    """一条审计程序的规范化定义。"""

    id: str = Field(pattern=r"^[A-Z]\d{1,3}$", description="程序 ID，如 P01；规范型包用 G0/G1")
    name: str = Field(min_length=1)
    description: str = ""
    tools: list[str] = Field(default_factory=list, description="该程序应调用的确定性工具名")
    assertions: list[str] = Field(default_factory=list, description="认定编码 E/C/A/V/P")
    execution_policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    dependencies: list[str] = Field(default_factory=list, description="必须先完成的程序 ID")
    mandatory: bool = False
    conditional: bool = False
    condition: str | None = Field(default=None, description="条件程序启用条件（自然语言，来自 SKILL.md）")
    source: str = Field(default="", description="程序库来源，如 Z1002 程序2")
    workpaper_index: str | None = Field(default=None, description="产出底稿索引号，如 Z-1-2-04")
    procedure_doc: str | None = Field(default=None, description="程序卡 Markdown 相对路径")
    skill_id: str = ""
    skill_version: str = ""
    sources: dict[str, str] = Field(
        default_factory=dict,
        description="字段级来源标记：字段名 → dsl / skill_md / runtime_config / derived",
    )

    @model_validator(mode="after")
    def _id_not_self_dependent(self) -> "ProcedureDefinition":
        if self.id in self.dependencies:
            raise ValueError(f"程序 {self.id} 不能依赖自身")
        return self


class ConflictRecord(AuditModel):
    """三源冲突记录（PART 11.3 第 3 条：输出冲突报告）。"""

    skill_id: str
    procedure_id: str
    field: str
    values: dict[str, str] = Field(default_factory=dict, description="来源名 → 取值")
    resolved: str = ""
    severity: ConflictSeverity = ConflictSeverity.WARNING
    note: str = ""
