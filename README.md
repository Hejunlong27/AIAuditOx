# 审小牛AIAuditOx HARNESS

审小牛是面向中国审计项目组的本地优先 AI 审计工作台。它以 Agent Harness 作为底层运行时，把财务报表、账套资料、审计程序、底稿、证据与复核过程组织到同一個本地工作区中。

## 当前可用能力

- **审小牛引导审计**：从财务报表和账套资料出发，组织审计计划、重要性、审计程序、控制测试、实质性底稿和复核清单。
- **审小牛对话审计**：直接讨论报表、风险、程序、资料缺口和复核发现。
- **本地模型**：检测 CPU、内存、磁盘和显卡，推荐 Ollama 模型，并可在主界面启动或关闭本地推理服务。
- **视觉识别**：预置 Qwen2.5-VL、MiniCPM-V 等图像模型目录，用于合同、发票、票据和扫描件识别。
- **技能中心**：读取审小牛 SkillHub 本地镜像，支持查看 `SKILL.md`、安装和卸载技能。
- **通用工具**：保留 Harness 的工具加载与插件机制，但以审小牛“通用工具”的产品语言呈现。
- **本地数据边界**：默认不上传客户文件；审计金额、勾稽和计算必须由确定性工具完成。

## 启动

```powershell
cd D:\编程\AIAuditOx\deepseek-harness\auditox
.\build.ps1
.\run.ps1
```

## 设计边界

- DSH 只作为 Agent Loop、会话、工具注册、审批、沙箱和模型适配的底层运行时。
- 可见界面采用审小牛独立视觉与交互语言，不复用 DeepSeek 产品品牌。
- Skill 事实源是 `D:\编程\AIAuditOx\skill-library`，安装后复制到 `DSH_HOME/skills`。
- 本地模型首选 Ollama；模型目录只登记已经核验可用的标签。
- 国内镜像用于检索和手动获取，不能伪装成 Ollama 官方拉取链路。

## 开源致谢

审小牛 Harness 基于 DeepSeek 开源的 DeepSeek Harness 项目进行产品化改造。上游项目、MIT 许可证和第三方声明继续保留；详细致谢见 [ACKNOWLEDGEMENTS.zh.md](./ACKNOWLEDGEMENTS.zh.md)。

## 文档

- [审小牛AIAuditOx HARNESS 启动说明](./auditox/README.zh.md)
- [财务数据包与项目数据库架构](./auditox/DATA-PACKAGE-ARCHITECTURE.zh.md)
- [开源致谢](./ACKNOWLEDGEMENTS.zh.md)
