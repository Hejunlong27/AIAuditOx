"""证据模型（PART 5.4 / PART 13）。

证据的第一原则：**每个审计数字都必须能沿着证据链回到源文件**。
因此 SourceRef 与 ResultRef 都强制记录 sha256，缺失即校验失败。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from agent.models.base import AuditModel, utcnow
from agent.models.enums import EvidenceKind, EvidenceStatus

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceRef(AuditModel):
    """输入侧溯源：哪个文件的哪一块。"""

    file: str = Field(min_length=1)
    sha256: str = Field(description="文件内容 SHA256，64 位小写十六进制")
    sheet: str | None = Field(default=None, description="Excel 工作表名")
    page: int | None = Field(default=None, ge=1, description="PDF 页码，从 1 开始")
    row_range: str | None = Field(default=None, description="行范围，如 '5-28'")
    columns: list[str] = Field(default_factory=list, description="使用的列名")
    extracted_at: datetime = Field(default_factory=utcnow)

    @field_validator("sha256")
    @classmethod
    def _sha256_format(cls, value: str) -> str:
        v = value.strip().lower()
        if not _SHA256_RE.match(v):
            raise ValueError("sha256 必须是 64 位小写十六进制")
        return v


class ResultRef(AuditModel):
    """输出侧溯源：工具产出了什么。"""

    file: str | None = Field(default=None, description="产出文件；纯内存结果可为空")
    sha256: str | None = None
    inline: dict[str, Any] | None = Field(default=None, description="无文件时的内联结果摘要")

    @field_validator("sha256")
    @classmethod
    def _sha256_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        v = value.strip().lower()
        if not _SHA256_RE.match(v):
            raise ValueError("sha256 必须是 64 位小写十六进制")
        return v


class Evidence(AuditModel):
    """一条可追溯的审计证据。"""

    evidence_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    procedure_id: str = Field(pattern=r"^[A-Z]\d{1,3}$")
    kind: EvidenceKind = EvidenceKind.TOOL_OUTPUT
    status: EvidenceStatus = EvidenceStatus.UNVERIFIED

    # 兼容任务书 PART 5.4 的扁平字段；结构化信息在 source / output 中
    source_file: str | None = None
    source_sha256: str | None = None
    tool_name: str = Field(min_length=1)
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    result_file: str | None = None
    result_sha256: str | None = None

    source: SourceRef | None = None
    output: ResultRef | None = None

    conclusion: str = ""
    requires_human_review: bool = False
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = Field(default="runtime", max_length=128)

    @property
    def traceable(self) -> bool:
        """是否具备完整证据链：必须能指回源文件哈希，且能说明产出。

        纯人工附件（HUMAN_ATTACHMENT）也必须有文件哈希——人交上来的
        扫描件本身就是源文件。
        """
        has_source = bool(self.source_file and self.source_sha256) or bool(
            self.source and self.source.sha256
        )
        has_output = bool(self.result_file or self.output)
        return has_source and has_output
