# Agent 数据模型与三源合并

## 1. 技能程序的三层来源

| 来源 | 内容 | 不允许承担的职责 |
| --- | --- | --- |
| `SKILL.md` | 六要素、程序分派表、认定、执行方式、产出底稿、复核清单 | 依赖顺序、运行时输入键 |
| `dsl.json` | 程序 ID、名称、工具声明、人工三态 | 程序依赖、任务状态 |
| `agent/config/procedures/*.yaml` | `depends_on`、`required_inputs`、`tools` 交叉校验、`enabled_when` | 改写技能业务规则 |

`SkillValidator` 将三源合并为 `ProcedureDefinition`，并用 `sources` 标记字段来源。

## 2. ProcedureDefinition

关键字段：

- `id` / `name` / `tools`
- `assertions` / `execution_policy`
- `dependencies`
- `required_inputs`
- `enabled_when`
- `mandatory` / `conditional`
- `workpaper_index`
- `procedure_doc`
- `skill_id` / `skill_version`

依赖只能来自 runtime YAML；不得从 DSL 或程序卡正文猜测。

## 3. AuditPlan

`AuditPlan` 是单个技能任务的执行计划：

- `steps`：所有 P01~Pn 的规范化步骤。
- `execution_order`：自动步骤的拓扑分层，同层可并行。
- `missing_inputs`：未提供的输入键并集。
- `human_tasks`：需人工确认、判断或人工主导的步骤。
- `conditional_tasks`：运行时带条件的步骤。
- `validated`：三源校验是否通过。

## 4. PlanStep 状态

- `PENDING`：依赖和输入满足，可执行。
- `BLOCKED`：缺少必要输入。
- `WAITING_HUMAN`：人工主导程序。
- `SKIPPED_NOT_APPLICABLE`：条件未激活。
- `RUNNING` / `VERIFYING` / `VERIFIED` / `FAILED`：由后续执行器推进。

`missing_inputs` 存在时不得开始数字核对，应先向用户发起资料请求。

## 5. bank_deposits 基线

`z-1-2-bank-deposits` 的自动执行层级：

```text
P01
→ (P02, P08)
→ P04
→ P06
→ P07
→ P10
```

- `P03`、`P05` 为人工主导任务。
- `P09` 默认跳过；激活“资金池/集团资金往来”条件后加入 DAG。
- `P05` 是强制程序，缺失配置会阻断校验。
## 6. 执行记录模型

| 模型 | 用途 |
| --- | --- |
| `ToolCall` | 一个程序内待执行的确定性工具、参数与审批状态 |
| `HumanSubmission` | 人工提交的说明与证据文件，必须至少有其中一项 |
| `QualityDecision` | 程序级质量门结论：通过 / 人工 / 重试 / 终止，四选一 |
| `StateChange` | 一次任务或步骤状态迁移，可供审计事件落库 |
| `OrchestrationResult` | 一次执行或恢复后的任务快照、最终计划与等待项 |
| `AuditProject` | 本地审计项目元数据 |
| `ArtifactRecord` | 输入文件、底稿和其他产物的路径、哈希与版本 |

`PlanStep.execution_mode` 保留 `AUTO / AUTO_WITH_CONFIRM / AUTO_WITH_JUDGMENT / HUMAN_LED / HUMAN_ONLY`，
执行器不能只凭工具数量猜测人工程序。

## 7. 编排状态约束

- 自动步骤的工具集合必须与 `required_tools` 完全覆盖，不接受漏调或越权增调。
- `RETRYABLE` 失败先重试；耗尽后步骤进入 `WAITING_HUMAN`，允许人工接管。
- `NEED_HUMAN` 直接进入 `WAITING_HUMAN`。
- `TERMINAL` 失败可触发一次或多次受上限约束的重规划；没有有效新计划时任务进入 `FAILED`。
- 人工材料提交后必须经过质量门，`HUMAN_COMPLETED` 不等于 `VERIFIED`。

## 8. 应用层持久化

`TaskApplicationService` 将执行内核与 SQLite 连接：

- 任务、计划、步骤状态写入 `tasks / plans / plan_steps`。
- 每次状态迁移写入 `audit_events`。
- 工具调用写入 `tool_runs`。
- 工具结果和人工附件写入 `evidences`。
- 人工待办与决定写入 `approvals`。
- 原始资料和底稿写入 `artifacts`，文件本体留在任务工作区。

银行存款端到端验收已验证：任务执行到人工等待后重建 `TaskApplicationService`，仍能加载任务、计划、审批和证据并继续到 `COMPLETED`。
