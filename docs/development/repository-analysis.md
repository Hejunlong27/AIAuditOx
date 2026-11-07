# 仓库现状分析报告

> 生成日期：2026-11-07
> 分析基线：`main` @ `08d8c4328b109a02140b8f70aca65a109bfaa589`（与 `origin/main` 一致，工作区干净）
> 分析方式：逐文件实测 + 脚本普查，**未依据 README 推断**。
> 复现命令：见文末「附录 A · 核查脚本」。

---

## 0. 结论摘要（先看这段）

| 判断 | 事实 |
| --- | --- |
| 仓库是什么 | **纯技能库 + 规范 + 两个构建脚本**。31 个技能包 / 658 个文件 / 179 份程序卡文档。 |
| 仓库不是什么 | **没有任何 Agent 运行时**。无 `agent/`、无 `api/`、无 `cli/`、无数据库、无 `pyproject.toml`、无 `requirements.txt`。 |
| 任务书前置文件 | 任务书要求读的 `docs/workpaper-spec.md` **不存在**；底稿规范的真实载体是 `skills/auditox-wp-standard/SKILL.md`。 |
| 最大设计冲突 | `docs/skill-spec.md` 描述的 `dsl.json` 结构与**真实 dsl.json 不一致**（文档写 `skill`/`assertions`/`mode`/`output`，实物只有 `skill_id`/`id`/`name`/`tools`/`human`）。DSL 里**没有依赖关系、没有认定、没有产出索引**。 |
| 第二冲突 | 「执行方式」列是**自由文本，130+ 种写法**，无法机器可靠解析为执行策略。程序是否必须人工，DSL 与 SKILL.md 存在 **5 处直接矛盾**（见 §12.2）。 |
| 可复用资产 | 银行包 `templates/*.xlsx` 双版本模板、`tests/sandbox/inputs/*.csv` 带预埋异常的黄金数据、`tools/build_index.py` 的结构判别逻辑。 |
| 工程风险 | 现有 CI 只跑 `validate_skills.py` + `build_index.py --check`（Python 3.11、零第三方依赖）。新增 Agent 依赖一旦污染这两个脚本，CI 立刻红。 |

**上一句最关键的话**：本任务是**从零建运行时**，不是"改造现有运行时"。所有 `agent/` 代码均为新建。

---

## 1. 当前仓库目录结构

```
AIAuditOx/                        674 个 Git 跟踪文件 · Python 11,302 行（38 个 .py）
├── AGENTS.md                     ★ agent 指令入口（110 行，含「调用协议」7 步）
├── CLAUDE.md                     仅转发 AGENTS.md
├── README.md                     技能清单与介绍
├── LICENSE                       CC-BY-NC-SA-4.0
├── .github/
│   ├── workflows/validate.yml    CI：validate_skills.py + build_index.py --check
│   └── ISSUE_TEMPLATE/           bug_report / feature_request
├── docs/
│   ├── architecture.md           分层图、四种技能形态、升级路径（明确「运行时规划中」）
│   └── skill-spec.md             技能包规范（★ 其中 dsl.json 示例与实物不符，见 §12.1）
├── registry/
│   └── skills.json               ★ 生成物，禁止手改（schemaVersion 1）
├── skills/                       31 个技能包 · 658 文件
│   ├── auditox-wp-standard/      底稿制式规范（standard）
│   ├── z-*-*/ f-*-*/ s-*-*/      26 个科目技能组（skill-group）
│   ├── heavy-asset-financial-analysis/   总控型（orchestrator，含 roles/）
│   ├── financial-statement-analysis/     工具型（tool，含 scripts/ + rules/）
│   ├── confirmation-address-auditor/     工具型（tool，含 scripts/）
│   └── doc-ocr-extract/                  工具型（tool，含 scripts/）
├── tools/
│   ├── build_index.py            扫描 skills/ 生成 registry/skills.json（--check 模式给 CI）
│   └── validate_skills.py        结构校验（0 通过 / 1 有错误）
├── publish_all.py                SkillHub 发布脚本（业务侧，与本任务无关）
├── switch_downloads.py           分发切换脚本（业务侧，与本任务无关）
├── publish-log.jsonl             发布日志（已 gitignore）
├── assets/images/                站点图片
└── .tmp/                         历史导入暂存（已 gitignore，勿动）
```

**不存在**：`agent/`、`api/`、`cli/`、`adapters/`、`tests/`（根级）、`storage/`、`workspaces/`、`artifacts/`、`pyproject.toml`、`setup.py`、`requirements.txt`、`docs/development/`、`docs/workpaper-spec.md`。

---

## 2. 已有功能和模块

| 模块 | 功能 | 状态 |
| --- | --- | --- |
| 技能内容层 `skills/` | 31 包方法论文本：六要素、程序分派表、程序卡 P01~Pn、复核清单、边界、Pitfalls | ✅ 完整可用 |
| 索引生成 `tools/build_index.py` | 扫目录 → 判形态（靠结构信号）→ 出 `registry/skills.json` | ✅ 可用，138 行，零依赖 |
| 结构校验 `tools/validate_skills.py` | 校验 frontmatter / name 一致 / dsl 可解析 / 程序卡文档存在 / 形态必备目录 | ✅ 可用，178 行，零依赖 |
| CI `.github/workflows/validate.yml` | push/PR 到 main 时跑上面两个脚本（Python 3.11） | ✅ 生效 |
| 技能包内脚本 | 4 个工具型包的 `scripts/`（地址核对、OCR、财报分析、重资产分析） | ⚠️ 存在但**不被任何运行时调用**，是独立 CLI |
| 技能包内回归脚本 | 29/31 包含 `tests/`，如 `z-1-2/tests/regression.py`（497 行） | ⚠️ 手工执行的沙箱脚本，**非 pytest，不进 CI** |

---

## 3. 现有技能数量与分类

`registry/skills.json` 实测：

```json
{ "count": 31, "totalProcedures": 179,
  "byVariant": { "skill-group": 26, "orchestrator": 1, "tool": 3, "standard": 1 } }
```

| 分类 | 数量 | 目录 |
| --- | --- | --- |
| `skill-group`（科目技能组） | 26 | `z-*`(9) / `f-*`(10) / `s-*`(7) |
| `orchestrator`（总控型） | 1 | `heavy-asset-financial-analysis` |
| `tool`（工具型） | 3 | `confirmation-address-auditor` / `doc-ocr-extract` / `financial-statement-analysis` |
| `standard`（规范型） | 1 | `auditox-wp-standard` |

**形态判别靠结构信号，不靠包名**（`build_index.py:detect_variant`）：有 `roles/` → orchestrator；有 `scripts/` → tool；有 `procedures/` → skill-group；否则 standard。

**重要**：31 个技能包中只有 **27 个**有 `dsl.json`。缺 DSL 的 4 个：`confirmation-address-auditor`、`doc-ocr-extract`、`financial-statement-analysis`、`heavy-asset-financial-analysis`。→ `SkillLoader` 必须容忍无 DSL 的包。

---

## 4. Skill 的实际数据结构

### 4.1 SKILL.md frontmatter

实测字段（`build_index.py:parse_frontmatter` 用极简解析，非完整 YAML）：

```yaml
---
name: z-1-2-bank-deposits      # 必须与目录名一致（validate_skills.py 强校验）
description: 触发场景与触发词
version: 1.0.0
slug: aiauditox-z-1-2-bank-deposits     # 部分包含
displayName: 货币资金·银行存款           # 部分包含
summary: ...                            # 部分包含
license: CC-BY-NC-SA-4.0                # 部分包含
---
```

→ **只能用极简 key: value 解析器**，不能假设是合法 YAML（value 中含中文冒号、全角符号）。

### 4.2 SKILL.md 正文必需章节

| 章节 | 是否被机器消费 | 解析难度 |
| --- | --- | --- |
| 技能来源与使用声明 | 否 | — |
| **六要素**（表格） | 语义参考 | 中（表格，5 行 2 列） |
| **程序分派表**（6 列表格） | ★ **是**：决定执行哪几张卡 | 中（见 §4.4） |
| Steps（调度流程） | ★ **是**：含依赖顺序与异常激活规则 | **高（自然语言）** |
| 一级复核清单 | 是（质量门参照） | 中（无序列表） |
| 边界与禁止事项 | 是（安全约束参照） | 中 |
| Pitfalls | 参考 | 低 |

### 4.3 程序卡文档 `procedures/Pxx-*.md`

固定 4 小节（`docs/skill-spec.md` §4 强制）：**输入 / Steps / 质量门 / 升级路径**。
Steps 内每步有 `【脚本】` / `【规则】` / `【人工】` 前缀标签 —— **这是唯一可信的"该步谁来执行"信号**，比 DSL 的 `human` 布尔字段更细。

### 4.4 程序分派表真实结构（★ 关键）

普查 31 包：

| 表头形态 | 包数 |
| --- | --- |
| 6 列：`程序卡/程序名称/程序库来源/对应认定/执行方式/产出底稿` | 25 |
| **5 列**：`程序卡/程序名称/程序库来源/对应认定/产出底稿`（**无执行方式**） | 1（`s-1-revenue`） |
| 无程序卡表格 | 5（4 个非 skill-group + `auditox-wp-standard`） |

→ **解析器必须按表头映射列，不能按列位置硬取**。`s-1-revenue` 少一列会让按位置解析的代码直接错位到「产出底稿」。

「执行方式」列取值实测 **130+ 种自由文本**，高频前几：

```
12  自动（schema 校验）+人工确认      11  自动+人工确认       11  自动（脚本核对）
 6  自动筛样+人工核单                  5  自动+人工判断        4  自动（预期值测算）+人工判断
 3  人工为主+汇总表自动                3  人工为主（职业怀疑+舞弊迹象判断）
```

「产出底稿」列取值形态：`Z-1-2-04`(27) / `F-1-01`(47) / `S-12-03`(27) / `Z-2-04`(21) / `F-10-02`(21)，另有 4 条特殊：`引用《A.01 银行函证工作簿》`、`Z-1-2-04 附区`、`联动 Z-1-2-10（回函核对入 F-1-02）`、`Z-1-2-06（中期函证前推并入）`。→ 索引号需 `^\w+(-\w+)*-\d+$` 提取 + 特殊形态单列。

---

## 5. DSL 的实际字段结构

### 5.1 实测根字段（27 个 DSL 完全一致）

```json
{
  "skill_id": "z-1-2-bank-deposits",
  "name": "货币资金·银行存款",
  "version": "1.0.0",
  "owner_role": "审计助理",
  "cycle": "Z",
  "group_code": "Z",
  "risk_level": "中",
  "description": "...",
  "procedures": [...],
  "quality_gate": { "required_coverage_pct": 100 }
}
```

### 5.2 实测 procedures 元素字段（190 条全量普查）

| 字段 | 出现次数 / 总数 | 说明 |
| --- | --- | --- |
| `id` | 190 / 190 | `P01`…`P10`；`auditox-wp-standard` 用 `G0`/`G1` |
| `name` | 190 / 190 | 程序名 |
| `tools` | 150 / 190 | **40 条程序没有任何工具声明**（纯判断类） |
| `human` | 112 / 190 | **78 条缺该字段** → 缺失 ≠ false，必须谨慎默认 |

### 5.3 **DSL 里没有的东西**（任务书假设有，实际没有）

| 任务书 PART 5.3 要求 | 实物 | 影响 |
| --- | --- | --- |
| `assertions`（认定） | ❌ 无 | 只能从 SKILL.md 分派表「对应认定」列解析 |
| `execution_policy` | ❌ 无 | 只能从 `human` + 分派表「执行方式」+ 程序卡 `【人工】` 标签推断 |
| `dependencies` | ❌ 无 | **必须由运行时配置 `bank_deposits.yaml` 提供** |
| `mandatory` | ❌ 无 | 只能靠程序名含「（强制）」或 SKILL.md 文字识别（如 `P05 银行函证程序（强制）`） |
| `conditional` | ❌ 无 | 只能靠 SKILL.md Steps 第 3 条「P09 视资金池/集团情况决定是否启用」识别 |
| `source` | ❌ 无 | 分派表「程序库来源」列有（`Z1002 程序2`） |

→ **结论：DSL 只是"程序目录 + 工具绑定 + 是否人工"的三元组，不足以驱动 DAG 执行。任务书 PART 11.4 要求建 `agent/config/procedures/bank_deposits.yaml` 是必需的，不是可选项。**

### 5.4 DSL 与程序卡文档覆盖缺口

| 技能包 | DSL 声明 | 实际 `.md` | 缺口 |
| --- | --- | --- | --- |
| `auditox-wp-standard` | G0, G1 | 0 | **2 份缺**（规范型本无程序卡，属正常） |
| `f-6-payroll-payable` | 10 | 3 | **P04~P10 缺 7 份**（真实结构缺口） |
| `z-1-3-other-monetary-funds` | 8 | 6 | **P05、P07 缺 2 份**（真实结构缺口） |
| 合计 | 190 | 179 | 11 |

→ 运行时遇到缺卡程序**不得自行补写内容**，须标 `NOT_IMPLEMENTED` 并走质量门告警。

---

## 6. 程序卡的实际结构（以银行存款为例）

10 张卡，P01~P10，结构统一。字段从程序卡正文提取：

| 卡 | 程序名 | 来源 | 认定 | 执行方式（SKILL.md） | 产出 | DSL `human` | DSL `tools` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | 余额明细表编制 | Z1002 程序2 | C、E | 自动（脚本核对） | Z-1-2-01 | false | recalc_check, balance_confirm |
| P02 | 账户完整性检查 | Z1002 程序3 | C | 自动+人工确认 | Z-1-2-02 | **false** | — |
| P03 | 定期存款检查 | Z1002 程序4 | E、A | **人工为主**（监盘/网银观察） | Z-1-2-03 | **true** | — |
| P04 | 余额调节表检查 | Z1002 程序5 | C、E、A | 自动（重算）+人工判断 | Z-1-2-04 | **false** | recon_statement_recalc, threshold_flag |
| P05 | 银行函证（**强制**） | Z1002 程序6 | C、E、A、P | **人工为主**+控制表自动 | 引用《A.01》 | **true** | — |
| P06 | 发生额双向核对 | Z1002 程序7、8、9 | A、C、E | 自动（脚本双向核对） | Z-1-2-06 | false | bank_reconcile_dual, sampling_draw |
| P07 | 截止测试 | Z1002 程序10、11 | C、E | 自动+人工判断 | Z-1-2-07 | false | — |
| P08 | 实质性分析程序 | Z1002 分析1、2 | C、E、A | 自动（利息测算/开户分析） | Z-1-2-08 | false | recalc_check, threshold_flag |
| P09 | 资金划转与关联方往来 | Z1002 程序12、13、14 | C、E、A | 自动+人工判断 | Z-1-2-09 | false | — |
| P10 | 披露检查 | Z1002 程序16 | P | 自动+人工确认 | Z-1-2-10 | false | rule_check |

**依赖顺序**（SKILL.md Steps 第 3 条原文）：
> P01 →（P02、P08 可并行）→ P04 → P06 → P07 → P10；P03/P05 标记人工主导任务并跟踪完成状态；P09 视资金池/集团情况决定是否启用。

**异常激活规则**（Steps 第 5 条原文）：
- P04 大额/长期未达 → 激活 P06 扩样 + 提示 P05 关注
- P08 利息差异超阈值 → 激活 P06 核查异常流水 + 升级助理
- P02 发现清单外账户 → 立即升级助理 + 舞弊风险迹象（程序15）

→ 这三条是**条件激活**，DSL 里完全没有，必须进 `bank_deposits.yaml`。

---

## 7. 现有工具的功能

**关键事实：仓库里的"工具"全部只是名字契约，没有任何实现。**

`dsl.json` 全库声明的工具名（去重 15 个）：

| 工具名 | 被多少包声明 | 有实现吗 |
| --- | --- | --- |
| `rule_check` | 26 | ❌ |
| `recalc_check` | 25 | ❌ |
| `threshold_flag` | 23 | ❌ |
| `balance_confirm` | 20 | ❌ |
| `sampling_draw` | 16 | ❌ |
| `excel_read` | 5 | ❌ |
| `cutoff_test` | 4 | ❌ |
| `interest_calc` | 3 | ❌ |
| `provision_calc` | 3 | ❌ |
| `bank_reconcile_dual` | 2 | ❌ |
| `revision_record` / `workpaper_fill` / `sheet_to_csv` / `ageing_bucket` / `recon_statement_recalc` | 各 1 | ❌ |

`docs/architecture.md` 原文确认：「**工具实现不在本仓库（属运行时侧），仓库只声明契约**」。

→ 任务书 PART 9 要求的 11 个工具，**全部需要从零实现**。其中 `file_reader`、`account_completeness_check` 在全库 190 条程序里**从未被声明**（0 次），属任务书新增契约，需在运行时注册为扩展工具。

`skills/*/scripts/` 里的 Python 是 4 个工具型技能的独立 CLI（如地址核对 `matcher.py`/`normalizer.py`），与本任务的确定性审计工具**不是一回事**，不复用。

---

## 8. 当前底稿生成能力

| 能力 | 现状 |
| --- | --- |
| 底稿制式规范 | ✅ `skills/auditox-wp-standard/SKILL.md` 四段式 + 三段式兜底，规定表头七要素、索引号体系、`.md` 伴随修订记录 |
| 底稿模板（Excel） | ✅ 银行存款包有 **2 个版本**：`Z-1-2银行存款审计工作簿模板.xlsx`（8 表）与 `..._v1.1.xlsx`（**10 表**，多 P03 定期存款、P09 资金划转） |
| 模板结构 | ✅ 每张工作表统一：A1 标题 / A2 索引+来源+认定 / A4「一、项目基本信息」/ A5-A6 七要素 / A8+「二、审计目标和程序说明」… |
| 底稿自动生成代码 | ❌ **不存在**。没有任何代码填充模板；`workpaper_fill` 工具只有名字 |
| 修订记录生成 | ❌ 只有模板 md，无生成代码 |
| 公式写入 | ⚠️ 模板内已有公式，但无代码校验重算（`openpyxl` 不能算公式，需另找方案或只做公式文本校验） |

→ 任务书 PART 15 的 Workpaper Writer **全新建**。模板可复用，但必须选 **v1.1**（10 表，覆盖 P03/P09），并记录模板版本。

---

## 9. 现有自动化测试情况

| 层级 | 现状 |
| --- | --- |
| CI 结构校验 | ✅ 2 个脚本，`ubuntu-latest` + Python 3.11，零第三方依赖 |
| pytest | ❌ **根级无 pytest、无 `tests/`、无 `conftest.py`、无 `pytest.ini`/`pyproject.toml`** |
| 技能包内回归 | ⚠️ 29/31 包有 `tests/`，形态是「`inputs/*.json` + `expected/*.json` + `regression.py`」，**手工跑、不进 CI、无断言框架** |
| 黄金数据 | ✅ `z-1-2-bank-deposits/tests/sandbox/inputs/` 有 6 个 CSV（accounts / confirmations / interest / journal_A002 / recon_items_A002 / statement_A002），带 7 项预埋异常 E1~E7（汇率错、未达账、长期未达、跨期、利息差、一收一付同额对私） |
| GC 覆盖率 | ❌ 无 |

→ 任务书 PART 21 的五层测试**全部新建**。`tests/sandbox/inputs/*.csv` 可直接作为 T01/T02 的种子，但**仍需扩充出 T03~T20 共 18 个场景**。

---

## 10. 可以直接复用的代码 / 资产

| 资产 | 复用方式 | 侵入性 |
| --- | --- | --- |
| `tools/build_index.py` 的 `detect_variant()` 结构判别 | `SkillRegistry` 直接调用（作为库导入），**不复制逻辑**，保证两套判别不分叉 | 零（只 import） |
| `registry/skills.json` | `SkillRegistry` 的**唯一**技能索引源（任务书 PART 7.1 明确禁止建第二套索引） | 零（只读） |
| `skills/*/SKILL.md` + `procedures/*.md` | `SkillLoader` / `DSLParser` 的输入 | 零（只读） |
| `templates/Z-1-2...v1.1.xlsx` | Workpaper Writer 的模板底座 | 零（复制到工作区再填） |
| `tests/sandbox/inputs/*.csv` | 黄金数据集种子 | 零（复制到 `tests/golden/`） |
| `skills/auditox-wp-standard/SKILL.md` | 底稿制式的**运行时校验规则源**（四段/七要素/索引号） | 零（只读） |

**明确不复用**：`publish_all.py`、`switch_downloads.py`（SkillHub 分发业务，与运行时无关）；4 个工具型技能的 `scripts/`（独立 CLI，接口不匹配）。

---

## 11. 必须新增的模块

按任务书 PART 4 目标结构，**全部为新建**（仓库当前 0 个文件属于运行时）：

```
agent/          18 个子模块：core/ models/ task/ skills/ tools/builtin/ llm/ quality/
                storage/ memory/ security/ config/procedures/
api/            main.py + dependencies.py + routes/{tasks,files,approvals,artifacts}.py
cli/            main.py + commands/{task,skill,server,config}.py
adapters/       mcp/{server,tools}.py + external_agent/skill_adapter.py
tests/          unit/ integration/ e2e/ fixtures/ golden/
docs/development/  12 份文档（本报告为第 1 份）
pyproject.toml  工程配置（新增）
```

**边界铁律**（AGENTS.md §6 + 任务书 PART 2.2）：运行时逻辑**一律不得写进 `skills/`**；`skills/` 保持纯内容层，无运行时也能被任意 agent 读取使用。

---

## 12. 发现的设计冲突与技术风险

### 12.1 🔴 冲突 A：`docs/skill-spec.md` 描述的 DSL 结构与实物不符

文档 §3 示例：

```json
{ "skill": "z-1-2-bank-deposits",
  "procedures": [{ "id":"P01", "source":"Z1002 程序1", "assertions":["C","E","A"],
                   "mode":"hybrid", "human":false, "tools":[...], "output":"Z-1-2-01" }] }
```

实物：根键是 `skill_id` 不是 `skill`；程序只有 `id/name/tools/human`，**无** `source`/`assertions`/`mode`/`output`。

**处置（不改技能、不改文档）**：
- `DSLParser` 以**实物 schema 为准**，做 `normalize()` 把 `skill`→`skill_id` 兼容掉，缺失字段置 `None` 而非默认值。
- 认定（assertions）改从 SKILL.md 分派表「对应认定」列解析；产出索引从「产出底稿」列解析。**DSL 与 SKILL.md 合并后才是完整 `ProcedureDefinition`**。
- 在 `docs/development/data-model.md` 记录「DSL 是子集，SKILL.md 分派表是补充源」这一事实，并在技能版本升级时统一（任务书 PART 11.3 第 7 条）。

### 12.2 🔴 冲突 B：人工要求，DSL 与 SKILL.md 直接矛盾（5 处）

| 程序 | SKILL.md 执行方式 | DSL `human` | 谁对 |
| --- | --- | --- | --- |
| P02 账户完整性 | 自动+**人工确认** | `false` | SKILL.md（有访谈/承诺函人工程序） |
| P04 调节表 | 自动（重算）+**人工判断** | `false` | SKILL.md（长期未达需人工判断） |
| P07 截止测试 | 自动+**人工判断** | `false` | SKILL.md（跨期事项人工复核） |
| P09 资金划转 | 自动+**人工判断** | `false` | SKILL.md（商业理由人工判断） |
| P10 披露检查 | 自动+**人工确认** | `false` | SKILL.md（审计结论人工确认） |
| P03 定期存款 | 人工为主 | `true` | 一致 |
| P05 函证 | 人工为主 | `true` | 一致 |

**处置**：任务书 PART 11.3 已定调「不得自动降低人工要求，采用保守策略」。实现上：
- 建**统一 `ExecutionPolicy`**，由三源合并：`dsl.human` ∪ 分派表「执行方式」含「人工」字样 ∪ 程序卡 Steps 含 `【人工】` 标签。
- 合并规则：`human_confirmation = OR(三源)`，**取最严**。
- 生成**冲突报告**落盘（`artifacts/<task>/conflicts.json`），指明每处冲突的三源取值。
- 不修改现有 `skills/` 任何文件。

### 12.3 🟠 风险 C：执行方式是自由文本，无法可靠机器化

130+ 种写法，且同一含义多种表述（「自动+人工确认」/「自动（schema 校验）+人工确认」）。任何"关键词分类"都会漏。

**处置**：不追求自动分类准确，改为 **`bank_deposits.yaml` 显式声明 + 保守推断兜底 + 冲突告警**。推断只做 `contains("人工") or contains("判断") or contains("确认")` 这一条最宽松规则，宁可多要人工，不可少要。

### 12.4 🟠 风险 D：DSL 无依赖关系，DAG 无法从技能库推导

`dependencies` 在 190 条程序里 0 出现。DAG 只能来自：
1. `bank_deposits.yaml` 显式 `depends_on`（主源）；
2. SKILL.md Steps 文字（辅助，仅 OCR 式参考，不解析为执行依据）。

**处置**：Planner 以 `yaml` 为唯一依赖真相源；`yaml` 缺失时**拒绝执行**（不猜）。

### 12.5 🟠 风险 E：CI 是零依赖 Python 3.11，新依赖会污染

`validate.yml` 直接 `python tools/validate_skills.py` 裸跑，不装任何包。一旦在 `tools/` 两个脚本里 import pydantic，CI 立刻红。

**处置**：铁律 —— `tools/build_index.py` 与 `tools/validate_skills.py` **永不修改**（也不 import agent 包）。新增独立 job 或不加 CI（第一版先不加，避免破坏现有绿灯）。

### 12.6 🟠 风险 F：Python 版本与本地环境

- 本机 `python` = 3.13.14；CI = 3.11。
- `SQLAlchemy 2.1.8` + `pydantic 2.14.3` + `fastapi 0.162.0` 已在本机 `.venv` 装好。
- → 代码必须兼容 **3.11 ~ 3.13**（不用 3.12+ 语法如 `type` 语句、不用 `@override` 装饰器）。

### 12.7 🟡 风险 G：`registry/skills.json` 是生成物，含 `generatedAt`

任何"重建索引"都会改动时间戳 → 制造无意义 diff。**处置**：`SkillRegistry.refresh()` 默认只读；写回仅在显式 `--write` 时；测试中对 `generatedAt` 做忽略比较。

### 12.8 🟡 风险 H：模板公式无法用 openpyxl 求值

`openpyxl` 读写公式文本但不计算。底稿模板内大量公式（合计、勾稽）。**处置**：Workpaper Writer 只**写入**公式文本并用 Python 独立复算关键勾稽值做交叉校验；不在运行时求值 Excel。此项在 `docs/development/bank-deposits-e2e.md` 标注为已知限制。

### 12.9 🟡 风险 I：`auditox-wp-standard` 的 DSL 程序是 `G0`/`G1`

程序 ID 规则不是 `P\d+`。任何 `^P\d+$` 正则会把规范型包的程序全部漏掉。**处置**：ID 正则用 `^[A-Z]\d+$`。

---

## 13. 与目标架构的差异对照（任务书 PART 3/4）

| 任务书要求 | 现状 | 差异类型 |
| --- | --- | --- |
| Interface Layer：CLI / REST / MCP | 全无 | 全新 |
| Application Layer：TaskApplicationService | 全无 | 全新 |
| Agent Runtime：Planner/Orchestrator/Executor | 全无 | 全新 |
| Skill Layer：Registry/Loader/Parser/Router | 有 `build_index.py`（只到"生成索引"），无加载/解析/路由 | 部分可复用 |
| Tool Layer：11 个确定性工具 | 只有名字，无实现 | 全新 |
| Quality Layer | 无 | 全新 |
| Infrastructure：DB/Storage/LLM/Security | 无 | 全新 |
| 混合模式（Standalone + MCP） | MCP 无 | 全新 |
| Pydantic v2 统一模型 | 无 | 全新 |
| SQLite + SQLAlchemy 2.x | 无 | 全新 |
| `docs/workpaper-spec.md` | **不存在** | 文档缺口（用 `auditox-wp-standard/SKILL.md` 替代，不新建该文件身份） |

---

## 14. 事实基线（供验收对账）

| 指标 | 数值 |
| --- | --- |
| Git HEAD | `08d8c43`，与 origin/main 一致，工作区干净 |
| 跟踪文件 | 674 |
| 技能包 | 31（skill-group 26 / tool 3 / orchestrator 1 / standard 1） |
| 有 dsl.json 的包 | 27 |
| DSL 程序条目 | 190 |
| 程序卡 `.md` | 179 |
| 程序卡缺口 | 11（`f-6-payroll-payable` 7 份、`z-1-3` 2 份、`auditox-wp-standard` 2 份） |
| 全库声明工具名 | 15，**实现数 0** |
| Python 文件 | 38 个 / 11,302 行 |
| 根级 pytest 测试 | 0 |
| CI 检查项 | 2（结构校验 + 索引可生成） |
| 银行存款模板 | 2 版（v1.0 8 表 / v1.1 10 表） |
| 沙箱黄金数据 | 6 个 CSV，预埋异常 E1~E7 |

---

## 附录 A · 核查脚本

```bash
cd <repo>
# 1 形态与数量
python tools/build_index.py --check
# 2 结构校验
python tools/validate_skills.py
# 3 DSL 字段普查
python - <<'PY'
import json
from pathlib import Path
from collections import Counter
root=Counter(); proc=Counter()
for p in Path('skills').iterdir():
    d=p/'dsl.json'
    if not d.exists(): continue
    j=json.loads(d.read_text(encoding='utf-8'))
    root.update(j.keys())
    for pr in j.get('procedures') or []: proc.update(pr.keys())
print('root',root); print('procedure',proc)
PY
# 4 程序卡覆盖率
python - <<'PY'
import json
from pathlib import Path
for p in Path('skills').iterdir():
    d=p/'dsl.json'
    if not d.exists(): continue
    ids=[x['id'] for x in json.loads(d.read_text(encoding='utf-8')).get('procedures',[])]
    mds={f.name for f in (p/'procedures').glob('*.md')} if (p/'procedures').is_dir() else set()
    miss=[i for i in ids if not any(m.startswith(i) for m in mds)]
    if miss: print(p.name,'缺',miss)
PY
```
