"""人工审批模型（PART 5.5 / PART 12）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from agent.models.base import AuditModel, utcnow
from agent.models.enums import ApprovalStatus


class ApprovalRequest(AuditModel):
    """人工待办/审批单。

    为什么不用一个 bool 表示"审批完成"：审计底稿的复核轨迹需要
    谁、何时、基于什么证据、写了什么意见，bool 无法承载，也无法应对
    "同一程序被拒后重新提交"的场景。
    """

    approval_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    procedure_id: str = Field(pattern=r"^[A-Z]\d{1,3}$")
    reason: str = Field(min_length=1, description="为什么需要人工介入")
    requested_action: str = Field(min_length=1, description="要求人工做什么")
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: str | None = None
    comment: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list, description="人工上传的证据文件路径")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _decided_needs_actor(self) -> "ApprovalRequest":
        # 已决的审批必须有操作人，否则就是"系统自己批了自己"
        if self.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            if not self.approved_by:
                raise ValueError(f"审批已{self.status.value}但未记录操作人")
        return self

    @property
    def pending(self) -> bool:
        return self.status is ApprovalStatus.PENDING
