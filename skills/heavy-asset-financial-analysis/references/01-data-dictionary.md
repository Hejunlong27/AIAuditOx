# 01 · 数据字典与数据质量标准

> 由 Skill 01（`roles/data-prep`）加载。定义"什么算标准数据"。

## 1. 数据识别清单（处理任何资料前必须先填）

| 项 | 取值 | 说明 |
|---|---|---|
| 公司名称 | 全称 / 简称 | 多主体时列明母子公司关系 |
| 期间 | 年 / 季 / 月 | 明确是报告期还是截止日 |
| 数据类型 | 三大报表 / 审计报告 / 附注 / 管理报表 / 台账 / 经营计划 | 决定可信度层级 |
| 财务口径 | 合并 / 单体 | 未声明时默认合并，并标注 |
| 币种 | CNY / USD / HKD … | 多币种须标注汇率与折算日 |
| 单位 | 元 / 千元 / 万元 / 亿元 | 统一折算为**万元** |
| 是否经审计 | 已审 / 未审 | 影响结论措辞（"经审计"vs"未经审计"） |
| 数据来源 | 文件名 + 页/表位置 | 用于溯源 |

## 2. 标准科目字典

标准数据集采用英文 snake_case 键名（供 `scripts/*.py` 直接计算），中文名为报告用名。

### 2.1 利润表 `income`

| 键名 | 中文名 | 归属 |
|---|---|---|
| `revenue` | 营业收入 | 利润表 |
| `cost_of_sales` | 营业成本 | 利润表 |
| `taxes_and_surcharges` | 税金及附加 | 利润表 |
| `selling_exp` | 销售费用 | 利润表 |
| `admin_exp` | 管理费用 | 利润表 |
| `rd_exp` | 研发费用 | 利润表 |
| `finance_exp` | 财务费用 | 利润表 |
| `interest_expense` | 利息支出 | 附注/财务费用明细 |
| `interest_income` | 利息收入 | 附注 |
| `investment_income` | 投资收益 | 利润表 |
| `fair_value_change` | 公允价值变动收益 | 利润表 |
| `asset_impairment` | 资产减值损失 | 利润表 |
| `credit_impairment` | 信用减值损失 | 利润表 |
| `asset_disposal` | 资产处置收益 | 利润表 |
| `other_income` | 其他收益 | 利润表 |
| `operating_profit` | 营业利润 | 利润表 |
| `ebit` | 息税前利润 | 计算 |
| `ebitda` | 息税折旧摊销前利润 | 计算 |
| `depreciation_amortization` | 折旧与摊销 | 现金流量表附注 |
| `non_recurring` | 非经常性损益 | 附注 |
| `income_tax` | 所得税费用 | 利润表 |
| `net_profit` | 净利润 | 利润表 |
| `net_profit_attr_parent` | 归母净利润 | 利润表 |
| `minority_interest_pl` | 少数股东损益 | 利润表 |

### 2.2 资产负债表 `balance`

| 键名 | 中文名 | 分组 |
|---|---|---|
| `cash` | 货币资金 | 资产-流动 |
| `restricted_cash` | 其中：受限资金 | 附注 |
| `short_term_investments` | 交易性金融资产 | 资产-流动 |
| `notes_receivable` | 应收票据 | 资产-流动 |
| `accounts_receivable` | 应收账款 | 资产-流动 |
| `other_receivable` | 其他应收款 | 资产-流动 |
| `prepayments` | 预付款项 | 资产-流动 |
| `inventory` | 存货（房开含开发成本/开发产品） | 资产-流动 |
| `contract_assets` | 合同资产 | 资产-流动 |
| `total_current_assets` | 流动资产合计 | 资产 |
| `long_term_equity_invest` | 长期股权投资 | 资产-非流动 |
| `investment_property` | 投资性房地产 | 资产-非流动 |
| `fixed_assets` | 固定资产 | 资产-非流动 |
| `cip` | 在建工程 | 资产-非流动 |
| `right_of_use_assets` | 使用权资产 | 资产-非流动 |
| `intangible_assets` | 无形资产（含采矿权） | 资产-非流动 |
| `goodwill` | 商誉 | 资产-非流动 |
| `deferred_tax_assets` | 递延所得税资产 | 资产-非流动 |
| `total_assets` | 资产总计 | 资产 |
| `short_term_loans` | 短期借款 | 负债-流动 |
| `notes_payable` | 应付票据 | 负债-流动 |
| `accounts_payable` | 应付账款 | 负债-流动 |
| `contract_liabilities` | 合同负债（预收房款） | 负债-流动 |
| `advance_receipts` | 预收款项 | 负债-流动 |
| `other_payable` | 其他应付款 | 负债-流动 |
| `current_portion_lt_debt` | 一年内到期的非流动负债 | 负债-流动 |
| `other_current_liabilities` | 其他流动负债 | 负债-流动 |
| `total_current_liabilities` | 流动负债合计 | 负债 |
| `long_term_loans` | 长期借款 | 负债-非流动 |
| `bonds_payable` | 应付债券 | 负债-非流动 |
| `lease_liabilities` | 租赁负债 | 负债-非流动 |
| `other_interest_bearing` | 其他有息负债 | 负债 |
| `total_interest_bearing_debt` | 有息负债合计 | 计算/附注 |
| `total_liabilities` | 负债合计 | 负债 |
| `total_equity` | 所有者权益合计 | 权益 |
| `equity_attr_parent` | 归属于母公司所有者权益 | 权益 |
| `minority_interest` | 少数股东权益 | 权益 |

### 2.3 现金流量表 `cashflow`

| 键名 | 中文名 |
|---|---|
| `cfo` | 经营活动产生的现金流量净额 |
| `cfi` | 投资活动产生的现金流量净额 |
| `cff` | 筹资活动产生的现金流量净额 |
| `capex` | 购建固定资产、无形资产和其他长期资产支付的现金 |
| `capex_maintenance` | 其中：维持性资本开支（矿业/基础设施） |
| `capex_growth` | 其中：扩张性资本开支 |
| `depreciation_amortization` | 折旧与摊销（现金流表补充资料） |
| `interest_paid` | 偿付利息支付的现金 |
| `dividends_paid` | 分配股利、利润支付的现金 |
| `borrowings_received` | 取得借款收到的现金 |
| `borrowings_repaid` | 偿还债务支付的现金 |
| `cash_begin` | 期初现金及现金等价物余额 |
| `cash_end` | 期末现金及现金等价物余额 |
| `net_increase_cash` | 现金及现金等价物净增加额 |

### 2.4 经营数据 `operating`（按行业取用）

**通用**：`sales_amount`（销售/签约金额）、`cash_collection`（回款额）、`collection_rate`（回款率）、`headcount`

**房地产**：`sales_area`（销售面积）、`sales_price`（销售均价）、`land_reserve_area`（土储面积）、`land_reserve_gmv`（土储货值）、`land_cost`（土地成本）、`construction_cost`（建安成本）、`contracted_not_delivered`（已售未结）

**矿业/能源**：`resource_reserve`（资源储量）、`mineable_reserve`（可采储量）、`ore_grade`（品位）、`capacity`（设计产能）、`production_volume`（产量）、`sales_volume`（销量）、`recovery_rate`（回收率）、`unit_price`（销售单价）、`unit_cost`（单位成本）、`cash_cost`（现金成本）、`stripping_ratio`（剥采比）、`mine_life`（剩余服务年限）、`royalty`（资源税/权益金）

### 2.5 债务明细 `debt_schedule`

按到期年份列出本息与融资方式：

```json
"debt_schedule": {
  "2026": {"amount": 120000, "rate": 0.045, "type": "银行借款"},
  "2027": {"amount": 80000,  "rate": 0.042, "type": "公司债"}
}
```

### 2.6 溯源表 `provenance`

每个关键字段标注来源，缺来源的数字在报告中标为「来源待确认」：

```json
"provenance": {"revenue": "2025审计报告 P42 合并利润表", "land_reserve_gmv": "用户提供 2025土储台账"}
```

## 3. 单位与口径规范

| 项目 | 规范 |
|---|---|
| 金额 | 一律折算为**万元**；正文重大金额可并列亿元 |
| 面积 | 统一**平方米**，正文可用万平方米 |
| 产量 | 统一**吨**，正文可用万吨；贵金属可用克/千克 |
| 时间 | 统一**自然年/自然季**；跨期一律标注起止日 |
| 汇率 | 标注折算汇率与折算日，禁止用期末汇率折算利润表 |
| 口径 | 合并/单体不得混用；不得用单体数据算集团偿债能力 |

### 3.1 符号约定（影响脚本计算，必须遵守）

| 科目 | 符号约定 | 原因 |
|---|---|---|
| `asset_impairment`（资产减值损失） | **填负数**（损失为负） | 与"营业利润 = 收入 − 成本 − 费用 + 其他损益 + 减值"的加总口径一致 |
| `credit_impairment`（信用减值损失） | **填负数** | 同上 |
| `investment_income` / `fair_value_change` / `other_income` / `asset_disposal` | 收益为正、损失为负 | 直接参与加总 |
| `capex` | **填正数**（支出金额） | 自由现金流 = CFO − CAPEX |
| 缺失值 | 填 `null` | 填 0 会被当作真实数值参与计算，导致指标失真 |

### 3.2 经营数据单位约定（脚本按此折算）

| 行业 | 字段 | 单位 | 脚本折算 |
|---|---|---|---|
| 房地产 | `sales_amount` / `cash_collection` / `land_reserve_gmv` / `land_cost` | 万元 | 直接使用 |
| 房地产 | `sales_area` / `land_reserve_area` | 万平方米 | 直接使用 |
| 房地产 | `sales_price` | 元/平方米 | 直接使用 |
| 房地产 | `collection_rate` | 小数（0.71 表示 71%） | 直接使用 |
| 矿业 | `sales_volume` / `production_volume` | 吨 | 与单价相乘后 ÷10000 得万元 |
| 矿业 | `unit_price` / `unit_cost` / `cash_cost` | 元/吨 | 同上 |
| 矿业 | `resource_reserve` / `mineable_reserve` / `capacity` / `production_volume`（储量类） | 万吨 | 储采比 = 可采储量 ÷ 年产量的万吨口径 |
| 矿业 | `ore_grade` / `recovery_rate` | 百分数数值（1.31 表示 1.31%） | 直接使用 |

> 经营数据与财务报表口径不一致时（如储量按万吨、销量按吨），必须在 `data-dictionary.md` 中显式声明折算关系，禁止混用。

## 4. 数据质量检查规则（12 条，逐条出结论）

| # | 检查项 | 判据 | 处理 |
|---|---|---|---|
| 1 | 缺失检查 | 核心科目空值 | 计入缺口清单，标记影响范围 |
| 2 | 重复检查 | 同一科目多来源冲突 | 取审计/附注优先，其余标注差异 |
| 3 | 单位错误 | 数量级异常（如收入为资产 10 倍） | 回溯原始表头，禁止直接改数 |
| 4 | 年份错位 | 期初期末与上期期末不符 | 标注并请用户确认 |
| 5 | 科目映射错误 | 科目归组不符会计准则 | 重新归组并记录调整 |
| 6 | 数据冲突 | 同一指标两处不同 | 并列展示 + 说明采用哪一个 |
| 7 | 口径差异 | 合并/单体混用 | 分离口径，禁止直接比较 |
| 8 | 期初期末不一致 | 本期期初 ≠ 上期期末 | 列差额，不强行调平 |
| 9 | 勾稽-资产 | 资产合计 = 负债合计 + 所有者权益合计 | 差额 >1% 标为质量风险 |
| 10 | 勾稽-现金 | 期末现金 = 期初 + CFO + CFI + CFF | 同上 |
| 11 | 勾稽-利润 | 营业利润 ≈ 收入 - 成本 - 税金 - 期间费用 + 其他损益 | 同上 |
| 12 | 经营-财务匹配 | 回款额 vs 销售商品收到现金；产量×单价 vs 收入 | 偏差 >10% 必须追因 |

## 5. Skill 01 输出物

| 输出 | 形式 | 用途 |
|---|---|---|
| 标准化数据集 | `standard_dataset.json` | 供 02/03/04/05 计算 |
| 数据字典 | Markdown | 口径说明书 |
| 数据质量报告 | Markdown | 可信度声明 |
| 数据缺口清单 | Markdown 表 | 决定哪些结论无法给出 |
| 可计算指标清单 | Markdown 表 | 决定分析边界 |
| 无法计算指标及原因 | Markdown 表 | 明确声明，不猜测 |
