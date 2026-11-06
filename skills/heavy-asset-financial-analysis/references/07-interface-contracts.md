# 07 · 子技能接口契约

> 由总控与全部子技能加载。约定"谁能读什么、必须写什么"。

## 1. 工作目录约定

每次分析在用户工作区建立独立目录：

```
fin-analysis/<公司简称>-<期间>/
├── 00-raw/                     原始资料（只读，不得改动）
├── 01-standard/
│   ├── standard_dataset.json   ★ 全流程唯一数据源
│   ├── data-dictionary.md
│   ├── data-quality-report.md
│   └── data-gap-list.md
├── 02-statements/
│   └── statement-analysis.md   + metrics.json
├── 03-industry/
│   ├── real-estate-analysis.md  或  mining-analysis.md
│   └── project-matrix.csv / sensitivity.csv
├── 04-risk/
│   ├── cashflow-gap.md
│   ├── debt-wall.md
│   ├── stress-test.md
│   └── risk-rating.md
└── 05-report/
    ├── final-report.md
    └── exec-summary.md
```

**规则**：`00-raw/` 只读；所有下游只从 `01-standard/standard_dataset.json` 取数，禁止直接读原始文件。

## 2. 标准数据集 Schema

```json
{
  "meta": {
    "company": "某某控股集团有限公司",
    "short_name": "某某控股",
    "industry": "real_estate",
    "scope": "consolidated",
    "currency": "CNY",
    "unit": "万元",
    "periods": ["2023", "2024", "2025"],
    "base_period": "2025",
    "audited": true,
    "sources": ["2025年审计报告.pdf", "2025年销售回款台账.xlsx"],
    "as_of": "2026-10-08"
  },
  "income":    { "revenue": {"2023": 0, "2024": 0, "2025": 0}, "...": {} },
  "balance":   { "total_assets": {"2023": 0, "2024": 0, "2025": 0}, "...": {} },
  "cashflow":  { "cfo": {"2023": 0, "2024": 0, "2025": 0}, "...": {} },
  "operating": { "sales_amount": {"2024": 0, "2025": 0}, "...": {} },
  "debt_schedule": { "2026": {"amount": 0, "rate": 0.045, "type": "银行借款"} },
  "provenance": { "revenue": "审计报告 P42" },
  "qc": { "status": "pass|warn|fail", "notes": ["..."] }
}
```

- 时点科目（资产负债表）与时期科目（利润表/现金流量表）都用"期末/期间"标签，不另设 `_end` 后缀。
- 缺失值用 `null`，**不得用 0 代替缺失**（0 会被当作真实数值参与计算）。
- 经营数据只填有把握的期间；不补算、不插值。

## 3. 各子技能 I/O 契约

### Skill 01 `data-prep`
| | 内容 |
|---|---|
| 输入 | `00-raw/` 下任意格式原始资料 |
| 输出 | `standard_dataset.json`、`data-dictionary.md`、`data-quality-report.md`、`data-gap-list.md`、可计算/不可计算指标清单 |
| 完成判据 | 12 条质量检查全部有结论；核心 4 类数据（资产/负债/收入/现金流）缺失时标记 `qc.status=fail` 并**停止下传** |
| 下游依赖 | 全部 |

### Skill 02 `statement-analysis`
| | 内容 |
|---|---|
| 输入 | `standard_dataset.json` |
| 输出 | `statement-analysis.md`（五维分析）、`metrics.json`（指标计算结果） |
| 必含 | 五维结论、趋势（同比/CAGR/环比）、财务质量背离清单、异常变动追因 |
| 下游依赖 | 03 / 04 / 05 / 06 |

### Skill 03 `real-estate`
| | 内容 |
|---|---|
| 输入 | `standard_dataset.json` + 项目/土储/销售/回款台账 |
| 输出 | `real-estate-analysis.md`、`project-matrix.csv`（项目盈利矩阵）、项目分类结论 |
| 前置 | 必须先有 Skill 02 输出 |
| 下游依赖 | 05（存货与去化风险）、06 |

### Skill 04 `mining`
| | 内容 |
|---|---|
| 输入 | `standard_dataset.json` + 生产/储量/成本台账 + 商品价格数据 |
| 输出 | `mining-analysis.md`、`sensitivity.csv`（价格敏感性）、三级盈利（矿山→产品→公司） |
| 前置 | 必须先有 Skill 02 输出 |
| 下游依赖 | 05（CAPEX 与周期风险）、06 |

### Skill 05 `cashflow-debt-risk`
| | 内容 |
|---|---|
| 输入 | `standard_dataset.json` + `metrics.json` + 03/04 行业结论 |
| 输出 | `cashflow-gap.md`、`debt-wall.md`、`stress-test.md`（6 情景）、`risk-rating.md`（绿/黄/红） |
| 硬约束 | 每条风险必须附数据证据，无证据不得评级 |
| 下游依赖 | 06 |

### Skill 06 `report-generator`
| | 内容 |
|---|---|
| 输入 | 01–05 全部输出 + 用户交付偏好（对象/篇幅/模板） |
| 输出 | `final-report.md` / `exec-summary.md`（按模式选模板） |
| 硬约束 | 只整合、不新增未经验证的结论；引用数据必须能回溯到上游产物 |
| 下游依赖 | 无（终端） |

## 4. 中间产物最小字段要求

下游技能可以假定以下字段一定存在（若缺失，Skill 01 必须已在缺口清单声明）：

- `meta`：`company` / `industry` / `scope` / `currency` / `unit` / `periods` / `base_period`
- `income`：`revenue` / `cost_of_sales` / `operating_profit` / `net_profit` / `net_profit_attr_parent`
- `balance`：`cash` / `accounts_receivable` / `inventory` / `total_current_assets` / `total_assets` / `short_term_loans` / `current_portion_lt_debt` / `long_term_loans` / `total_current_liabilities` / `total_liabilities` / `total_equity`
- `cashflow`：`cfo` / `cfi` / `cff` / `capex` / `cash_begin` / `cash_end`

## 5. 独立运行规则

每个子技能都能单独调用，但须满足：

1. **自带降级**：输入不满足前置条件时，先声明缺什么、哪些结论降级，再继续能做的部分。
2. **输出自足**：独立运行时，输出文件必须自带 `meta` 段（公司/口径/单位/期间），不依赖上下文。
3. **不越界**：Skill 02 不做行业专项结论；Skill 03/04 不做偿债能力评级；Skill 06 不新增分析结论。
4. **编号稳定**：所有产物文件名固定，便于跨会话复用与增量更新。
