# AGENTS.md — 审小牛 AIAuditOx Agent 指令

> 本文件是本仓库的**唯一 agent 入口**。任何 agent（Claude Code / Codex / Cursor / WorkBuddy / 自建运行时）在本仓库工作时，先读本文件，再按需读 `docs/`。
> 修改本文件等于修改 agent 行为，需在 PR 中说明理由。

---

## 1. 项目定位

AIAuditOx 把审计程序库逐条拆解成**可复用、可组合、可扩展的 AI 技能**：一个科目一个技能组，一道程序一张程序卡，凡能本地算完的一律交给确定性工具。

**三件套**（缺一不可）：

| 件 | 作用 | 位置 |
| --- | --- | --- |
| 技能库 | 方法论载体：六要素、程序分派表、复核清单、边界 | `skills/` |
| 确定性工具 | 勾稽、重算、抽样、索引号、哈希——不用模型估算 | 各包 `scripts/`、`dsl.json` 的 `tools` |
| 底稿制式 | 四段式输出规范，保证同一 agent 产出一致 | `skills/auditox-wp-standard/` |

**确定性优先**：凡是能本地算的（金额勾稽、比例重算、抽样、索引号、文件哈希）一律调确定性工具；LLM 只做分析、解释、判断。差异类结论必须标注「待人工确认」。

---

## 2. 目录结构

```
skills/                        31 个技能包，一包一目录
├── auditox-wp-standard/       ★ 全局底稿制式，编制任何底稿前必须加载
├── z-*-*/ f-*-*/ s-*-*/       26 个科目技能组（资产 / 负债 / 损益）
├── heavy-asset-financial-analysis/   总控型（roles/ 子技能）
├── financial-statement-analysis/     工具型（scripts/ + rules/）
└── doc-ocr-extract/                  工具型（原始凭证 → 结构化输入）
registry/skills.json           技能索引（由 tools/build_index.py 生成，勿手改）
docs/                          架构、技能规范、编号对照
tools/                         索引生成与校验脚本
```

**两类技能包的判别**（靠结构，不靠包名）：

| 形态 | 判别 | 特征 |
| --- | --- | --- |
| 技能组 | 含 `SKILL.md` + `dsl.json` + `procedures/` | 六要素 + 程序分派表 + P01~Pn 程序卡 |
| 总控型 | 含 `roles/` 子目录 | 1 总控 + N 子技能，负责路由与调度 |
| 工具型 | 含 `scripts/` + `rules/`，无 `roles/` | 单体执行，按 `SKILL.md` 的工作方法跑 |

---

## 3. 调用协议

**按顺序判断，不要跳步：**

1. **识别科目** —— 用户提到报表科目（如「银行存款」）→ 在 `registry/skills.json` 查对应 `skill_id`。
2. **先加载底稿制式** —— 任何要产出底稿的任务，先读 `skills/auditox-wp-standard/SKILL.md`。
3. **再加载科目技能** —— 读该包的 `SKILL.md`，按「程序分派表」确定要执行哪几张程序卡。
4. **按卡执行** —— 读 `procedures/Pxx-*.md`，按其「输入 / 步骤 / 质量门 / 升级路径」执行。
5. **原始凭证先过 OCR** —— 输入是扫描件/照片/PDF 时，先用 `doc-ocr-extract` 转成结构化 JSON，再做后续程序。
6. **确定性工具优先** —— `dsl.json` 的 `procedures[].tools` 列出了该卡应调的工具，能调就调，不要用模型估算数字。
7. **输出前自查** —— 按该包「一级复核清单」逐项过，再交结果。

**升级规则**：程序卡里的「质量门」不通过、或数据缺失无法判断时，**不要猜**。按「升级路径」标注待人工确认项，把缺口列清楚交回。

---

## 4. 开发规范

### 新增一个科目技能组

1. 建目录 `skills/<skill_id>/`（`<skill_id>` 用 `<组>-<科目号>-<英文名>`，如 `z-1-2-bank-deposits`）
2. `SKILL.md` frontmatter 必须有 `name` / `description` / `version`
3. 「程序分派表」必须是标准 Markdown 表格，表头含：程序卡 / 程序名称 / 程序库来源 / 对应认定 / 执行方式 / 产出底稿
4. `dsl.json` 声明 `procedures[].tools`
5. 程序卡文档放 `procedures/P01-<名称>.md`
6. `CHANGELOG.md` 记录首次发布

### 版本与变更

- 语义化版本：修内容 → patch；加程序卡 → minor；改结构/断后向兼容 → major
- 每次改动必须更新该包 `CHANGELOG.md`（倒序，最新在上）
- 只记技能内容变更，不记分发渠道动作

### 提交前必须跑

```bash
python tools/build_index.py      # 重建 registry/skills.json
python tools/validate_skills.py  # 校验结构、frontmatter、程序卡引用
```

两项都通过再提交。CI 会跑同样的检查。

---

## 5. 硬边界

- **不出审计意见**。所有输出是工作底稿与执行记录，不构成审计结论或专业建议。
- **客户数据不出本机**。禁止把客户资料传给公开的 AI 服务；`doc-ocr-extract` 设计为全程本地推理。
- **不伪造出处**。引用准则、程序库来源必须真实可查；无公认典故/无原文依据时明确声明是自编。
- **差异必标注**。任何比对不一致，标「待人工确认」，不自行判定为错误。
- **不提交凭证**。API key、token、客户名称、真实金额明细一律不进仓库。

---

## 6. 给 agent 的运行时约定（后续升级用）

当前仓库是**技能库 + 规范**，agent 运行时尚未内置。计划中的升级方向：

- `agent/` —— 运行时配置（模型、工具注册、路由策略）
- `agent/router.md` —— 科目路由与技能编排规则
- 保持 `skills/` 为纯内容层，运行时通过 `registry/skills.json` 发现技能

**约束**：新增运行时不得把业务逻辑写进 `skills/`；技能包必须能被任意 agent 直接读取使用（无运行时也能工作）。
