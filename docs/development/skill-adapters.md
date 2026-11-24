# Skill Adapter：输入资料到工具调用

> 更新时间：2026-11-24
> 当前完成：`z-1-2-bank-deposits`

## 1. 目标

自动 Skill Adapter 负责：

```text
任务逻辑输入文件
→ CSV/XLSX 解析
→ 表头别名识别
→ 金额、日期、方向标准化
→ 程序级工具调用
→ ToolExecutor
```

Adapter 不负责：

- 替代审计人员判断。
- 生成审计意见。
- 猜测缺失字段。
- 把无法识别的数据静默忽略。

无法安全映射时，必须明确报错或等待补充资料。

## 2. 当前结构

```text
agent-runtime/agent/adapters/
├── base.py
├── table.py
├── bank_deposits.py
└── registry.py
```

`AdapterRegistry` 根据技能 ID 创建对应 Adapter。`TaskApplicationService.run_task()` 在未提供
显式 provider 时自动使用 Adapter。

## 3. 银行存款输入键

```text
bank_balance_detail
general_ledger
financial_statement
bank_account_list
time_deposit_certificates
bank_reconciliation
bank_statement
confirmation_requests_responses
bank_journal
interest_income
interest_rate
disclosure_draft
```

`fund_pool_agreements`、`related_party_transactions` 只在不适用条件 P09 激活时需要。

## 4. 自动生成的程序调用

### P01

- `recalc_check`：总账 1002 余额 vs 账面折算合计。
- `balance_confirm`：总账余额 vs 官方汇率重算余额。

### P04

- 每个账户一条 `recon_statement_recalc`。
- 所有未达账项一条 `threshold_flag`。

### P06

- `bank_reconcile_dual`：日记账与对账单双向匹配。
- `sampling_draw`：基于发生额总体生成固定种子样本。

### P08

- `recalc_check`：预期利息收入 vs 账面利息收入。
- `threshold_flag`：利息差异与重要性阈值比较。

### P10

- `rule_check`：银行存款披露、受限资金披露、底稿和报表存在性。

## 5. 支持格式

当前：

- `.csv`
- `.tsv`
- `.xlsx`
- `.xlsm`

CSV 默认 UTF-8 BOM，解码失败时尝试 GB18030。中文表头通过别名匹配，不依赖固定列顺序。

## 6. 证据链

Adapter 为每个 `ToolCall` 设置 `source_files`。证据落库时优先使用这些文件路径计算 SHA-256，
因此工具运行证据可以追溯到原始资料，而不是只保存计算参数。

## 7. CLI

自动模式：

```powershell
python -m cli.main task run TASK-xxxx
```

仅在开发调试或未支持技能上使用显式工具调用：

```powershell
python -m cli.main task run TASK-xxxx --calls-file .\calls.json
```

## 8. 验收

真实 Node 工具端到端测试：

```powershell
cd D:\编程\AIAuditOx\agent-runtime
.\.venv\Scripts\python.exe -m pytest tests\integration\test_bank_adapter.py -o addopts='' -q
```

覆盖：

- 不提供 `calls.json`。
- 使用技能库真实银行存款样例。
- P01/P04/P06/P08/P10 自动生成工具调用。
- 人工审批循环。
- 任务完成。
- Excel 底稿生成。

## 9. 下一批 Adapter

建议顺序：

1. 库存现金。
2. 应收账款。
3. 营业收入。
4. 应付账款。
5. 短期借款。

每个 Adapter 必须先定义输入契约和字段映射测试，再接入真实工具。
