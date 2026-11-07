"""模型公共基类与工具函数。

约定：
- 所有模型禁用多余字段（``extra="forbid"``），防止上游 DSL 结构漂移时静默丢字段。
- 所有时间戳统一 UTC 且带时区，禁止 naive datetime。
- 金额一律 ``Decimal``，禁止 float。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer

# 金额：序列化为字符串，避免 JSON 浮点误差（前端/外部 agent 侧再解析）
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]

# 百分比：0~100 的 Decimal，同样序列化为字符串
Percent = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]


def utcnow() -> datetime:
    """当前 UTC 时间（带时区）。全库唯一时间来源，便于测试冻结。"""
    return datetime.now(timezone.utc)


def to_money(value: Any) -> Decimal:
    """把多种输入安全转成 Decimal。

    支持 int / str / Decimal；float 先经 repr 再转，避免 0.1 的二进制误差扩散。
    非法输入抛 ValueError，不做静默兜底——金额算错比报错严重得多。
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError(f"布尔值不能作为金额：{value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("，", "")
        if not text:
            raise ValueError("空字符串不能作为金额")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"无法解析为金额：{value!r}") from exc
    raise ValueError(f"不支持的金额类型：{type(value).__name__}")


class AuditModel(BaseModel):
    """所有运行时模型的基类。"""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        frozen=False,
    )
