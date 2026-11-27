# 审小牛 AIAuditOx HARNESS

> 一切审计程序皆可 Skill 化。

审小牛把审计程序逻辑、确定性执行工具、项目数据和复核证据组织在一个本地 AI Audit Harness 中。它既能作为审计人员的工作台，也能作为其他 Agent 可调用的本地审计能力层。

## 核心理念

| 层 | 责任 |
| --- | --- |
| **Skill** | 说明“这项审计程序应该怎么做”：目标、输入、步骤、判断规则、证据要求和底稿结构。 |
| **通用工具** | 执行“具体怎么做”：文件解析、数据库操作、确定性计算、OCR、图像处理、文档生成、模型调用。 |
| **Audit Runtime** | 保存项目、账套、任务、计划、证据、审批、底稿和修订记录。 |
| **Trace Ledger** | 对 Agent 与工具执行追加哈希链记录，让底稿来源、输入摘要和输出摘要可核验。 |
| **MCP** | 把本地审计能力暴露给其他 Agent 或编排系统，避免重复建设。 |

## 当前能力

- **引导审计**：从财务报表和账套资料出发，组织审计计划、重要性、程序、控制测试、实质性底稿和复核包。
- **对话审计**：围绕报表、风险、程序、资料缺口和复核发现进行连续会话。
- **本地模型**：检测硬件，推荐 Ollama 模型，支持本地模型启动、关闭、自定义 OpenAI 兼容地址和 GGUF 导入。
- **技能中心**：读取本地 SkillHub 镜像，查看 `SKILL.md`，按需安装和卸载技能。
- **审计工具**：项目与资料登记、任务执行、审批、底稿导出、证据与修订记录查询。
- **留痕**：底稿包含程序明细、证据清单、修订记录和 SHA-256 摘要；Harness 工具调用追加 JSONL 哈希链。
- **MCP**：本机 `http://127.0.0.1:11436/mcp` 提供技能、项目、底稿和留痕工具，供其他 Agent 调用。

## 目录

```text
auditox/                         审小牛产品配置、文档和启动脚本
packages/client/ui-brand-auditox/ 品牌、首页、审计档案
packages/client/ui-auditox-workbench/ 本地模型与技能中心
packages/extensions/tool-auditox-runtime/ 审计 Runtime 工具桥与 Trace Ledger
packages/extensions/auditox-local-services/ 本地模型、SkillHub、MCP 服务
```

## 启动

```powershell
cd auditox
.\build.ps1
.\run.ps1
```

`run.ps1` 默认使用同工作区的旧版 AuditOx Runtime（`..\agent-runtime`），也可以通过 `AUDITOX_RUNTIME_URL` 指向其他本地 Runtime。

旧版运行时已完整归档在 GitHub 分支：

```text
archive/legacy-runtime-92e03237
```

它不是被删除，而是从新的 `main` 产品代码中分离出来，继续通过 Runtime 桥和 MCP 供 Harness 使用。

## 安全边界

- 客户资料默认只在本机和本地模型中流转。
- 金额、勾稽、抽样和汇总必须由确定性工具执行。
- 模型输出标记为分析草稿，不替代原始证据、项目组判断和签字结论。
- MCP 默认仅绑定回环地址；设置 `AUDITOX_MCP_TOKEN` 后要求 Bearer Token。
- 云模型和外部 MCP 客户端必须由用户明确配置。

## 开发文档

- [启动与配置](./auditox/README.zh.md)
- [Skill × Tool 融合架构](./auditox/SKILL-TOOL-ARCHITECTURE.zh.md)
- [财务数据包与项目数据库](./auditox/DATA-PACKAGE-ARCHITECTURE.zh.md)
- [MCP 接口](./auditox/MCP.zh.md)

## 开源协议与致谢

根目录 [LICENSE](./LICENSE) 保持上游原始 MIT 协议不变。上游开源贡献只在许可证、第三方声明和 [开源致谢](./ACKNOWLEDGEMENTS.zh.md) 中保留，不构成审小牛对外产品品牌。
