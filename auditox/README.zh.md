# 审小牛 AuditOx Harness

这是基于官方 `deepseek-ai/deepseek-harness` `0.2.3-alpha.2` 的审小牛产品化分支。

## 设计原则

- 不重写 DSH 的 Agent Loop、session、工具注册、审批、沙箱和模型适配器；
- 审小牛能力通过 bundle patch、client plugin、agent preset 和 tool plugin 扩展；
- Python `agent-runtime` 继续作为审计项目、资料、证据和底稿领域服务；
- `skill-library` 是唯一技能事实源，DSH 直接以自定义 skill 根目录加载；
- 客户数据默认只走本地服务和本地文件。

## 已接入

### 品牌与主题

`packages/client/ui-brand-auditox` 通过 `ctx.theme.overrideTokens()` 和 UI slots 提供：

- 审小牛侧栏标志与字标；
- 纸账本式浅色/深色 token；
- 首页“底稿 / 证据 / 复核”图形层；
- 审计档案右侧栏类型与 header action；
- `DSH_CLIENT_TITLE` 产品标题。

### 技能

`auditox/cordis.patch.yml` 将以下目录挂到 DSH `skill-filesystem`：

```text
D:/编程/AIAuditOx/skill-library
```

当前 42/42 个包的 `SKILL.md` frontmatter 均包含 DSH 所需的 `name` 与 `description`。

### 审小牛引导 preset

`auditox` preset 默认不开放 shell、任意文件系统写和外部 web 工具，先以审计数据和受控工具为主。当前包含：

- `tool-skill`：加载审小牛技能；
- `tool-auditox-runtime`：连接本地 Python Runtime；
- `tool-office`：读取 Office 资料；
- `tool-ask-user`、`tool-todo`、`plan-mode`、`present`；
- `compaction`。

### Python Runtime 工具桥

`packages/extensions/tool-auditox-runtime` 注册：

- `auditox_health`
- `auditox_list_projects`
- `auditox_create_project`
- `auditox_list_assets`
- `auditox_upload_asset`
- `auditox_start_guided_thread`
- `auditox_advance_guided_stage`

默认连接 `http://127.0.0.1:8765`，可通过 `AUDITOX_RUNTIME_URL` 覆盖。

## 启动

### 一键启动

```powershell
cd D:\编程\AIAuditOx\deepseek-harness\auditox
.\build.ps1
.\run.ps1
```

`run.ps1` 会按需启动本地 Python Runtime，启动 DSH Web UI，并在退出时关闭由它启动的 Runtime。使用 `-NoOpen` 可不自动打开浏览器。

### 手动启动

#### 1. 启动 Python AuditOx Runtime

```powershell
cd D:\编程\AIAuditOx\agent-runtime
.\.venv\Scripts\python.exe -m api.main --port 8765
```

#### 2. 构建 DSH

DSH 当前要求 Node `^24.22.3 || >=26.13.1`。本机验证时使用 Node `26.13.1`。

```powershell
cd D:\编程\AIAuditOx\deepseek-harness
$env:DSH_CLIENT_TITLE = '审小牛 AuditOx Harness'
pnpm install
pnpm run build
```

#### 3. 启动带审小牛 overlay 的 Web UI

```powershell
$env:DSH_HOME = 'D:\编程\AIAuditOx\deepseek-harness\.tmp\dsh-home-auditox'
pnpm dsh --profile web --patch ./auditox/cordis.patch.yml --no-open --port 3080
```

浏览器打开命令打印的带 token URL。

## 许可证

上游 DSH 为 MIT License，Copyright (c) 2026 DeepSeek。衍生分发必须保留上游许可证和第三方声明。本分支新增的审小牛代码沿用仓库约定，并在发布前单独复核许可与第三方依赖。

## 当前边界

这是可运行的产品化技术验证，不是最终安装包：

- 尚未制作 Windows 桌面安装器；
- 尚未把 Python Runtime 作为 DSH 子进程自动拉起；
- 审计档案右侧栏目前是工作台骨架，后续接入真实项目、阶段和证据数据；
- 尚未配置真实模型 API 做端到端审计对话；
- 需要跟随 DSH 开发者预览版升级并持续做插件兼容测试。