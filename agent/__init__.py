"""AIAuditOx 审计 Agent 运行时。

设计约束（与本仓库 AGENTS.md 一致）：
- 运行时逻辑不写入 ``skills/``，技能层保持纯内容，脱离运行时也能被任意 agent 使用。
- 金额一律使用 Decimal，禁止 float 参与金额运算。
- 所有外部调用必须有显式超时；所有自主循环必须有步数上限。
"""

from __future__ import annotations

__version__ = "0.1.0"

# 运行时根目录：本包所在仓库根（agent/ 的上一级）
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent

__all__ = ["REPO_ROOT", "__version__"]
