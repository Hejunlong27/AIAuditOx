# 审小牛AIAuditOx HARNESS

> 一切审计程序皆可 Skill 化。

审小牛是一套面向审计项目组的本地 AI Audit Harness。它把 Skill、通用工具、审计 Runtime、项目数据和可核验留痕组合成一套可复用的审计能力层。

## 产品界面

- 冷白工作区与深色模式，侧栏按“通用工具、审计自动化、本地模型、技能中心”组织。
- 首页展示审计路径：项目资料 → 审计计划 → 控制测试 → 实质程序 → 项目复核。
- 支持引导审计与对话审计两种模式。
- 本地模型可直接启动、关闭、切换地址和导入 GGUF。
- 不设置首次登录门槛，模型和 API 配置由用户主动完成。

## 核心能力

### Skill × Tool

- Skill 说明审计程序的目标、输入、步骤、判断、证据和底稿要求。
- Tool 执行文件、数据、计算、OCR、图像、文档和模型操作。
- 审计 Runtime 保存项目、任务、审批、证据、底稿和修订记录。
- Trace Ledger 对 Harness 工具调用追加哈希链记录。

详见 [SKILL-TOOL-ARCHITECTURE.zh.md](./SKILL-TOOL-ARCHITECTURE.zh.md)。

### 本地模型

- CPU、内存、磁盘、显卡检测；
- Ollama 安装与运行状态检测；
- 启动、关闭本地推理服务；
- 按硬件适配度推荐模型；
- 一键安装配置与模型下载；
- 自定义 OpenAI 兼容地址和 API Key；
- 本机模型网关；
- GGUF 上传导入或本机路径导入；
- 国内镜像检索链接，并明确区分其与 Ollama 拉取源。

### 技能中心

- 读取本地 SkillHub 镜像；
- 技能列表、分类和搜索；
- 查看 `SKILL.md`；
- 按需安装和卸载技能；
- 将技能复制到 Harness 本地技能目录。

### MCP

本机 MCP 入口：

```text
http://127.0.0.1:11436/mcp
```

支持技能查询、项目查询、底稿导出、工作底稿留痕查询和引导阶段执行。详见 [MCP.zh.md](./MCP.zh.md)。

## 数据架构

财务数据包、项目数据库、字段映射、底稿和证据血缘见：

[DATA-PACKAGE-ARCHITECTURE.zh.md](./DATA-PACKAGE-ARCHITECTURE.zh.md)

旧版 Runtime 已归档在分支 `archive/legacy-runtime-92e03237`，通过 `tool-auditox-runtime` 和 MCP 继续为 Harness 提供能力。

## 启动

```powershell
cd auditox
.\build.ps1
.\run.ps1
```

## 边界

- 客户文件默认只在本机流转。
- 金额、勾稽和计算由确定性工具完成，模型只做分析、解释和草稿。
- 模型输出不得替代原始证据、项目组判断或签字结论。
- 对外发布、网盘上传和 SkillHub 上架仍需项目负责人确认。

## 开源协议

本仓库产品代码与文档采用 [AIAuditOx 非商业许可 1.0](../LICENSE)。禁止商业使用、转售、去除署名或冒充来源；商业授权需与作者单独协商。上游第三方组件继续适用各自许可证，见 [ACKNOWLEDGEMENTS.zh.md](../ACKNOWLEDGEMENTS.zh.md) 和 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
