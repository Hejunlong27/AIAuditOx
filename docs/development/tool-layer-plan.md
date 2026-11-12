# Agent 工具层开发计划

> 日期：2026-11-12
> 范围：`agent-runtime`、`skill-library`、`skill-tools/auditox-tools`
> 目标：共性能力集中实现，技能只声明调用语义、科目规则和专属适配。

## 1. 现状盘点

基于 `python tools/audit_tool_usage.py --fail-on-missing` 的实测结果：

| 指标 | 当前值 |
|---|---:|
| `auditox-tools` 中心工具 | 26 |
| `dsl.json` 引用的中心工具 | 15 |
| 工具引用总次数 | 247 |
| DSL 引用但中心工具不存在 | 0 |
| 未被 DSL 引用的中心工具 | 11 |
| 含工具引用或本地脚本的技能包 | 32 |

高频工具：

| 工具 | 引用次数 |
|---|---:|
| `recalc_check` | 72 |
| `rule_check` | 55 |
| `threshold_flag` | 41 |
| `sampling_draw` | 27 |
| `balance_confirm` | 22 |
| `excel_read` | 8 |
| `interest_calc` | 7 |
| `cutoff_test` | 4 |
| `provision_calc` | 4 |
| `bank_reconcile_dual` | 2 |

结论：核心科目技能已经有较好的中心工具声明，不是从零开始。主要缺口是 Runtime 尚无工具注册与执行层，以及 5 个辅助技能包内存在文件读取、归一化、校验、报表生成等可复用实现。

## 2. 工具分类

### A. 已中心化的确定性工具

保留在 `skill-tools/auditox-tools`，作为确定性执行内核：

- 勾稽、重算、账↔单核对、余额核对。
- 阈值、规则/schema 校验、抽样。
- 账龄、坏账准备、折旧、利息、截止测试。
- 索引号、manifest、修订记录、底稿填充。
- Excel/Word/PDF 转换与读写。

### B. 应继续收敛的通用能力

从辅助技能包中识别共性，但先审计再迁移：

- 文件/目录发现、文件哈希、证据清单。
- Excel/CSV/PDF/Word 的统一读取与错误分类。
- 金额、日期、单位、字段名、表头归一化。
- Schema/字段完整性/跨表一致性校验。
- 报告、工作底稿、异常清单的统一输出封装。

### C. 必须留在技能包的专属逻辑

- 科目字段映射和报表列定义。
- 特定审计程序的业务规则、阈值和例外解释。
- 专属模板、样例、黄金用例。
- 专业判断和人工复核口径。

## 3. Runtime 工具层目标架构

```text
Skill dsl.json
  procedure -> tool_id
        |
        v
ToolRegistry  (唯一工具注册表)
        |
ToolExecutor
  schema validate -> permission -> timeout -> retry -> audit log
        |
        +--> deterministic adapter
        +--> office/file adapter
        +--> skill-specific adapter
        |
ToolResult
  success/result/evidence/warnings/failure_class
```

### 必须满足的契约

复用并扩展现有模型：

- `ToolSpec`：名称、描述、风险级别、输入/输出 schema、超时、重试、审批要求、技能声明。
- `ToolInvocation`：任务、程序、参数、成功/失败、耗时、审计记录。
- `ToolResult`：结果、证据、警告、人工复核要求、失败分类。
- `PermissionPolicy`：白名单、网络/Shell 禁止、调用次数上限。

后续需要补充：

- 工具版本和实现来源。
- 是否确定性、是否幂等、是否有副作用。
- 宿主支持矩阵：Python Runtime / DSH / EXE。
- 输入归一化和输出证据的统一约定。

## 4. 开发阶段

### P0：工具审计与边界（已完成）

- 新增 `tools/audit_tool_usage.py`。
- 输出中心工具、技能引用、缺失工具、未使用工具和技能本地脚本。
- 新增单元测试，保证审计结果可回归。

### P1：Tool Registry + Executor（已完成）

- 实现 `ToolContext`、`ToolHandler`、`ToolExecutionError`。
- 实现唯一 `ToolRegistry`：注册、查询、重复检测和能力解析。
- 实现 `ToolExecutor`：JSON Schema 参数/输出校验、权限、审批、超时、重试、错误分类和调用审计。
- 扩展 `ToolSpec`：版本、确定性、幂等性、后端类型和宿主支持矩阵。
- 新增 `ToolRequirement` 与 `tool-requirements.json` 加载器：
  - 显式清单优先。
  - 无清单时从 `dsl.json` 推导 required 工具。
  - required 缺失阻塞；preferred 有 fallback 才允许降级；optional 缺失仅警告。
- 不在 Skill 包内新增运行时逻辑。

技能可选能力清单格式：

```json
{
  "schemaVersion": 1,
  "requirements": [
    {"name": "recalc_check", "level": "required"},
    {"name": "excel_read", "level": "preferred", "fallback": "skill_local"},
    {"name": "pdf_ops", "level": "optional"}
  ]
}
```

### P2：包装中心工具（已完成）

全部 26 个中心工具已完成 Python Runtime 接入，其中 17 个纯函数工具与 9 个 Office/PDF 工具共用同一个固定 Node 桥。

- 通用计算：`recalc_check`、`rule_check`、`threshold_flag`、`sampling_draw`、`balance_confirm`
- 账务核对：`bank_reconcile_dual`、`recon_statement_recalc`
- 资产计量：`ageing_bucket`、`provision_calc`、`depreciation_calc`、`interest_calc`、`cutoff_test`
- 底稿契约：`index_numbering`、`manifest_json`、`revision_record`、`workpaper_fill`、`workpaper_spec`

实现方式：

- 新增 `skill-tools/auditox-tools/scripts/runtime_bridge.mjs`。
- Node 桥只监听 stdin 的 JSON Lines，输出单行 JSON，不经过 Shell。
- 桥内部使用固定 26 工具白名单：17 个只读纯函数、9 个本地写入工具体。
- Python `NodeToolBridge` 以固定 Node 可执行文件和固定脚本路径启动持久子进程。
- 工具目录、输入 schema 和输出 schema 从 Node 定义动态读取，Python 不复制算法。
- Python `register_node_core_tools()` 将桥接工具注册到 `ToolRegistry`。
- 传输错误归类 `RETRYABLE`；Node 工具返回 `ok:false` 时归类 `NEED_HUMAN`。
- 文件工具必须提供 `workspace_root`，所有路径规范化并限制在工作区内。
- 桥接模式下 Python sidecar 的输出重定向到 stderr，避免污染 JSON 协议 stdout。
- 输入 schema 保持严格。
- 为兼容旧工具契约，输出 required 字段严格校验，允许额外诊断/证据字段，并允许可选输出字段为 `null`。

Office/PDF 工具已增加本地路径边界：

- 纯函数工具标记 `READ_ONLY`。
- 文件输出工具标记 `LOCAL_WRITE`。
- `path/input/inputs/output/out/csv_path` 等文件参数统一解析到 `workspace_root`。
- 相对路径按任务工作区解析；越界路径返回 `NEED_HUMAN`。
- 没有 `workspace_root` 的文件工具禁止执行。
- Node 工具返回 `ok:false` 时统一映射为 `NEED_HUMAN`，不得静默当作成功。

- 优先包装高频工具：`recalc_check`、`rule_check`、`threshold_flag`、`sampling_draw`、`balance_confirm`。
- 通过统一适配器调用现有实现，避免重写已验证算法。
- 将工具调用结果统一映射为 `ToolResult`，保留原始结果和证据。

### P3：收敛辅助技能共性（进行中）

已完成 P3-1：Runtime 侧能力配置已生成到 5 个辅助技能包的 `tool-requirements.json`，且无中心工具硬依赖，standalone fallback 保持可用。

已完成 P3-2 第一批：`safe_div`、`yoy_change`、`sha256_file` 已收敛到 `skill-tools/auditox-python-core/`，并由生成器同步到技能包。

- 从 `confirmation-address-auditor`、`doc-ocr-extract`、`financial-statement-analysis`、`heavy-asset-financial-analysis`、`universal-annual-audit` 中提取重复的底层能力。
- 迁移前逐个建立等价性测试。
- 专属业务规则、字段映射和报告结构留在包内。

### P4：DSH 与 EXE 适配（待开始）

- DSH 插件只负责宿主工具注册、preset 和调用桥接。
- 独立 EXE 复用同一 ToolRegistry/Executor。
- 两种交付不得复制业务工具实现。

## 5. P2 前需要确认的实现边界

Runtime 使用 Python，而现有中心工具以 Node/Cordis 为主。P1 的 Tool Registry/Executor 已与实现语言解耦；P2 注册具体工具前必须确认唯一实现和调用边界：

1. 先复用 Node 工具，通过受控本地桥接调用。
2. 将中心工具逐步迁移/包装为 Python 核心。
3. 建立宿主无关的本地工具服务协议。
4. 同一逻辑保留双实现（不推荐）。

在确认前，不批量迁移脚本，不重写现有 26 个工具。
