[中文](./README.md) | [English](./README.en.md)

# [AIAuditOx](https://github.com/Hejunlong27/AIAuditOx)

> 一切审计程序皆可 Skill 化。

审小牛 AIAuditOx HARNESS 是一套面向审计项目组的本地 AI Audit Harness。它把审计程序逻辑、确定性执行工具、项目数据库、证据链和复核留痕组织在同一个工作区中，既能作为审计人员的工作台，也能作为其他 Agent 可调用的本地审计能力层。

## 为什么做

传统审计软件通常把程序逻辑、数据处理和界面写死在一起，新增一个审计程序需要重新开发整条流程。审小牛把能力拆成稳定边界：

- **Skill** 负责“这项审计程序应该怎么做”；
- **通用工具** 负责“具体用什么工具执行”；
- **Audit Runtime** 负责保存项目事实、任务状态、证据和底稿；
- **Trace Ledger** 负责证明执行过程和版本；
- **MCP** 负责让其他 Agent 复用这些能力。

这样，新增审计能力时可以先扩展 Skill，再复用或新增确定性工具，而不必重新建设一套应用。

## 核心架构

```text
财务报表 / 账套 / 票据 / 合同 / 原始文件
                  │
                  ▼
        Skill：程序目标、输入、判断、证据、底稿契约
                  │
                  ▼
        Agent：选择 Skill、编排阶段、请求人工确认
                  │
                  ▼
        Tools：解析、数据库、计算、OCR、图像、文档、模型
                  │
                  ▼
        Audit Runtime：项目、任务、审批、底稿、修订
                  │
                  ▼
        Trace Ledger：输入摘要、输出摘要、哈希链
                  │
                  ├── 人工复核 / 项目负责人在底稿与页面复核
                  └── MCP：其他 Agent / 编排系统按权限调用
```

## 当前能力

### 审计工作流

- 引导审计：报表与账套资料 → 审计计划 → 重要性 → 审计程序 → 穿行与控制测试 → 实质性底稿 → 资料缺口 → 复核包。
- 对话审计：围绕审计问题、风险判断、资料缺口、复核发现进行连续会话。
- 审计档案：在会话右侧查看审计阶段、工作边界和留痕说明。

### 技能中心

- 读取本地 SkillHub 镜像；
- 搜索、分类和查看技能；
- 展开 `SKILL.md`；
- 按需安装、卸载到本地 Harness 技能目录；
- 技能事实源保持独立，界面只消费镜像。

### 本地模型

- 检测 CPU、内存、磁盘、NVIDIA/Windows 显卡；
- 检测 Ollama 安装和运行状态；
- 一键配置 Ollama、启动或关闭本地推理；
- 推荐适配本机硬件的轻量语言模型和视觉模型；
- 自定义 OpenAI 兼容地址、模型名和可选 API Key；
- 通过本地网关把当前模型接入 Agent；
- 上传 GGUF 或从本机路径导入已下载模型。

### 审计工具

- 项目、资料和任务管理；
- 审计任务执行；
- 人工审批与复核决定；
- 工作底稿生成；
- 产物、证据和修订记录查询；
- 工作底稿 Trace 查询。

### 留痕

底稿文件本身包含：

- 程序明细；
- 证据清单；
- 修订记录；
- 编制人、复核人和状态；
- 文件 SHA-256。

Harness 额外写入 append-only JSONL Trace Ledger：

- 项目、任务、技能和工具身份；
- 输入摘要与输出摘要；
- 成功或失败状态；
- 上一条记录哈希；
- 本条记录哈希。

> 当前是防篡改的本地哈希链，不等同于外部公证、可信时间戳或 WORM 存储。若用于正式证据归档，应继续增加电子签章和归档锁定。

## MCP 能力

默认入口：

```text
http://127.0.0.1:11436/mcp
```

已经提供：

| 工具 | 用途 |
| --- | --- |
| `auditox_harness_status` | Harness、模型网关、技能源和 Runtime 状态 |
| `auditox_skill_list` | 列出本地技能 |
| `auditox_skill_read` | 读取指定 `SKILL.md` |
| `auditox_runtime_health` | 检查审计 Runtime |
| `auditox_project_list` | 列出审计项目 |
| `auditox_workpaper_trace` | 返回任务、计划、产物、审批和留痕 |
| `auditox_export_workpaper` | 生成可复核底稿 |
| `auditox_guided_stage` | 推进引导审计阶段 |

详细配置见 [auditox/MCP.zh.md](./auditox/MCP.zh.md)。

## 快速启动

### 前置环境

- Windows 10/11、macOS 或 Linux；
- Node.js `^24.22.3` 或 `>=26.13.1`；
- pnpm `11.28.5`；
- 旧版 AuditOx Runtime 的 Python 环境（默认从工作区 `../agent-runtime` 读取）。

### 启动

```powershell
cd auditox
.\build.ps1
.\run.ps1
```

默认界面：

```text
http://127.0.0.1:3080
```

默认审计 Runtime：

```text
http://127.0.0.1:8765
```

默认本地模型网关：

```text
http://127.0.0.1:11435/v1
```

### 常用环境变量

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `AUDITOX_RUNTIME_URL` | 旧版审计 Runtime 地址 | `http://127.0.0.1:8765` |
| `AUDITOX_SKILL_LIBRARY` | 技能镜像目录 | `../skill-library` |
| `AUDITOX_MCP_PORT` | MCP 服务端口 | `11436` |
| `AUDITOX_MCP_TOKEN` | MCP Bearer Token，可选 | 空 |
| `AUDITOX_TRACE_FILE` | Trace Ledger 文件 | `$DSH_HOME/auditox-traces/workpapers.jsonl` |
| `AUDITOX_MODEL_GATEWAY_PORT` | 本地模型网关端口 | `11435` |

## 目录结构

```text
auditox/
  README.zh.md                    启动与配置
  SKILL-TOOL-ARCHITECTURE.zh.md   Skill × Tool 融合架构
  DATA-PACKAGE-ARCHITECTURE.zh.md 项目数据库与数据血缘
  MCP.zh.md                       MCP 使用说明
  cordis.patch.yml                审小牛运行配置
  build.ps1 / run.ps1             构建与启动

packages/client/ui-brand-auditox/
  品牌、官网配色、首页、审计档案

packages/client/ui-auditox-workbench/
  本地模型、技能中心、本地状态开关

packages/extensions/tool-auditox-runtime/
  项目、任务、审批、底稿和 Trace 工具桥

packages/extensions/auditox-local-services/
  本地模型、SkillHub、MCP 服务

packages/extensions/auditox-trace/
  append-only 审计执行留痕账本
```

## 旧版 Runtime

上一版 Runtime 完整保存在 GitHub 分支：

```text
archive/legacy-runtime-92e03237
```

它不是被删除，而是从新的 `main` 产品代码中分离出来，继续通过 Runtime Bridge 和 MCP 提供项目、任务、审批、底稿和修订能力。

## 开发与验证

```powershell
# 全量构建
npx pnpm@11.28.5 run build

# 类型检查
npx pnpm@11.28.5 run typecheck

# MCP / Trace 定向测试
npx pnpm@11.28.5 exec vitest run `
  packages/extensions/auditox-local-services/tests/mcp.spec.ts `
  packages/extensions/tool-auditox-runtime/tests/trace.spec.ts

# 代码检查
npx pnpm@11.28.5 exec oxlint packages/extensions/auditox-local-services/src `
  packages/extensions/auditox-trace/src `
  packages/extensions/tool-auditox-runtime/src
```

## 安全边界

- 客户文件默认只在本机和本地模型流转。
- 金额、勾稽、抽样、汇总和索引号必须由确定性工具完成。
- 模型输出标记为分析草稿，不替代原始证据、审计判断和签字结论。
- MCP 默认只绑定回环地址；跨 Agent 使用时应配置 Bearer Token。
- 云模型、外部 MCP 和任何外部上传必须由用户显式配置。
- 请勿将客户敏感数据提交到 Git、公开模型或公共 SkillHub。

## 文档

- [启动与配置](./auditox/README.zh.md)
- [Skill × Tool 融合架构](./auditox/SKILL-TOOL-ARCHITECTURE.zh.md)
- [财务数据包与项目数据库](./auditox/DATA-PACKAGE-ARCHITECTURE.zh.md)
- [MCP 接口](./auditox/MCP.zh.md)
- [第三方声明](./THIRD_PARTY_NOTICES.md)
- [上游开源致谢](./ACKNOWLEDGEMENTS.zh.md)

## 许可

本仓库采用 [AIAuditOx 非商业许可 1.0](./LICENSE)：

- 允许个人学习、教学研究、单位内部审计和修改；
- 允许保留署名与相同许可的分发；
- 禁止商业使用、转售、去除署名和冒充来源；
- 商业授权需与作者单独协商。

该许可不是 OSI 认可的开源许可，属于 **source-available**。上游第三方组件仍适用各自的许可证，见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。
