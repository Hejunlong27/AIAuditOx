# 辅助技能通用能力迁移矩阵

> 日期：2026-11-12
> 范围：`confirmation-address-auditor`、`doc-ocr-extract`、`financial-statement-analysis`、`heavy-asset-financial-analysis`、`universal-annual-audit`
> 状态：只读侦察完成；P3-1 Runtime 能力配置与技能包清单分发已完成；未删除任何技能脚本。
> 原则：中心工具是唯一源码；技能专属逻辑保留；独立安装使用发布时生成的兼容实现。

## 1. 侦察摘要

- 5 个辅助技能包共有 40 个 Python/测试脚本。
- 跨包“完全相同函数体”很少，仅发现：
  - OCR 发票/合同抽取中的 `_yc`。
  - `universal-annual-audit` 内两处 `read_json`。
- 大量重复是**语义重复**而非文本克隆：
  - Excel/CSV/PDF/Word 读取。
  - 金额、日期、表头、标签归一化。
  - 数据完整性校验。
  - Excel/Word/Markdown 报表输出。
  - 文件哈希、证据清单、manifest。

结论：不能按函数名机械抽离；必须按能力边界和等价比对迁移。

## 2. 迁移分类

| 能力 | 主要来源 | 迁移判定 | 中心落点 | 独立 Skill 兼容方式 |
|---|---|---|---|---|
| Excel/CSV 读取 | address reader、fs loader、universal extractor | 中心优先 | `excel_read`、`sheet_to_csv` | 保留技能本地读取；发布时生成兼容包 |
| PDF/OCR 输入 | doc OCR loader、address reader | 拆分 | PDF 工具负责输入；OCR 领域抽取留技能 | OCR 技能本地脚本 |
| 金额/日期/标签归一化 | fs loader、universal extractor、doc validate | 中心优先 | 新 Python 共享能力或现有确定性工具 | 兼容工具随技能包生成 |
| 财务比率/期间/YoY | fs analysis、heavy asset、universal | 按公式匹配 | 已有明确公式用中心工具；其余先做候选 | 保留本地实现 |
| 账龄/准备/折旧/利息/截止 | 科目技能 DSL | 已中心化 | 现有 Node 工具 | 无 AuditOx 时使用生成兼容包 |
| 哈希/证据/manifest | address attachment、doc writer、universal source register | 中心优先 | 新 evidence/hash 工具；已有 `manifest_json` | 保留本地证据读取 |
| Excel/Word 底稿输出 | address report builder、fs reports、universal templates | 中心优先 | `workpaper_spec`、`xlsx_export`、`wp_to_docx` | 兼容导出器随包生成 |
| 地址/主体名称匹配 | address normalizer、matcher | 保留技能 | 不迁 | 本地专属实现 |
| 函证风险判断 | address risk engine | 保留技能 | 不迁 | 本地专属实现 |
| 发票/合同字段抽取 | doc invoice/contract extract | 保留技能 | 不迁 | 本地专属实现 |
| 财报项目映射与分析判断 | fs config/profile/analysis | 保留技能 | 不迁 | 本地专属实现 |
| 重资产敏感性分析 | heavy fin_metrics/data_qc | 保留技能 | 不迁 | 本地专属实现 |
| 年报概览 SVG/报告叙事 | universal overview/reports | 保留技能 | 不迁 | 本地专属实现 |

## 3. 逐技能矩阵

### confirmation-address-auditor

| 模块 | 判定 | 说明 |
|---|---|---|
| `reader.py` 多格式读取 | 中心优先，技能兼容保留 | 可优先使用中心 Excel/PDF 读取；Word/CSV 边界需进一步统一 |
| `normalizer.py` 地址/主体归一化 | 保留 | 业务语义强，不宜通用化 |
| `matcher.py`、`risk_engine.py` | 保留 | 函证核对与风险判断专属 |
| `report_builder.py` 表格样式/Word 输出 | 拆分 | 底层文件输出用中心工具；函证报告结构保留 |
| `attachment.py` 证据清单/哈希 | 中心候选 | 需要统一 evidence/hash 工具 |
| `run.py` | 保留 | 技能编排入口 |

### doc-ocr-extract

| 模块 | 判定 | 说明 |
|---|---|---|
| `ocr_core/engine.py`、`loader.py` | OCR 能力保留 | 模型、缓存与版面处理属于 OCR 专属 |
| `ocr_core/validate.py` 金额/日期/USCC | 拆分 | 通用金额/日期可中心化；税号校验规则保留 |
| `ocr_core/writer.py` 输出 | 部分中心化 | JSON/Markdown 保留；证据/manifest 可中心化 |
| `extract_invoice.py`、`extract_contract.py` | 保留 | 文档类型专属抽取 |
| `run_ocr.py` | 保留 | OCR 流程编排 |

### financial-statement-analysis

| 模块 | 判定 | 说明 |
|---|---|---|
| `loader.py` 工作簿定位/表头/期间解析 | 拆分 | 通用 Excel 读取用中心；财报项目映射保留 |
| `profile.py` 科目别名与抵消 | 保留 | 财报语义专属 |
| `analysis.py` 指标、勾稽、异常等级 | 拆分 | `safe_div`、YoY 等候选中心化；判断规则保留 |
| `reports.py` Excel 样式与底稿输出 | 中心优先 | 优先使用 `workpaper_spec` / `xlsx_export` |
| `pipeline.py` | 保留 | 技能内部编排 |

### heavy-asset-financial-analysis

| 模块 | 判定 | 说明 |
|---|---|---|
| `data_qc.py` 数据完整性检查 | 部分中心化 | 通用 schema/期间检查可复用；重资产规则保留 |
| `fin_metrics.py` 财务指标/敏感性 | 保留 | 业务公式与行业判断专属 |
| 输出渲染 | 中心候选 | 通用表格导出可复用中心工具 |

### universal-annual-audit

| 模块 | 判定 | 说明 |
|---|---|---|
| `extract_financial_data.py` | 拆分 | 通用 Excel/CSV 读取和数字归一化可中心化 |
| `calculate_financial_ratios.py` | 拆分 | `normalize_label`、`parse_number`、`safe_div`、YoY 为候选 |
| `source_register.py` | 拆分 | 哈希、去重、证据登记可中心化；登记业务字段保留 |
| `build_templates.py`、`generate_reports.py` | 中心优先 | 底层 Excel/Word 输出使用中心工具；年报模板/叙事保留 |
| `build_overview.py` | 保留 | SVG 年报概览专属 |
| `peer_comparison.py` | 保留 | 同业分析口径专属 |

## 4. P3 实施顺序

### P3-1：技能能力清单（已完成）

已新增 Runtime 侧配置：

`config/skill-tool-requirements.json`

加载优先级：

1. 技能包自身 `tool-requirements.json`。
2. Runtime 侧技能覆盖配置。
3. `dsl.json` 推导的 required 工具。

当前 5 个辅助技能均已配置：

- `required`：无中心工具硬依赖，保证无 AuditOx 时仍可使用本地脚本。
- `preferred`：有 AuditOx 时优先使用中心工具，`fallback=skill_local`。
- `optional`：缺失仅提示。

能力清单已通过 `tools/sync_skill_tool_requirements.py` 生成到 5 个技能包；中心配置仍是唯一源，生成物只用于运行时识别与发布。

已完成：

- 生成器支持 `--check` / `--write`。
- `--check` 已纳入测试，防止配置和技能包清单漂移。
- 5 个技能包均保留原有脚本，standalone 模式未受影响。

### P3-2：低风险共享能力试点（已完成）

已建立唯一 Python 公共源码：

`skill-tools/auditox-python-core/`

已抽取并替换：

- `safe_div`
- `yoy_change`（支持普通分母与绝对值分母）
- `sha256_file`
- `parse_number_flexible` / `parse_number_strict`
- `normalize_label`

已替换技能：

- `financial-statement-analysis`：`safe_div`
- `universal-annual-audit`：`safe_div`、YoY 数值计算
- `heavy-asset-financial-analysis`：安全除法、YoY 数值计算
- `doc-ocr-extract`：文件 SHA-256
- `financial-statement-analysis`：宽松金额解析、项目名称归一化
- `universal-annual-audit`：严格金额解析、标签归一化、金额解析 fallback

兼容策略：

- 原技能函数签名和业务包装保留。
- 数值计算委托共享核心。
- 技能包内 `scripts/auditox_common/` 为生成副本。
- 中心源码与生成副本由 `tools/sync_python_core.py` 检查漂移。

### P3-3：报表输出收敛（进行中）

已完成第一批基础工作：

- Word run 字体应用收敛到 `auditox_common.docx_style.set_run_font`。
- `confirmation-address-auditor` 和 `financial-statement-analysis` 已接入。
- 新增 Excel/Word 结构指纹：
  - 单元格值、公式、格式、字体、填充、边框、列宽、行高、合并区域。
  - Word 段落、run、表格、页面尺寸与边距。
- 新增比较 CLI：
  `python agent-runtime/tools/report_fingerprint.py 基线文件 --diff 新文件`

尚未迁移：

- Excel 整体布局和样式构造。
- Word 表格布局和分页。
- 各技能专属报告结构与文案。

### P3-4：独立 Skill 兼容包

- 在发布打包时，从中心源码生成兼容实现。
- 禁止技能仓库和中心工具各手工维护一份。
- 兼容包携带工具版本并写入运行证据。

## 5. 暂不迁移

- 地址与主体名称相似度算法。
- 函证风险分级。
- 发票/合同字段抽取。
- 财报项目映射和异常等级判断。
- 重资产敏感性模型。
- 年报叙事、SVG、PPT/Word 版式。
- 任何依赖客户上下文或审计专业判断的规则。

## 6. 验收要求

每个迁移候选必须同时通过：

1. 中心工具单元测试。
2. 技能原脚本黄金用例。
3. 迁移前后 JSON/文件输出等价比对。
4. AuditOx 模式测试。
5. 无 AuditOx 的 standalone 模式测试。
6. 路径边界与敏感数据不进日志测试。
