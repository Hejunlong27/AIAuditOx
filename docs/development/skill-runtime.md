# Skill Runtime 流程

## 1. 启动链路

```text
SkillRegistry
→ SkillRouter
→ SkillLoader
→ SkillValidator
→ AuditPlanner
→ ToolRegistry / ToolExecutor
```

当前已完成到 `AuditPlanner`，任务执行器和状态机是下一步。

## 2. SkillValidator

校验内容：

- YAML `skill_id` 与请求一致。
- YAML 程序集合与 `SKILL.md + DSL` 合并结果一致。
- 所有 mandatory 程序必须出现在 YAML。
- runtime tools 必须与技能层工具声明一致。
- 工具必须存在于当前 ToolRegistry。
- 依赖必须指向已知程序，且不得成环。

任何阻断冲突都会抛出 `SkillValidationError`，不能降级执行。

## 3. AuditPlanner

输入：

- `task_id`
- `skill_id`
- `provided_inputs`
- `active_conditions`

输出 `AuditPlan`：

- 拓扑分层执行顺序。
- 缺失输入。
- 人工程序。
- 条件程序。
- 各步骤状态。

## 4. bank_deposits 配置

配置位置：

```text
agent/config/procedures/bank_deposits.yaml
```

硬指标：

```text
P01 → (P02,P08) → P04 → P06 → P07 → P10
```

P01↔P04 人为成环时，Validator 必须拒绝。

## 5. 执行边界

- 输入缺失：步骤 `BLOCKED`，等待用户资料。
- 人工程序：步骤 `WAITING_HUMAN`。
- 条件未激活：`SKIPPED_NOT_APPLICABLE`。
- 工具不在 Registry：整个技能计划阻断。
- 依赖成环：整个技能计划阻断。

## 6. 当前入口

```python
validator = SkillValidator(loader, available_tools=set(tool_registry.list_names()))
planner = AuditPlanner(validator)
plan = planner.build_plan(
    task_id=task_id,
    skill_id="z-1-2-bank-deposits",
    provided_inputs={"bank_statement", "bank_journal"},
)
```
