# 审小牛AIAuditOx HARNESS

审小牛AIAuditOx HARNESS 是本地优先的审计工具，底层以 DeepSeek Harness `0.2.3-alpha.2` 为 Agent 运行时，并通过审计领域插件完成产品化改造。对外界面使用审小牛独立品牌，DeepSeek 的开源贡献仅在仓库许可证、第三方声明和致谢文档中保留。

## 产品界面

- 深色/浅色自适应，默认采用冷白工作区与石墨侧栏。
- 侧栏按“通用工具、审计自动化、本地模型、技能中心”组织。
- 首页展示审计路径：项目资料 → 审计计划 → 控制测试 → 实质程序 → 项目复核。
- 主界面提供本地模型启动/关闭开关。
- 取消首次打开登录门槛；模型和 API 配置由用户主动进入设置完成。

## 已接入能力

### 审小牛模式

- `审小牛引导审计`：报表与账套驱动的引导式审计流程。
- `审小牛对话审计`：直接讨论审计问题、资料缺口和复核发现。

### 本地模型

`packages/extensions/auditox-local-services` 提供：

- CPU、内存、磁盘、NVIDIA GPU/Windows 显卡检测；
- Ollama 安装与运行状态检测；
- 启动、关闭本地推理服务；
- 按硬件适配度推荐模型；
- Ollama 一键配置与模型下载；
- 自定义 OpenAI 兼容模型地址和 API Key；
- 通过本机网关把“当前本地模型”接入 Agent；
- 选择 GGUF 文件上传导入，或直接填写本机 GGUF 路径导入；
- 国内镜像检索链接，并明确区分其与 Ollama 拉取源。

模型目录当前包含已核验的 Qwen3.5 文本模型和 Qwen2.5-VL、MiniCPM-V 视觉模型。默认模型为 `qwen3.5:4b`，本地 OpenAI 兼容入口为 `http://127.0.0.1:11434/v1`。

### 技能中心

`packages/client/ui-auditox-workbench` 提供：

- 读取 `D:/编程/AIAuditOx/skill-library` 的本地 SkillHub 镜像；
- 42 包技能列表、分类和搜索；
- 点击查看 `SKILL.md`；
- 安装到 `$DSH_HOME/skills`；
- 卸载和重新扫描。

### 数据架构

财务数据包、项目数据库和审计模块的统一设计见：

[DATA-PACKAGE-ARCHITECTURE.zh.md](./DATA-PACKAGE-ARCHITECTURE.zh.md)

## 启动

```powershell
cd D:\编程\AIAuditOx\deepseek-harness\auditox
.\build.ps1
.\run.ps1
```

## 边界

- 客户文件默认只在本机流转。
- 金额、勾稽和计算由确定性工具完成，模型只做分析、解释和草稿。
- 模型输出不得替代原始证据或项目组结论。
- 对外发布、网盘上传和 SkillHub 上架仍需项目负责人确认。

## 开源致谢

上游项目：`deepseek-ai/deepseek-harness`，MIT License，Copyright (c) 2026 DeepSeek。

完整说明见仓库根目录 [ACKNOWLEDGEMENTS.zh.md](../ACKNOWLEDGEMENTS.zh.md)。
