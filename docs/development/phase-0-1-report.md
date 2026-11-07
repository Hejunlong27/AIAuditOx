# Phase 0 + Phase 1 交付报告

> 日期：2026-11-07
> 基线提交：`08d8c43`（与 `origin/main` 一致）
> 本轮交付：Phase 0（工程基础）+ Phase 1（Skill Runtime）

---

## 1. 本阶段实现的功能

### Phase 0 · 工程基础

| 功能 | 落地位置 | 可验证行为 |
| --- | --- | --- |
| 工程配置与依赖锁定 | `pyproject.toml` | `pip install -e ".[dev]"` 可装；`auditox` 入口预留 |
| 统一数据模型（9 个模块） | `agent/models/` | `extra="forbid"`、UTC 强制、金额 `Decimal` |
| SQLite + SQLAlchemy 9 张表 | `agent/storage/` | 外键强制、WAL、索引、乐观锁 |
| 工作区隔离与路径穿越防护 | `agent/security/workspace.py` | `..`/绝对路径/符号链接/NUL 全部拒绝 |
| 原始资料只读 + SHA256 登记 | 同上 | 写原始资料目录被拒；篡改可检出 |
| 工具白名单与权限预算 | `agent/security/permissions.py` | 未注册工具拒绝；网络/Shell/破坏性恒禁 |
| 结构化脱敏审计日志 | `agent/security/audit_log.py` | 账号/身份证/手机/邮箱落盘前脱敏 |
| 配置单一真相 | `agent/config/settings.py` | 路径派生、DB URL 派生、默认关闭外网 |

### Phase 1 · Skill Runtime

| 功能 | 落地位置 | 可验证行为 |
| --- | --- | --- |
| 技能注册表（唯一索引源） | `agent/skills/registry.py` | 读到 31 包；中文 2-gram 检索；路径不越界 |
| 技能加载器 | `agent/skills/loader.py` | 读 SKILL.md/dsl/程序卡/模板/底稿制式 |
| DSL 归一化（容忍文档与实物差异） | `agent/skills/parser.py` | `skill`→`skill_id` 兼容；`human` 三态 |
| 分派表解析（按表头取列） | 同上 | 5 列包不会把「产出底稿」读成「执行方式」 |
| 三源合并 + 冲突报告 | 同上 | 银行存款 10 程序、5 条 BLOCKING 冲突 |
| 技能路由（含糊即问人） | `agent/skills/router.py` | 打平/低分返回候选 + `needs_confirmation` |

---

## 2. 新增文件列表

```
pyproject.toml
agent/__init__.py
agent/models/{__init__,base,enums,task,plan,procedure,evidence,approval,result,tool}.py
agent/storage/{__init__,database,orm}.py
agent/security/{__init__,workspace,permissions,audit_log}.py
agent/config/{__init__,settings}.py
agent/skills/{__init__,registry,loader,parser,router}.py
tests/__init__.py
tests/conftest.py
tests/unit/{test_models,test_storage,test_workspace_security,test_audit_log,test_settings,test_skills}.py
tests/{integration,e2e,fixtures,golden}/          (空目录，Phase 3+ 填充)
docs/development/repository-analysis.md
docs/development/architecture.md
docs/development/phase-0-1-report.md
```

## 3. 修改文件列表

| 文件 | 改动 | 理由 |
| --- | --- | --- |
| `.gitignore` | 增加 `storage/ workspaces/ artifacts/ *.db .coverage htmlcov/` | 客户数据与运行产物绝不入库 |
| `README.md` | 新增「Agent Runtime（开发中）」章节 | 说明当前能力与进度，不夸大 |

**未修改**：`skills/`（658 文件）、`registry/skills.json`、`tools/*.py`、`.github/workflows/validate.yml`、`AGENTS.md`、`docs/skill-spec.md`、`docs/architecture.md`。
`git status --porcelain skills registry tools .github` 输出为空，可复核。

---

## 4. 核心类与函数

| 类 / 函数 | 文件 | 说明 |
| --- | --- | --- |
| `SkillRegistry.load/search/get/get_skill_path/refresh` | `skills/registry.py` | 只读索引；`refresh(write=False)` 复用 `tools/build_index.py` |
| `SkillLoader.load_skill/load_procedure/load_template/load_wp_standard` | `skills/loader.py` | 技能包 → `LoadedSkill` |
| `DSLParser.parse/normalize` | `skills/parser.py` | 真实 schema 归一化 + `human` 三态 |
| `DispatchTableParser.parse` | `skills/parser.py` | 按表头名映射列 |
| `merge_procedure` | `skills/parser.py` | 三源合并，产出 `ProcedureDefinition` + 冲突 |
| `infer_policy` | `skills/parser.py` | 保守策略推导 `ExecutionPolicy` |
| `SkillRouter.route/search_candidates/confirm_route` | `skills/router.py` | 三级路由 |
| `Workspace.create/resolve_inside/resolve_for_write/register_raw_file/verify_raw_unchanged/backup` | `security/workspace.py` | 隔离与溯源 |
| `PermissionPolicy.check_tool/record_call` | `security/permissions.py` | 白名单与预算 |
| `JsonLineAuditLogger.emit` | `security/audit_log.py` | 结构化 + 脱敏 |
| `Database.session/create_all` | `storage/database.py` | 事务边界 |
| `to_money` | `models/base.py` | 金额安全解析（float 经 `repr`） |

---

## 5. 数据库变更

新建 9 张表（`agent/storage/orm.py`）：

| 表 | 主键 | 关键约束 |
| --- | --- | --- |
| `projects` | `project_id` | `version` 乐观锁 |
| `tasks` | `task_id` | FK→projects；`ix_tasks_project_status` |
| `plans` | `plan_id` | FK→tasks |
| `plan_steps` | 自增 id | `UNIQUE(task_id, step_id)` |
| `tool_runs` | `execution_id` | FK→tasks；`tool_name` 索引 |
| `evidences` | `evidence_id` | FK→tasks；`procedure_id` 索引 |
| `approvals` | `approval_id` | FK→tasks；`status` 索引 |
| `artifacts` | `artifact_id` | FK→tasks；只存路径+SHA256，不存二进制 |
| `audit_events` | 自增 id | FK→tasks（可空，容纳项目级事件） |

SQLite PRAGMA：`foreign_keys=ON`、`journal_mode=WAL`、`synchronous=NORMAL`、`busy_timeout=5000`。

## 6. API 变更

无。Phase 6 实现。

---

## 7-8. 测试结果

```
$ .venv/Scripts/python.exe -m pytest tests -q
127 passed
```

| 测试文件 | 用例数 | 覆盖内容 |
| --- | ---: | --- |
| `test_models.py` | 30 | 9 类模型、枚举、金额解析、时区、`extra=forbid` |
| `test_storage.py` | 12 | 9 表存在、外键、唯一约束、事务回滚、乐观锁、PRAGMA |
| `test_workspace_security.py` | 21 | 4 类路径穿越、只读、篡改检测、备份、权限、Shell |
| `test_audit_log.py` | 11 | 4 类 PII 模式、金额不误伤、JSONL 格式、trace_id |
| `test_settings.py` | 7 | 路径派生、DB URL、默认关闭外网 |
| `test_skills.py` | 47 | 注册表、DSL 三态、5 列表不错位、策略矩阵、冲突、条件程序、路由打平 |

覆盖率（`--cov=agent`）：**92%**（1379 语句，117 未覆盖）。

**集成测试**：本轮仅覆盖「技能层 → 模型层」链路（`test_skills.py` 直接对真实 `skills/` 断言），
完整集成链（Registry→…→Quality Gate）待 Phase 4/5 后补齐。

### 真实技能库验证输出

```
技能 z-1-2-bank-deposits v1.0.0 | 程序 10 条 | 冲突 5 条 | 缺卡 []

ID   强制  人工  模式                认定      底稿       工具
P01  —    —    AUTO                C,E      Z-1-2-01  recalc_check,balance_confirm
P02  —    是    AUTO_WITH_CONFIRM   C        Z-1-2-02  —
P03  —    是    HUMAN_LED           E,A      Z-1-2-03  —
P04  —    是    AUTO_WITH_JUDGMENT  C,E,A    Z-1-2-04  recon_statement_recalc,threshold_flag
P05  是   是    HUMAN_LED           C,E,A,P  —         —
P06  —    —    AUTO                A,C,E    Z-1-2-06  bank_reconcile_dual,sampling_draw
P07  —    是    AUTO_WITH_JUDGMENT  C,E,A    Z-1-2-07  —
P08  —    —    AUTO                C,E,A    Z-1-2-08  recalc_check,threshold_flag
P09  —    是    AUTO_WITH_JUDGMENT  C,E,A    Z-1-2-09  —
P10  —    是    AUTO_WITH_CONFIRM   P        Z-1-2-10  rule_check
```

冲突 5 条（全部 `BLOCKING`，已按保守策略判为需人工）：P02 / P04 / P07 / P09 / P10。
条件程序 1 条：P09「视资金池/集团情况决定是否启用」。

---

## 9. 失败测试及原因

无。过程中修复 1 处测试自身缺陷：`test_missing_raw_detected` 初始版本直接 `unlink()`
只读文件，被 Windows 拒绝（`WinError 5`）——这恰好证明只读防护有效，改为先 `chmod` 解除只读再删。

## 10. 尚未解决的问题

| 问题 | 性质 | 处理计划 |
| --- | --- | --- |
| `docs/skill-spec.md` 的 dsl 示例与实物不符 | 文档未改（避免越界改规范） | Phase 2 在 `data-model.md` 记录事实，技能版本升级时统一 |
| 执行方式 130+ 种自由文本 | 只做 `含"人工"` 的宽松推断 | Phase 2 由 `bank_deposits.yaml` 显式声明为准 |
| DSL 无 `dependencies` | 技能层返回空，不编造 | Phase 2 配置提供 DAG |
| 程序卡缺 11 份 | 加载器上报 `missing_procedure_docs` | 不补写；质量门告警 |
| Excel 公式不求值 | `openpyxl` 限制 | Phase 5 Python 侧独立复算交叉校验 |
| LLM 适配器未实现 | 第一版可全程确定性 | Phase 2 起按需接入 |

## 11. 下一阶段建议（Phase 2）

1. 定义 `agent/config/procedures/bank_deposits.yaml` 的 Schema（Pydantic），含 `depends_on` / `mandatory` / `conditional` / `tools` / `required_inputs`，并加校验测试。
2. 写 `SkillValidator`：把「DSL + SKILL.md + yaml」合成后做完整性校验（强制程序不可缺、依赖不可成环）。
3. `AuditPlanner.build_plan()`：拓扑分层、循环依赖检测、输入缺口识别、人工/条件程序识别，输出可解释 `AuditPlan`。
4. Planner 阶段必须能对 P01→(P02,P08)→P04→P06→P07→P10 这条真实顺序给出与 SKILL.md 一致的 `execution_order`。
5. 补 `docs/development/data-model.md` 与 `skill-runtime.md`。
