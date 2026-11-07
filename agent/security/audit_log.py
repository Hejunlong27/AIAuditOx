"""结构化审计日志与敏感信息脱敏（PART 20 第 5、12 条 / PART 24 第 7 条）。

日志要求：
- 结构化（JSON Lines），可被机器消费，不写自然语言长句；
- 每条带 ``trace_id``，能串起一次任务的完整链路；
- 落盘前脱敏：账号、身份证号、手机号、客户名称不进入普通日志。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

# 脱敏规则：按"识别特征明确"优先，避免误伤金额与日期
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # 银行账号：16~19 位连续数字（含中间空格）
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4,7}\b"), "[ACCT]"),
    # 身份证：18 位（末位可为 X）
    (re.compile(r"\b\d{17}[\dXx]\b"), "[ID]"),
    # 手机号
    (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE]"),
    # 邮箱
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
)

# 键名命中即整体替换（不看值长什么样）
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "secret",
        "api_key",
        "apikey",
        "access_key",
        "authorization",
        "cookie",
        "client_name",
        "customer_name",
        "被审计单位",
    }
)


def redact_text(text: str) -> str:
    """对自由文本做模式化脱敏。"""
    out = text
    for pattern, repl in _PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_value(value: Any) -> Any:
    """递归脱敏任意可 JSON 化结构。"""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if str(k).lower() in _SENSITIVE_KEYS else redact_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    return value


class JsonLineAuditLogger:
    """JSON Lines 审计日志写入器。

    每次 ``emit`` 一行，立即 flush —— 审计日志的价值在于"事故后还有"，
    不能留在缓冲区里等着丢。
    """

    def __init__(self, path: Path, *, trace_id: str = "") -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_id = trace_id

    def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        from agent.models.base import utcnow

        record = {
            "ts": utcnow().isoformat(),
            "trace_id": fields.pop("trace_id", self.trace_id),
            "event": event,
        }
        record.update(redact_value(fields))
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
        return record


class RedactingFilter(logging.Filter):
    """给标准 logging 加脱敏。用于第三方库日志（uvicorn 等）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            record.args = tuple(redact_value(a) for a in record.args)
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """进程级日志配置：统一格式 + 脱敏过滤器。幂等。"""
    root = logging.getLogger()
    if any(isinstance(f, RedactingFilter) for f in root.filters):
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    handler.addFilter(RedactingFilter())
    root.handlers = [handler]
    root.addFilter(RedactingFilter())
    root.setLevel(level)
