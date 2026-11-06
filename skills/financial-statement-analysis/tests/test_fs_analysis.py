"""分析程序的自动化测试：复算一致性、边界情况与分级口径。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import make_sample  # noqa: E402
from fs_analysis import analysis, pipeline  # noqa: E402
from fs_analysis.loader import load_workbook  # noqa: E402
from fs_analysis import profile  # noqa: E402


@pytest.fixture(scope="module")
def sample_path(tmp_path_factory):
    outdir = tmp_path_factory.mktemp("sample")
    path = outdir / "示例-四张报表.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "资产负债表"
    make_sample.build_balance_sheet(ws)
    make_sample.build_income_statement(wb.create_sheet("利润表"))
    make_sample.build_cash_flow(wb.create_sheet("现金流量表"))
    make_sample.build_equity_statement(wb.create_sheet("所有者权益变动表"))
    wb.save(path)
    return path


@pytest.fixture(scope="module")
def outcome(sample_path, tmp_path_factory):
    outdir = tmp_path_factory.mktemp("output")
    return pipeline.run(sample_path, outdir=outdir, entity="示例制造有限公司",
                        period="2025年度", materiality=None)


# ---------------------------------------------------------------- 加载与映射


def test_all_four_statements_loaded(sample_path):
    report = load_workbook(sample_path)
    assert set(report.statements) == {"资产负债表", "利润表", "现金流量表", "所有者权益变动表"}


def test_key_figures_parsed_correctly(sample_path):
    report = load_workbook(sample_path)
    assert report.get("利润表", "营业收入") == (156000000.0, 120000000.0)
    assert report.get("资产负债表", "应收账款") == (42300000.0, 26500000.0)
    assert report.get("资产负债表", "资产总计") == (200000000.0, 155200000.0)
    assert report.get("现金流量表", "经营活动产生的现金流量净额") == (13500000.0, 20000000.0)
    assert report.get("所有者权益变动表", "本年年末余额") == (91800000.0, 76400000.0)


def test_prefix_and_alias_mapping():
    assert profile.resolve_item("减：营业成本")[0] == "营业成本"
    assert profile.resolve_item("其中：利息费用")[0] == "利息费用"
    assert profile.resolve_item("主营业务收入")[0] == "营业收入"
    assert profile.resolve_item("预收款项")[0] == "合同负债"
    assert profile.resolve_item("没有任何对应关系的项目")[0] is None


def test_unmapped_items_are_recorded_not_dropped(sample_path):
    report = load_workbook(sample_path)
    eq_unmapped = report.statement("所有者权益变动表").unmapped
    assert any("上年年末余额" in name for name in eq_unmapped)
    assert any("本年增减变动金额" in name for name in eq_unmapped)


# ---------------------------------------------------------------- 数据校验


def test_balance_sheet_ties(outcome):
    result = outcome["result"]
    ties = [r for r in result.validation if r["检查项"] in ("资产负债表平衡", "资产负债权益")]
    assert ties, "应生成资产负债表勾稽检查"
    assert all(r["结论"] == "通过" for r in ties)


def test_equity_rollforward_ties(outcome):
    result = outcome["result"]
    rows = [r for r in result.validation if r["检查项"] == "权益变动勾稽"]
    assert rows
    assert all(r["结论"] == "通过" for r in rows), [r["说明"] for r in rows]


def test_cash_flow_ties(outcome):
    result = outcome["result"]
    rows = [r for r in result.validation if r["检查项"] == "现金流量表勾稽"]
    assert rows
    assert all(r["结论"] == "通过" for r in rows)


def test_cross_statement_net_profit_matches(outcome):
    result = outcome["result"]
    rows = [r for r in result.validation if r["检查项"] == "表间勾稽"]
    assert rows and all(r["结论"] == "通过" for r in rows)


# ---------------------------------------------------------------- 比率复算


def test_ratio_recomputation(outcome):
    ratios = {r["指标"]: r for r in outcome["result"].ratios}
    gross_margin = (156000000 - 103000000) / 156000000
    assert ratios["毛利率"]["本期"] == pytest.approx(gross_margin)
    prior_margin = (120000000 - 84000000) / 120000000
    assert ratios["毛利率"]["上期"] == pytest.approx(prior_margin)
    assert ratios["毛利率"]["变动"] == pytest.approx(gross_margin - prior_margin)

    # 流动资产 / 流动负债
    assert ratios["流动比率"]["本期"] == pytest.approx(118000000 / 88200000)
    # 平均余额口径周转率
    ar_avg = (42300000 + 26500000) / 2
    assert ratios["应收账款周转率"]["本期"] == pytest.approx(156000000 / ar_avg)
    # 杜邦分解恒等关系
    net_margin = ratios["净利率(杜邦)"]["本期"]
    turnover = ratios["总资产周转率(杜邦)"]["本期"]
    multiplier = ratios["权益乘数"]["本期"]
    assert net_margin * turnover * multiplier == pytest.approx(ratios["净资产收益率"]["本期"])


def test_turnover_prior_period_note(outcome):
    ratios = {r["指标"]: r for r in outcome["result"].ratios}
    assert "期末余额" in ratios["应收账款周转率"]["备注"]


# ---------------------------------------------------------------- 期望值复算


def test_expectation_models_recompute(outcome):
    rows = {r["项目"]: r for r in outcome["result"].expectation}
    prior_margin = (120000000 - 84000000) / 120000000
    expected_cost = 156000000 * (1 - prior_margin)
    assert rows["营业成本"]["期望值"] == pytest.approx(expected_cost)
    assert rows["营业成本"]["差异"] == pytest.approx(103000000 - expected_cost)
    # 可容忍差异 = max(重要性水平×50%, 期望值×5%)
    materiality = outcome["result"].meta["materiality"]
    assert rows["营业成本"]["可容忍差异"] == pytest.approx(max(materiality * 0.5, expected_cost * 0.05))

    expected_ar = 26500000 * (1 + (156000000 - 120000000) / 120000000)
    assert rows["应收账款"]["期望值"] == pytest.approx(expected_ar)


def test_chart_data_present(outcome):
    data = outcome["result"].meta["chart_data"]
    assert data["income"]
    assert data["balance"]


# ---------------------------------------------------------------- 一致性检查


def test_consistency_rules_trigger(outcome):
    rows = {r["检查项"]: r for r in outcome["result"].consistency}
    assert rows["收入与应收账款背离"]["是否触发"] == "触发"
    assert rows["毛利率异常变动"]["是否触发"] == "触发"
    assert rows["其他应收款异常增长"]["是否触发"] == "触发"
    assert rows["利润与经营现金流背离"]["是否触发"] == "触发"
    assert rows["回款质量不足"]["是否触发"] == "触发"


# ---------------------------------------------------------------- 分级


def test_low_confidence_model_capped_at_l2(outcome):
    rows = {r["项目"]: r for r in outcome["result"].expectation}
    low = [r for r in rows.values() if r["模型置信度"] == "低"]
    assert low
    assert all(not r["分级"].startswith("L3") for r in low)


def test_exception_levels_sorted(outcome):
    levels = [r["等级"] for r in outcome["result"].exceptions]
    order = {"L3 高风险": 0, "L2 需解释": 1, "L1 提示": 2}
    assert levels == sorted(levels, key=lambda x: order[x])
    assert all(r["人工结论"] == "" for r in outcome["result"].exceptions)


def test_grade_thresholds():
    assert analysis.grade_exception(150, 200, 5000) == "L1 提示"
    assert analysis.grade_exception(300, 200, 5000) == "L2 需解释"
    assert analysis.grade_exception(6000, 200, 5000) == "L3 高风险"
    assert analysis.grade_exception(10, 200, 5000) == ""


# ---------------------------------------------------------------- 边界情况


def test_zero_prior_growth_not_applicable():
    rate, note = analysis.growth_rate(100, 0)
    assert rate is None
    assert "不适用" in note


def test_negative_prior_growth_not_applicable():
    rate, note = analysis.growth_rate(-50, -100)
    assert rate is None
    assert "不适用" in note


def test_zero_denominator_ratio_marked(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "资产负债表"
    ws.append(["编制单位：测试        单位：元"])
    ws.append(["项目", "本期金额", "上期金额"])
    ws.append(["流动资产合计", 1000, 800])
    ws.append(["流动负债合计", 0, 500])
    ws.append(["资产总计", 1000, 800])
    ws.append(["负债和所有者权益总计", 1000, 800])
    ws2 = wb.create_sheet("利润表")
    ws2.append(["项目", "本期金额", "上期金额"])
    ws2.append(["营业收入", 0, 0])
    ws2.append(["净利润", 100, 50])
    path = tmp_path / "boundary.xlsx"
    wb.save(path)

    report = load_workbook(path)
    ratios = {r["指标"]: r for r in analysis.compute_ratios(report)}
    assert ratios["流动比率"]["本期"] is None
    assert "无法计算" in ratios["流动比率"]["备注"] or "分母" in ratios["流动比率"]["备注"]


def test_unit_conversion_from_wan(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "利润表"
    ws.append(["编制单位：测试        单位：万元"])
    ws.append(["项目", "本期金额", "上期金额"])
    ws.append(["营业收入", 1000, 800])
    ws.append(["净利润", 100, 80])
    path = tmp_path / "unit.xlsx"
    wb.save(path)
    report = load_workbook(path)
    assert report.get("利润表", "营业收入") == (10000000.0, 8000000.0)
    assert report.statement("利润表").unit == "万元"


def test_missing_statement_does_not_crash(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "利润表"
    ws.append(["项目", "本期金额", "上期金额"])
    ws.append(["营业收入", 1000, 800])
    path = tmp_path / "partial.xlsx"
    wb.save(path)
    report = load_workbook(path)
    assert report.statement("资产负债表") is None
    result = analysis.AnalysisResult()
    result.ratios = analysis.compute_ratios(report)
    assert result.ratios
    assert any("未找到" in w for w in report.warnings)


# ---------------------------------------------------------------- 输出文件


def test_outputs_written(outcome):
    paths = outcome["paths"]
    for key in ("excel", "word", "csv", "log", "revision"):
        assert paths[key].exists()
        assert paths[key].stat().st_size > 0


def test_excel_contains_expected_sheets(outcome):
    from openpyxl import load_workbook as load_xlsx
    wb = load_xlsx(outcome["paths"]["excel"])
    for name in ["说明与参数", "数据校验", "结构分析", "两年对比", "比率分析",
                 "期望值模型", "一致性检查", "异常汇总", "行业对比（待填）", "图表"]:
        assert any(sheet.endswith(name) for sheet in wb.sheetnames), name
    # 工作表名 = 底稿索引号（A-9-序号）+ 名称
    assert all(sheet.startswith("A-9-") for sheet in wb.sheetnames)


def test_excel_sheet_uses_four_section_format(outcome):
    from openpyxl import load_workbook as load_xlsx
    wb = load_xlsx(outcome["paths"]["excel"])
    ws = next(wb[name] for name in wb.sheetnames if name.endswith("异常汇总"))
    texts = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]
    for marker in ["一、项目基本信息", "二、审计目标和程序说明", "三、审计程序执行结果", "四、审计说明"]:
        assert marker in texts, marker
    assert any("编制人：" in t and "审核人：" in t for t in texts), "应含签字行"
    assert any("修订记录" in t for t in texts), "应含修订记录伴随声明"


def _find_header_row(ws, *names):
    for r in range(1, ws.max_row + 1):
        values = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        if all(name in values for name in names):
            return r
    return None


def test_excel_uses_real_formulas(outcome):
    from openpyxl import load_workbook as load_xlsx
    wb = load_xlsx(outcome["paths"]["excel"])
    ws = next(wb[name] for name in wb.sheetnames if name.endswith("两年对比"))
    header_row = _find_header_row(ws, "变动额", "变动率")
    assert header_row
    header = {ws.cell(row=header_row, column=c).value: c
              for c in range(1, ws.max_column + 1)
              if ws.cell(row=header_row, column=c).value}
    first_change = ws.cell(row=header_row + 1, column=header["变动额"]).value
    assert isinstance(first_change, str) and first_change.startswith("=")


def test_procedure_table_has_dropdown(outcome):
    from openpyxl import load_workbook as load_xlsx
    wb = load_xlsx(outcome["paths"]["excel"])
    ws = next(wb[name] for name in wb.sheetnames if name.endswith("数据校验"))
    validations = ws.data_validations.dataValidation
    assert any("是,否,不适用" in (dv.formula1 or "") for dv in validations)


def test_ratio_number_format_follows_unit(outcome):
    from openpyxl import load_workbook as load_xlsx
    wb = load_xlsx(outcome["paths"]["excel"])
    ws = next(wb[name] for name in wb.sheetnames if name.endswith("比率分析"))
    header_row = _find_header_row(ws, "分组", "指标", "本期")
    assert header_row
    header = {ws.cell(row=header_row, column=c).value: c
              for c in range(1, ws.max_column + 1)
              if ws.cell(row=header_row, column=c).value}
    formats = {}
    r = header_row + 1
    while ws.cell(row=r, column=header["指标"]).value:
        name = ws.cell(row=r, column=header["指标"]).value
        formats[name] = ws.cell(row=r, column=header["本期"]).number_format
        r += 1
    assert formats["毛利率"] == "0.00%"
    assert formats["净资产收益率"] == "0.00%"
    assert formats["流动比率"] == "0.00"
    assert formats["应收账款周转天数"] == "0.00"


def test_word_contains_conclusion_placeholder(outcome):
    from docx import Document
    doc = Document(str(outcome["paths"]["word"]))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "分析结论" in text
    assert "程序不代写结论" in text
    assert "待向被审计单位询问的问题" in text
    assert len(doc.tables) >= 3


def test_questions_carry_amounts(outcome):
    from docx import Document
    doc = Document(str(outcome["paths"]["word"]))
    questions = [p.text for p in doc.paragraphs if p.text.strip().startswith("1. 关于")]
    assert questions
    assert "元" in questions[0]
    l1_items = [r["项目/指标"] for r in outcome["result"].exceptions if r["等级"].startswith("L1")]
    assert all(f"【{item}】" not in q for item in l1_items for q in questions), "L1 事项不进入询问清单"


def test_csv_has_bom_and_headers(outcome):
    raw = outcome["paths"]["csv"].read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert "人工结论" in text.splitlines()[0]
