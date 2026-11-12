"""运行时枚举定义。

所有状态值均为 ``str`` 枚举，便于直接落库（SQLite 存 TEXT）与 JSON 序列化。
"""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """任务状态机状态（任务书 PART 5.1）。"""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    WAITING_INPUT = "WAITING_INPUT"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """计划步骤状态。

    ``HUMAN_COMPLETED`` 与 ``VERIFIED`` 分开是为了满足 PART 12：
    人工程序不能用一个布尔字段说"已完成"，必须区分
    「人工提交了材料」和「材料通过质量检查并正式关闭」。
    """

    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    HUMAN_COMPLETED = "HUMAN_COMPLETED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    SKIPPED_NOT_APPLICABLE = "SKIPPED_NOT_APPLICABLE"
    FAILED = "FAILED"


class ApprovalStatus(str, Enum):
    """人工审批单状态。"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class EvidenceKind(str, Enum):
    """证据类型。区分"算出来的"与"人交上来的"，避免模型推测混入客观证据。"""

    TOOL_OUTPUT = "TOOL_OUTPUT"
    HUMAN_ATTACHMENT = "HUMAN_ATTACHMENT"
    RULE_RESULT = "RULE_RESULT"
    SOURCE_FILE = "SOURCE_FILE"


class EvidenceStatus(str, Enum):
    """证据校验状态。"""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ToolRiskLevel(str, Enum):
    """工具风险分级，决定是否需要人工二次确认（PART 20）。"""

    READ_ONLY = "READ_ONLY"
    LOCAL_WRITE = "LOCAL_WRITE"
    EXTERNAL_IO = "EXTERNAL_IO"
    DESTRUCTIVE = "DESTRUCTIVE"


class FailureClass(str, Enum):
    """异常分类，驱动不同处理路径（PART 9 加固要求）。"""

    RETRYABLE = "RETRYABLE"
    NEED_HUMAN = "NEED_HUMAN"
    TERMINAL = "TERMINAL"


class ExecutionMode(str, Enum):
    """程序执行方式。由 SKILL.md「执行方式」列归一化而来。"""

    AUTO = "AUTO"
    AUTO_WITH_CONFIRM = "AUTO_WITH_CONFIRM"
    AUTO_WITH_JUDGMENT = "AUTO_WITH_JUDGMENT"
    HUMAN_LED = "HUMAN_LED"
    HUMAN_ONLY = "HUMAN_ONLY"


class ConflictSeverity(str, Enum):
    """DSL / SKILL.md / 配置三源冲突的严重度。"""

    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"

class ToolRequirementLevel(str, Enum):
    """技能对工具能力的依赖强度，用于双模式降级。"""

    REQUIRED = "required"
    PREFERRED = "preferred"
    OPTIONAL = "optional"
