"""安全层：工作区隔离、权限白名单、脱敏审计日志。"""

from __future__ import annotations

from agent.security.audit_log import (
    JsonLineAuditLogger,
    RedactingFilter,
    configure_logging,
    redact_text,
    redact_value,
)
from agent.security.permissions import PermissionDenied, PermissionPolicy, ShellGuard
from agent.security.workspace import (
    ARTIFACT_DIR,
    BACKUP_DIR,
    LOG_DIR,
    RAW_DIR,
    WORKPAPER_DIR,
    FileRecord,
    SecurityError,
    Workspace,
    sha256_bytes,
    sha256_file,
)

__all__ = [
    "ARTIFACT_DIR",
    "BACKUP_DIR",
    "LOG_DIR",
    "RAW_DIR",
    "WORKPAPER_DIR",
    "FileRecord",
    "JsonLineAuditLogger",
    "PermissionDenied",
    "PermissionPolicy",
    "RedactingFilter",
    "SecurityError",
    "ShellGuard",
    "Workspace",
    "configure_logging",
    "redact_text",
    "redact_value",
    "sha256_bytes",
    "sha256_file",
]
