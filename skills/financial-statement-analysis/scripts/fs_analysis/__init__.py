"""财务报表分析程序 - 分析性程序底稿生成引擎。"""

__version__ = "1.0.0"

from . import config, profile, loader, analysis, reports, pipeline

__all__ = ["config", "profile", "loader", "analysis", "reports", "pipeline", "__version__"]
