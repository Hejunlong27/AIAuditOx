# Application Service 与本地 CLI

> 更新时间：2026-11-15
> 状态：银行存款单技能产品闭环已贯通到持久化、人工审批、证据链和 Excel 底稿导出。

## 1. 分层位置

```text
CLI / DSH / EXE / REST（宿主适配）
                ↓
TaskApplicationService（项目、任务、输入、审批、导出）
                ↓
SkillRouter → SkillValidator → AuditPlanner
                ↓
TaskStateMachine → AgentOrchestrator → ToolExecutor
                ↓
Node 工具 / Python 公共核心 / 文件工作区
                ↓
SQLite 9 表 + 工作区文件
```

应用服务是唯一允许同时协调数据库、工作区、规划器和执行器的层。宿主适配器不得复制状态机或手写工具执行循环。

## 2. 项目与任务生命周期

```text
创建项目
→ 创建任务（路由或显式 skill_id）
→ 创建任务工作区
→ 导入原始资料并复制为只读快照
→ 生成计划并落库
→ 执行自动程序
→ 等待输入或人工材料
→ 人工审批/附件登记
→ 恢复执行
→ 程序级质量门
→ 导出 Excel 底稿和 Markdown 预览
→ 登记 artifact / evidence / audit_event
```

数据库是任务恢复的真相源。关闭进程后重新创建 `TaskApplicationService`，仍可通过任务 ID 加载任务、计划、步骤状态和已批准人工材料。

## 3. 持久化映射

| 业务对象 | 数据表 |
| --- | --- |
| 项目 | `projects` |
| 任务 | `tasks` |
| 计划 | `plans` |
| 程序步骤 | `plan_steps` |
| 工具调用 | `tool_runs` |
| 工具/人工证据 | `evidences` |
| 人工审批 | `approvals` |
| 底稿与输入文件 | `artifacts` |
| 状态和业务事件 | `audit_events` |

任务、计划和步骤每次关键状态变化均写审计事件。工具结果通过 `result_sink` 自动形成证据记录；人工附件按文件哈希去重后登记为 `HUMAN_ATTACHMENT`。

## 4. 技能事实源

统一工作区中的 CLI 默认使用：

```text
D:\编程\AIAuditOx\skill-library
```

Runtime 索引是生成物，默认写入：

```text
D:\编程\AIAuditOx\agent-runtime\registry\skill-library.json
```

重建命令：

```powershell
cd D:\编程\AIAuditOx\agent-runtime
python tools/build_index.py --skills-dir ../skill-library --out registry/skill-library.json
```

`agent-runtime/skills/` 的 31 包仅用于仓库存活测试，不再是生产事实源。

## 5. 输入导入

`create_task(input_files=...)` 接收逻辑输入键到源文件路径的映射：

```text
bank_statement=/path/bank-statement.csv
bank_journal=/path/bank-journal.xlsx
```

行为：

1. 逻辑键必须是 `[a-z][a-z0-9_]*`。
2. 文件复制到任务工作区 `01_原始资料/`。
3. 目标文件设置为只读。
4. 计算 SHA-256。
5. 写入 `artifacts`，元数据保留逻辑输入键和相对路径。

不会引用外部原文件作为证据源。

## 6. 人工审批

流水线：

```text
步骤 WAITING_HUMAN
→ approvals 自动生成 PENDING
→ CLI/API 审批
→ APPROVED/REJECTED + actor + comment + attachments
→ 下一次 run_task 自动加载批准材料
→ WAITING_HUMAN → HUMAN_COMPLETED → VERIFYING
→ 质量门
→ VERIFIED
```

拒绝不会自动关闭程序；下一次执行会重新形成待办。`HUMAN_COMPLETED` 永远不等于 `VERIFIED`。

## 7. 银行存款底稿

当前 Workpaper Writer 支持：

- `z-1-2-bank-deposits`。
- 四段式 Excel 主表。
- 程序明细。
- 证据清单。
- 修订记录。
- 同路径 Markdown 预览。
- 输入/结果文件哈希。
- `artifact` 登记和 `WORKPAPER_EXPORTED` 审计事件。

输出：

```text
<任务工作区>/02_工作底稿/Z-1-2_银行存款审计执行底稿.xlsx
<任务工作区>/02_工作底稿/Z-1-2_银行存款审计执行底稿.md
```

底稿只记录实际执行状态和证据，不虚构金额、结论或审计意见。

## 8. CLI

安装：

```powershell
cd D:\编程\AIAuditOx\agent-runtime
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

基础命令：

```powershell
python -m cli.main --help
python -m cli.main project create --name "某公司 2026 年报审计" --client "某公司" --period "2026"
python -m cli.main project list
python -m cli.main task list --project PRJ-xxxx
python -m cli.main task show TASK-xxxx
python -m cli.main approval list --task TASK-xxxx
python -m cli.main approval approve APR-xxxx --actor reviewer --comment "已复核"
python -m cli.main workpaper export TASK-xxxx --prepared-by "审计员" --reviewer "复核人"
```

创建任务：

```powershell
python -m cli.main task create `
  --project PRJ-xxxx `
  --request "执行银行存款审计程序" `
  --skill z-1-2-bank-deposits `
  --input bank_balance_detail=C:\data\accounts.csv
```

银行存款任务默认使用自动 Skill Adapter。创建任务时只需要把业务文件映射到逻辑输入键：

```powershell
python -m cli.main task run TASK-xxxx
```

对于尚未实现 Adapter 的技能，可临时使用显式工具调用文件：

```json
{
  "P01": [
    {
      "tool_name": "recalc_check",
      "arguments": {
        "op": "diff",
        "operands": [100, 100]
      }
    }
  ]
}
```

```powershell
python -m cli.main task run TASK-xxxx --calls-file .\calls.json
```

银行存款已经完成“规范化输入数据 → 工具参数”的自动适配。其他技能仍可使用上述显式参数文件作为受控过渡方案。

## 9. 当前验收

```text
Agent Runtime  185 passed
```

覆盖：

- 输入复制、只读和哈希。
- 项目、任务、计划跨服务实例恢复。
- 人工审批跨实例恢复。
- 工具证据和人工证据落库。
- 银行存款流程完成。
- Excel/Word 底稿文件结构与内容。
- CLI 项目创建和查询烟雾测试。

## 10. 尚未完成

- 自动把业务文件转换成每个工具的参数。
- 全部技能的 Runtime YAML。
- REST API、DSH 完整工具插件和独立 EXE。
- 人工审批图形界面。
- 通用 Workpaper Writer（目前只支持银行存款）。
- 更多技能的 Runtime YAML 与自动工具参数适配。
