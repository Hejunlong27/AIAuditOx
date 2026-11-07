"""技能层测试：注册表、DSL 归一化、分派表解析、三源合并、路由。

对真实仓库中的 ``skills/`` 做**只读**验证——这是把"运行时能读懂技能库"
变成可回归断言的地方。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.models.enums import ExecutionMode
from agent.skills import SkillLoader, SkillRegistry, SkillRouter
from agent.skills.parser import (
    DSLParser,
    DispatchTableParser,
    infer_policy,
    merge_procedure,
    parse_frontmatter,
)
from agent.security.workspace import SecurityError

pytestmark = pytest.mark.unit

BANK = "z-1-2-bank-deposits"


@pytest.fixture(scope="module")
def registry(repo_root: Path) -> SkillRegistry:
    return SkillRegistry(repo_root).load()


@pytest.fixture(scope="module")
def loader(repo_root: Path, registry: SkillRegistry) -> SkillLoader:
    return SkillLoader(repo_root, registry)


class TestRegistry:
    def test_loads_31_skills(self, registry: SkillRegistry) -> None:
        assert len(registry.list_ids()) == 31

    def test_variant_counts(self, registry: SkillRegistry) -> None:
        by_variant = {}
        for s in registry.list_skills():
            by_variant[s.variant] = by_variant.get(s.variant, 0) + 1
        assert by_variant["skill-group"] == 26
        assert by_variant["standard"] == 1

    def test_get_unknown_raises(self, registry: SkillRegistry) -> None:
        with pytest.raises(KeyError, match="未注册的技能"):
            registry.get("no-such-skill")

    def test_skill_path_inside_skills_dir(self, registry: SkillRegistry, repo_root: Path) -> None:
        p = registry.get_skill_path(BANK)
        assert p.is_dir()
        assert p.is_relative_to((repo_root / "skills").resolve())

    def test_search_bank(self, registry: SkillRegistry) -> None:
        hits = registry.search("银行存款 余额调节表")
        assert hits
        assert hits[0].id == BANK

    def test_search_empty_query(self, registry: SkillRegistry) -> None:
        assert registry.search("") == []


class TestFrontmatter:
    def test_parses_bank(self, loader: SkillLoader) -> None:
        loaded = loader.load_skill(BANK)
        assert loaded.frontmatter["name"] == BANK
        assert loaded.frontmatter["version"] == "1.0.0"

    def test_no_frontmatter(self) -> None:
        assert parse_frontmatter("# 标题\n正文") == {}

    def test_multiline_continuation(self) -> None:
        text = "---\nname: x\ndescription: 第一行\n  第二行\n---\n"
        data = parse_frontmatter(text)
        assert data["description"] == "第一行 第二行"


class TestDSLParser:
    def test_real_dsl_normalized(self, repo_root: Path) -> None:
        dsl = DSLParser().parse(repo_root / "skills" / BANK)
        assert dsl["skill_id"] == BANK
        assert len(dsl["procedures"]) == 10

    def test_skill_alias_accepted(self) -> None:
        # docs/skill-spec.md 写的根键是 skill，真实文件是 skill_id
        parsed = DSLParser().normalize({"skill": "x", "procedures": []})
        assert parsed["skill_id"] == "x"

    def test_human_tristate(self) -> None:
        parsed = DSLParser().normalize(
            {"procedures": [{"id": "P01", "name": "a"}, {"id": "P02", "name": "b", "human": False}]}
        )
        assert parsed["procedures"][0]["human"] is None  # 缺失 ≠ False
        assert parsed["procedures"][1]["human"] is False

    def test_bad_procedure_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="非法程序 ID"):
            DSLParser().normalize({"procedures": [{"id": "1P", "name": "a"}]})

    def test_lowercase_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="非法程序 ID"):
            DSLParser().normalize({"procedures": [{"id": "p01", "name": "a"}]})

    def test_duplicate_procedure_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="程序 ID 重复"):
            DSLParser().normalize(
                {"procedures": [{"id": "P01", "name": "a"}, {"id": "P01", "name": "b"}]}
            )

    def test_missing_procedures_ok(self) -> None:
        assert DSLParser().normalize({})["procedures"] == []


class TestDispatchTable:
    def test_bank_has_ten_rows(self, loader: SkillLoader) -> None:
        loaded = loader.load_skill(BANK)
        assert len(loaded.dispatch_rows) == 10
        assert [r.procedure_id for r in loaded.dispatch_rows] == [f"P{i:02d}" for i in range(1, 11)]

    def test_columns_mapped_by_header(self, loader: SkillLoader) -> None:
        row = next(r for r in loader.load_skill(BANK).dispatch_rows if r.procedure_id == "P01")
        assert row.assertions == ["C", "E"]
        assert row.workpaper_index == "Z-1-2-01"
        assert "自动" in row.execution_method

    def test_five_column_table_not_shifted(self, loader: SkillLoader) -> None:
        """s-1-revenue 的分派表少「执行方式」列，不能把产出底稿读成执行方式。"""
        rows = loader.load_skill("s-1-revenue").dispatch_rows
        assert rows, "s-1-revenue 应有程序分派表"
        first = rows[0]
        assert first.execution_method == "", "无执行方式列时必须为空，而不是产出底稿"
        assert first.workpaper_index is not None

    def test_special_workpaper_cell(self) -> None:
        parser = DispatchTableParser()
        text = (
            "| 程序卡 | 程序名称 | 程序库来源 | 对应认定 | 执行方式 | 产出底稿 |\n"
            "|---|---|---|---|---|---|\n"
            "| P05 | 银行函证 | Z1002 程序6 | C、E、A、P | 人工为主+控制表自动 | 引用《A.01 银行函证工作簿》 |\n"
        )
        rows = parser.parse(text)
        assert rows[0].workpaper_index is None  # 提不出索引，不许瞎猜
        assert rows[0].assertions == ["C", "E", "A", "P"]


class TestPolicyInference:
    @pytest.mark.parametrize(
        ("method", "human", "card", "expect_human", "expect_mode"),
        [
            ("自动（脚本核对）", False, False, False, ExecutionMode.AUTO),
            ("自动+人工确认", False, False, True, ExecutionMode.AUTO_WITH_CONFIRM),
            ("自动（重算）+人工判断", False, False, True, ExecutionMode.AUTO_WITH_JUDGMENT),
            ("人工为主（监盘/网银观察）", True, False, True, ExecutionMode.HUMAN_LED),
            ("", None, True, True, ExecutionMode.AUTO_WITH_CONFIRM),
        ],
    )
    def test_matrix(
        self,
        method: str,
        human: bool | None,
        card: bool,
        expect_human: bool,
        expect_mode: ExecutionMode,
    ) -> None:
        policy = infer_policy(method, human, card)
        assert policy.requires_human is expect_human
        assert policy.mode is expect_mode

    def test_never_lowers_human_requirement(self) -> None:
        """DSL 说 false，但正文要求人工 → 必须仍然要人。"""
        policy = infer_policy("自动+人工判断", False, False)
        assert policy.human_confirmation is True


class TestMergedProcedures:
    def test_ten_procedures_with_assertions(self, loader: SkillLoader) -> None:
        loaded = loader.load_skill(BANK)
        assert len(loaded.procedures) == 10
        p01 = next(p for p in loaded.procedures if p.id == "P01")
        assert p01.assertions == ["C", "E"]
        assert p01.workpaper_index == "Z-1-2-01"
        assert p01.tools == ["recalc_check", "balance_confirm"]

    def test_p05_is_mandatory_and_human(self, loader: SkillLoader) -> None:
        p05 = loader.load_procedure(BANK, "P05")
        assert p05.mandatory is True, "银行函证是强制程序"
        assert p05.execution_policy.requires_human is True
        assert p05.execution_policy.mode is ExecutionMode.HUMAN_LED

    def test_p03_is_human_led(self, loader: SkillLoader) -> None:
        p03 = loader.load_procedure(BANK, "P03")
        assert p03.execution_policy.mode is ExecutionMode.HUMAN_LED

    def test_conflicts_detected_and_resolved_strictly(self, loader: SkillLoader) -> None:
        """DSL human=false 但 SKILL.md 要求人工 → 必须有 BLOCKING 冲突记录。"""
        loaded = loader.load_skill(BANK)
        human_conflicts = [c for c in loaded.conflicts if c.field == "human"]
        ids = {c.procedure_id for c in human_conflicts}
        assert {"P02", "P04", "P07", "P09", "P10"}.issubset(ids), ids
        for c in human_conflicts:
            assert "保守" in c.resolved

    def test_conflict_procedures_require_human(self, loader: SkillLoader) -> None:
        for pid in ("P02", "P04", "P07", "P09", "P10"):
            assert loader.load_procedure(BANK, pid).execution_policy.requires_human, pid

    def test_conditional_procedure_p09(self, loader: SkillLoader) -> None:
        p09 = loader.load_procedure(BANK, "P09")
        assert p09.conditional is True
        assert p09.condition and "资金池" in p09.condition

    def test_dependencies_empty_from_skill_layer(self, loader: SkillLoader) -> None:
        """DSL 无依赖字段，技能层不得编造依赖。"""
        loaded = loader.load_skill(BANK)
        assert all(p.dependencies == [] for p in loaded.procedures)

    def test_missing_card_docs_reported(self, loader: SkillLoader) -> None:
        loaded = loader.load_skill("f-6-payroll-payable")
        assert loaded.missing_procedure_docs, "该包已知缺 7 份程序卡"

    def test_no_dsl_skill_returns_empty_procedures(self, loader: SkillLoader) -> None:
        loaded = loader.load_skill("confirmation-address-auditor")
        assert loaded.procedures == []
        assert loaded.dsl == {}

    def test_source_traceability(self, loader: SkillLoader) -> None:
        p01 = loader.load_procedure(BANK, "P01")
        assert p01.skill_id == BANK
        assert p01.skill_version == "1.0.0"
        assert p01.source.startswith("Z1002")
        assert p01.sources["assertions"] == "skill_md"
        assert p01.procedure_doc and p01.procedure_doc.startswith("procedures/")


class TestWorkpaperStandard:
    def test_load_standard(self, loader: SkillLoader) -> None:
        std = loader.load_wp_standard()
        assert len(std["sections"]) == 4
        assert "索引号" in std["header_elements"]
        assert std["path"].endswith("auditox-wp-standard")

    def test_list_templates(self, loader: SkillLoader) -> None:
        names = loader.list_templates(BANK)
        assert any(n.endswith(".xlsx") for n in names)

    def test_missing_template_raises_with_hint(self, loader: SkillLoader) -> None:
        with pytest.raises(FileNotFoundError, match="可用"):
            loader.load_template(BANK, "不存在.xlsx")

    def test_template_path_traversal_blocked(self, loader: SkillLoader) -> None:
        with pytest.raises(SecurityError):
            loader.load_template(BANK, "../../../pyproject.toml")


class TestRouter:
    def test_routes_bank_by_alias(self, registry: SkillRegistry) -> None:
        d = SkillRouter(registry).route("对某公司银行存款执行审计程序")
        assert d.skill_id == BANK
        assert d.needs_confirmation is False

    def test_routes_by_subject_code(self, registry: SkillRegistry) -> None:
        d = SkillRouter(registry).route("1002 科目审计")
        assert d.skill_id == BANK

    def test_unknown_request_asks_human(self, registry: SkillRegistry) -> None:
        d = SkillRouter(registry).route("帮我写一首诗")
        assert d.skill_id is None
        assert d.needs_confirmation is True

    def test_empty_request_asks_human(self, registry: SkillRegistry) -> None:
        d = SkillRouter(registry).route("")
        assert d.needs_confirmation is True

    def test_tie_requires_confirmation(self) -> None:
        """人为构造打平场景，必须交人工而不是随便选。"""
        from agent.skills.registry import SkillEntry

        class FakeRegistry(SkillRegistry):
            def __init__(self) -> None:  # noqa: D107
                self._entries = {
                    "a-x": SkillEntry("a-x", "甲", "1", "银行存款", "skill-group", "skills/a-x", (), 1),
                    "b-x": SkillEntry("b-x", "乙", "1", "银行存款", "skill-group", "skills/b-x", (), 1),
                }
                self._loaded = True

            def get(self, skill_id: str) -> SkillEntry:  # noqa: D102
                return self._entries[skill_id]

            def list_ids(self) -> list[str]:  # noqa: D102
                return sorted(self._entries)

            def list_skills(self, *, variant: str | None = None) -> list[SkillEntry]:  # noqa: D102
                return [self._entries[k] for k in self.list_ids()]

            def search(self, query: str, *, limit: int = 10) -> list[SkillEntry]:  # noqa: D102
                return [e for e in self.list_skills() if "银行存款" in e.description]

        decision = SkillRouter(FakeRegistry()).route("银行存款")
        assert decision.needs_confirmation is True
        assert decision.skill_id is None

    def test_confirm_route_rejects_standard(self, registry: SkillRegistry) -> None:
        with pytest.raises(ValueError, match="不能作为审计任务主技能"):
            SkillRouter(registry).confirm_route("auditox-wp-standard")

    def test_confirm_route_accepts_bank(self, registry: SkillRegistry) -> None:
        d = SkillRouter(registry).confirm_route(BANK)
        assert d.decided is True
