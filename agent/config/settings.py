"""运行配置（PART 3 基础层）。

所有路径与开关集中在此，业务模块不读环境变量、不写死路径。
密钥类配置一律从环境变量读，日志中永不打印值。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent import REPO_ROOT


class Settings(BaseSettings):
    """运行时设置。环境变量前缀 ``AUDITOX_``。"""

    model_config = SettingsConfigDict(
        env_prefix="AUDITOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 路径 ----
    repo_root: Path = Field(default=REPO_ROOT, description="技能库仓库根")
    skills_dir: Path | None = Field(default=None, description="默认 repo_root/skills")
    registry_path: Path | None = Field(default=None, description="默认 repo_root/registry/skills.json")
    data_root: Path | None = Field(default=None, description="运行数据根，默认 repo_root/storage")
    workspace_root: Path | None = Field(default=None, description="任务工作区根，默认 repo_root/workspaces")
    artifacts_root: Path | None = Field(default=None, description="产出根，默认 repo_root/artifacts")

    # ---- 数据库 ----
    database_url: str = Field(default="", description="空则用 sqlite:///<data_root>/auditox.db")

    # ---- 运行时约束 ----
    max_steps: int = Field(default=20, ge=1, le=200, description="单任务最大步数（PART 17 C5）")
    max_tool_calls: int = Field(default=500, ge=1, le=10000)
    default_tool_timeout: float = Field(default=30.0, gt=0, le=600)
    allow_network: bool = Field(default=False, description="第一版恒为 False，仅供审计日志记录")
    allow_shell: bool = Field(default=False, description="第一版恒为 False")
    log_level: str = Field(default="INFO")

    # ---- LLM（可选，不配置时走确定性路径）----
    llm_provider: str = Field(default="none", description="none / openai / anthropic / local")
    llm_model: str = Field(default="")
    llm_api_key: str = Field(default="", description="仅从环境读取，禁止写入代码或日志")
    llm_base_url: str = Field(default="")
    llm_timeout: float = Field(default=60.0, gt=0, le=300)

    @field_validator("skills_dir", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if v in ("", None) else v

    # ---- 派生路径（保证单一真相）----
    @property
    def skills_path(self) -> Path:
        return Path(self.skills_dir or (self.repo_root / "skills")).resolve()

    @property
    def registry_file(self) -> Path:
        return Path(self.registry_path or (self.repo_root / "registry" / "skills.json")).resolve()

    @property
    def data_path(self) -> Path:
        return Path(self.data_root or (self.repo_root / "storage")).resolve()

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_root or (self.repo_root / "workspaces")).resolve()

    @property
    def artifacts_path(self) -> Path:
        return Path(self.artifacts_root or (self.repo_root / "artifacts")).resolve()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_file = self.data_path / "auditox.db"
        return "sqlite:///" + db_file.as_posix()

    def ensure_dirs(self) -> None:
        for p in (self.data_path, self.workspace_path, self.artifacts_path):
            p.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """构造设置。测试可传入环境变量覆盖，避免全局单例污染。"""
    return Settings()


__all__ = ["Settings", "get_settings"]
