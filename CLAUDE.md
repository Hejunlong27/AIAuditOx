# CLAUDE.md

本仓库的 agent 指令统一维护在 **[AGENTS.md](AGENTS.md)**，本文件只做入口转发，不重复内容。

请先完整读取 `AGENTS.md`，再按其中「调用协议」执行任务。

补充给 Claude Code 的两点：

1. **技能安装路径**：`~/.claude/skills/`。若要使用本仓库技能，先 `cp -r skills/* ~/.claude/skills/`，或直接在仓库内工作并相对读取 `skills/<id>/SKILL.md`。
2. **强制前置**：任何要产出审计底稿的任务，先读 `skills/auditox-wp-standard/SKILL.md`，再读科目技能。跳过制式规范会导致底稿结构不合规。
