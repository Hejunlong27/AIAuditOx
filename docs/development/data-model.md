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
