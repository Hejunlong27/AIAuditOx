# Skill Runtime 流程

## 1. 启动链路

```text
SkillRegistry
→ SkillRouter
→ SkillLoader
→ SkillValidator
→ AuditPlanner
→ TaskApplicationService
→ TaskStateMachine / AgentOrchestrator
→ ToolRegistry / ToolExecutor
→ Evidence / Workpaper Writer
```

当前已完成到 `TaskApplicationService`、SQLite 持久化、人工审批、证据链和银行存款 Excel 底稿生成。任务按 DAG 推进，自动步骤统一经过 `ToolExecutor` 和程序级质量门。

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
## 7. TaskStateMachine

任务和步骤只允许通过合法迁移推进：

```text
任务：CREATED → PLANNING → READY → RUNNING → VERIFYING → COMPLETED
暂停：PLANNING/RUNNING → WAITING_INPUT
人工：RUNNING → WAITING_HUMAN → RUNNING
步骤：PENDING → READY → RUNNING → VERIFYING → VERIFIED
人工：WAITING_HUMAN → HUMAN_COMPLETED → VERIFYING → VERIFIED
```

`HUMAN_COMPLETED` 只表示“人交了材料”，不能直接关闭程序；仍须经过质量门。

## 8. AgentOrchestrator

输入：

- 已通过三源校验的 `AuditPlan`。
- `PermissionPolicy`。
- `tool_call_provider`：只负责为程序组装确定性工具参数，不承载状态推进。
- 可选人工提交、重规划器和工作区根目录。

执行规则：

- 缺少输入：任务 `WAITING_INPUT`，相关步骤不得执行。
- 人工程序：任务 `WAITING_HUMAN`；材料提交后进入 `VERIFYING`。
- 自动程序：声明工具必须全部调用，未声明工具不得调用。
- 工具失败：
  - `RETRYABLE`：按步骤重试额度重试，耗尽后转人工接管。
  - `NEED_HUMAN`：立即暂停为 `WAITING_HUMAN`。
  - `TERMINAL`：可调用重规划器生成新的已验证计划；否则任务失败。
- 同一层内相互独立的步骤会继续推进；该层有人工等待时，后续依赖层暂停。
- 所有活动步骤 `VERIFIED`，条件未激活步骤 `SKIPPED_NOT_APPLICABLE` 后，任务才可 `COMPLETED`。

## 9. 当前入口

```python
orchestrator = AgentOrchestrator(
    state_machine=TaskStateMachine(event_sink=events.append),
    tool_executor=ToolExecutor(tool_registry),
)
result = await orchestrator.execute(
    task,
    plan,
    permission_policy=PermissionPolicy(allowed_tools=allowed_tools),
    tool_call_provider=provider,
    workspace_root=workspace.root,
    human_submissions=submissions,
)
```

真实验收：`tests/integration/test_bank_deposits_e2e.py` 使用真实 SkillRegistry/Loader/Validator/Planner，按
`P01 → (P02,P08) → P04 → P06 → P07 → P10` 跑到 `COMPLETED`，并验证 P09 条件跳过。

## 10. TaskApplicationService

应用层负责项目、任务、工作区、输入文件、计划、审批、证据和底稿的生命周期协调。

```text
create_project
→ create_task
→ import input files / SHA-256
→ build + persist plan
→ run_task / resume
→ create pending approvals
→ load approved submissions
→ persist task + plan + evidence
→ export_workpaper
```

关键边界：

- 数据库是恢复状态的事实源。
- 人工审批通过后由下一次 `run_task` 自动加载。
- 工具结果通过 `result_sink` 写入 `evidences`。
- 人工附件按哈希去重写入 `evidences`。
- 银行存款底稿生成 Excel + Markdown，并登记为 `artifacts`。
- CLI 入口为 `python -m cli.main`。
