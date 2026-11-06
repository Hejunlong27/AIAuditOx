# 审小牛 AIAuditOx

> 一切审计程序，皆可 skill 化。

把审计程序库逐条拆解成**可复用、可组合、可扩展的 AI 技能**：一个科目一个技能组，一道程序一张程序卡，凡能本地算完的一律交给确定性工具。

- 官网 / 在线检索：https://aiauditox.l.cd/
- 技能商店：SkillHub（org `org-c491l5hl`）
- 作者：何小疯27

---

## 这是什么

三件套，缺一不可：

| 件 | 作用 |
| --- | --- |
| **技能库** | 方法论载体：六要素（审计目标 / 所需资料 / 所需数据 / 核对逻辑 / 底稿内容 / 输出格式）、程序分派表、一级复核清单、边界与易错点 |
| **确定性工具** | 勾稽、重算、抽样、索引号、哈希——凡能本地算的一律调工具，禁止用模型估算 |
| **底稿制式** | 四段式输出规范（项目基本信息 / 审计目标和程序说明 / 程序执行结果 / 审计说明），保证同一 agent 产出一致 |

**确定性优先**：LLM 只做分析、解释、判断；差异类结论必须标注「待人工确认」。

---

## 技能清单

**31 个技能包 · 179 份程序卡文档**（数字由 `tools/build_index.py` 生成，以 `registry/skills.json` 为准）

### 全局规范（1）

| 技能 | 说明 |
| --- | --- |
| [`auditox-wp-standard`](skills/auditox-wp-standard) | 底稿制式规范（强制）。任何底稿编制前必须先加载 |

### 资产类 Z（9）

| 技能 | 科目 | 程序卡 |
| --- | --- | --- |
| [`z-1-1-cash-on-hand`](skills/z-1-1-cash-on-hand) | 库存现金 | 5 |
| [`z-1-2-bank-deposits`](skills/z-1-2-bank-deposits) | 银行存款 | 10 |
| [`z-1-3-other-monetary-funds`](skills/z-1-3-other-monetary-funds) | 其他货币资金 | 6 |
| [`z-2-1-notes-receivable`](skills/z-2-1-notes-receivable) | 应收票据 | 7 |
| [`z-2-accounts-receivable`](skills/z-2-accounts-receivable) | 应收账款 | 10 |
| [`z-3-prepayments`](skills/z-3-prepayments) | 预付款项 | 7 |
| [`z-4-other-receivables`](skills/z-4-other-receivables) | 其他应收款 | 7 |
| [`z-6-dividends-receivable`](skills/z-6-dividends-receivable) | 应收股利 | 7 |
| [`z-7-interest-receivable`](skills/z-7-interest-receivable) | 应收利息 | 5 |

### 负债类 F（10）

| 技能 | 科目 | 程序卡 |
| --- | --- | --- |
| [`f-1-borrowings`](skills/f-1-borrowings) | 短期借款 | 9 |
| [`f-3-notes-payable`](skills/f-3-notes-payable) | 应付票据 | 6 |
| [`f-4-accounts-payable`](skills/f-4-accounts-payable) | 应付账款 | 8 |
| [`f-6-payroll-payable`](skills/f-6-payroll-payable) | 应付职工薪酬 | 3 |
| [`f-8-advances-from-customers`](skills/f-8-advances-from-customers) | 预收账款 | 4 |
| [`f-9-taxes-payable`](skills/f-9-taxes-payable) | 应交税费 | 12 |
| [`f-10-interest-payable`](skills/f-10-interest-payable) | 应付利息 | 3 |
| [`f-11-dividends-payable`](skills/f-11-dividends-payable) | 应付股利 | 5 |
| [`f-12-other-payables`](skills/f-12-other-payables) | 其他应付款 | 8 |
| [`f-13-deferred-income`](skills/f-13-deferred-income) | 递延收益 | 5 |

### 损益类 S（7）

| 技能 | 科目 | 程序卡 |
| --- | --- | --- |
| [`s-1-revenue`](skills/s-1-revenue) | 营业收入 | 12 |
| [`s-8-taxes-and-surcharges`](skills/s-8-taxes-and-surcharges) | 税金及附加 | 4 |
| [`s-9-selling-expenses`](skills/s-9-selling-expenses) | 销售费用 | 9 |
| [`s-10-admin-expenses`](skills/s-10-admin-expenses) | 管理费用 | 9 |
| [`s-11-financial-expenses`](skills/s-11-financial-expenses) | 财务费用 | 6 |
| [`s-12-payroll-expenses`](skills/s-12-payroll-expenses) | 工资费用 | 10 |
| [`s-14-credit-impairment`](skills/s-14-credit-impairment) | 信用减值损失 | 2 |

### 辅助分析类（4）

| 技能 | 形态 | 说明 |
| --- | --- | --- |
| [`heavy-asset-financial-analysis`](skills/heavy-asset-financial-analysis) | 总控 + 6 子技能 | 重资产企业财务分析：房企 / 矿业 / 能源 / 基建 |
| [`financial-statement-analysis`](skills/financial-statement-analysis) | 工具型 | 四张报表进，可复算可追溯的分析底稿出 |
| [`doc-ocr-extract`](skills/doc-ocr-extract) | 工具型 | 合同发票票据进，带溯源坐标的结构化文档出（全程本地） |
| [`confirmation-address-auditor`](skills/confirmation-address-auditor) | 工具型 | 函证地址清单进，逐项核对工商注册地址并留痕 |

---

## 快速开始

### 方式一：装到 agent 的 skills 目录（推荐）

```bash
git clone https://github.com/Hejunlong27/AIAuditOx.git
cp -r AIAuditOx/skills/* ~/.claude/skills/        # Claude Code
# 或 ~/.codex/skills/  /  ~/.cursor/skills/  /  ~/.workbuddy/skills/
```

**注意**：`auditox-wp-standard` 必须先装——所有底稿技能依赖它。

### 方式二：让 agent 直接读本仓库

在 agent 里说：

```
读 https://github.com/Hejunlong27/AIAuditOx 的 AGENTS.md，
然后按 skills/z-1-2-bank-deposits/SKILL.md 执行银行存款审计程序。
```

### 方式三：SkillHub 安装

```
请根据 https://skillhub.cn/install/skillhub.md，安装 `@org-c491l5hl/z-1-2-bank-deposits`。
```

---

## 目录结构

```
skills/                    31 个技能包
├── auditox-wp-standard/   全局底稿制式（强制）
├── z-*/ f-*/ s-*/         26 个科目技能组（SKILL.md + dsl.json + procedures/）
└── */                     辅助分析类（总控型 / 工具型）
registry/skills.json       技能索引（自动生成，勿手改）
docs/                      架构与技能规范
tools/                     索引生成与校验
AGENTS.md                  ★ agent 指令入口
```

单个技能组内部：

```
<skill_id>/
├── SKILL.md               六要素 + 程序分派表 + 复核清单 + 边界
├── dsl.json               程序卡的认定、执行方式、工具映射
├── procedures/P01-*.md    程序卡详情：输入 / 步骤 / 质量门 / 升级路径
├── templates/             底稿模板
├── tests/                 黄金用例
└── CHANGELOG.md           更新记录（倒序）
```

---

## 开发

```bash
python tools/build_index.py      # 重建 registry/skills.json
python tools/validate_skills.py  # 校验结构（CI 同款）
```

新增技能组的规范见 [`AGENTS.md`](AGENTS.md) §4 与 [`docs/skill-spec.md`](docs/skill-spec.md)。

---

## 交流与共建

这个项目是开放的，欢迎一起把它做厚。

<img src="assets/images/wechat-group-qr.png" width="230" alt="审小牛开源交流群二维码">

**微信群「审小牛开源交流群」** —— 技能怎么用、底稿怎么改、审计 AI 怎么落地，都在这儿聊。发现问题、想要新科目，直接群里提。

> 群二维码 7 天内有效。失效了请提 [Issue](https://github.com/Hejunlong27/AIAuditOx/issues) 或发邮件，我会重发。

| 渠道 | 适合什么 |
| --- | --- |
| 微信群 | 用法答疑、需求讨论、快速反馈 |
| [GitHub Issues](https://github.com/Hejunlong27/AIAuditOx/issues) | 报 bug、纠错程序卡、提新科目 |
| 317950728@qq.com | 正式反馈、合作洽谈 |

### 怎么参与

- **报错**：说清哪个技能、哪张程序卡、哪条逻辑不对，附上你的判断依据（准则条款、程序库出处）
- **补科目**：按 [`docs/skill-spec.md`](docs/skill-spec.md) 的结构提交，一个科目一个包
- **改底稿**：`auditox-wp-standard` 是制式基准，动它要说明影响面
- **校对引用**：程序库来源、准则条款、会计科目编号，错了就该改
- **提工具**：`dsl.json` 里的 `tools` 是契约，新增工具请同时说明输入输出

**一条硬规矩**：不提交客户真实数据。所有样例必须脱敏。

---

## 声明

- 本仓库输出内容仅供学习与工作参考，**不构成任何审计意见或专业建议**。
- **请勿将客户敏感数据用于公开的 AI 服务**；`doc-ocr-extract` 设计为全程本地推理。
- 引用准则与程序库来源均标注出处；无公认依据处明确声明为自编，不伪造出处。

## 许可

免费开源，**禁止商用转售**。详见 [LICENSE](LICENSE)。

---

© 审小牛 AIAuditOx · 底稿制式与技能库版权归作者所有
