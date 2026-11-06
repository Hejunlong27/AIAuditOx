"""分析程序：数据校验、结构分析、两年对比、比率、期望值、一致性检查与分级。"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config as cfg
from .loader import ReportSet, StatementData


# ------------------------------------------------------------------ 数据类


@dataclass
class AnalysisResult:
    meta: dict = field(default_factory=dict)
    validation: list[dict] = field(default_factory=list)
    structure: list[dict] = field(default_factory=list)
    trend: list[dict] = field(default_factory=list)
    ratios: list[dict] = field(default_factory=list)
    expectation: list[dict] = field(default_factory=list)
    consistency: list[dict] = field(default_factory=list)
    exceptions: list[dict] = field(default_factory=list)
    unmapped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ 工具


def safe_div(numerator, denominator):
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def average(a, b):
    if a is None or b is None:
        return None
    return (a + b) / 2.0


def growth_rate(current, prior):
    """增长率的适用性判断：上期为零或为负时不适用。"""
    if current is None or prior is None:
        return None, "缺少数据"
    if prior == 0:
        return None, "上期为零，变动率不适用"
    if prior < 0:
        return None, "上期为负，变动率不适用"
    return (current - prior) / abs(prior), None


def causes_for(item: str) -> list[str]:
    found = cfg.CAUSE_LIBRARY.get(item)
    if found:
        return list(found)
    return list(cfg.GENERAL_CAUSES)


def procedures_for(item: str) -> list[str]:
    found = cfg.PROCEDURE_LIBRARY.get(item)
    if found:
        return list(found)
    return list(cfg.GENERAL_PROCEDURES)


def nature_of(statement: str, item: str) -> str:
    return cfg.ITEM_NATURE.get(item, "资产负债" if statement == "资产负债表" else "费用")


def grade_exception(diff_abs, tolerable, materiality) -> str:
    """分级：先看可容忍差异，再看重要性水平，避免小额科目被过度定级。"""
    if diff_abs is None:
        return ""
    if tolerable is None:
        tolerable = 0.0
    if diff_abs <= tolerable * cfg.DEFAULT_CONFIG["L1_floor"]:
        return ""
    if diff_abs <= tolerable:
        return "L1 提示"
    if materiality and diff_abs >= materiality:
        return "L3 高风险"
    else:
        return "L2 需解释"


# 汇总数与现金余额类项目不单独作为关注项：其变动由明细项目与业务实质决定，
# 单独提示只会淹没真正需要解释的科目。这些项目在明细表中仍然完整列示。
NO_FLAG_ITEMS = {
    "流动资产合计", "非流动资产合计", "资产总计", "流动负债合计", "非流动负债合计",
    "负债合计", "所有者权益合计", "负债和所有者权益总计",
    "经营活动现金流入小计", "经营活动现金流出小计", "投资活动现金流入小计",
    "投资活动现金流出小计", "筹资活动现金流入小计", "筹资活动现金流出小计",
    "现金及现金等价物净增加额", "期初现金及现金等价物余额", "期末现金及现金等价物余额",
    "营业利润", "利润总额", "净利润", "综合收益总额", "本年年末余额", "本年年初余额",
}


def tolerable_difference(expected, statement: str, item: str, materiality) -> float:
    nature = nature_of(statement, item)
    rate = cfg.DEFAULT_CONFIG["tolerance_rate"].get(nature, 0.10)
    by_materiality = (materiality or 0.0) * cfg.DEFAULT_CONFIG["tolerable_ratio_of_materiality"]
    by_expected = abs(expected) * rate if expected is not None else 0.0
    return max(by_materiality, by_expected)


# ------------------------------------------------------------------ 重要性水平


def suggest_materiality(report: ReportSet) -> dict:
    profit, _ = report.find("利润总额")
    assets, _ = report.get("资产负债表", "资产总计")
    revenue, _ = report.get("利润表", "营业收入")

    bases = [
        ("税前利润", profit, cfg.DEFAULT_CONFIG["materiality_ratio_of_profit"], "营利性企业常用基准"),
        ("营业收入", revenue, cfg.DEFAULT_CONFIG["materiality_ratio_of_revenue"], "收入规模大或利润波动大时使用"),
        ("资产总计", assets, cfg.DEFAULT_CONFIG["materiality_ratio_of_asset"], "资产规模大或重资产行业使用"),
    ]
    rows = []
    candidates = []
    for name, value, ratio, usage in bases:
        if value is None or value <= 0:
            rows.append({"基准": name, "基准金额": value, "比例": ratio, "测算值": None,
                         "是否可用": "否", "适用情形": usage})
            continue
        amount = value * ratio
        rows.append({"基准": name, "基准金额": value, "比例": ratio, "测算值": amount,
                     "是否可用": "是", "适用情形": usage})
        candidates.append((name, amount))

    # 首选税前利润基准；不可用时依次退到营业收入、资产总计
    suggestion = None
    basis_used: list[str] = []
    for preferred in ("税前利润", "营业收入", "资产总计"):
        match = [c for c in candidates if c[0] == preferred]
        if match:
            suggestion = match[0][1]
            basis_used = [preferred]
            break
    return {
        "bases": rows,
        "suggestion": suggestion,
        "basis_used": basis_used,
        "note": (
            f"建议值以{basis_used[0]}为基准，其余基准供参考。营利性企业通常以税前利润 5% 为基准，"
            "存在亏损、利润大幅波动或特殊行业时应改用其他基准。最终由项目组确认。"
            if suggestion else "无法测算，请手动提供重要性水平"
        ),
    }


# ------------------------------------------------------------------ 数据校验


def _tie_row(name, item_desc, left, right, tolerance, note=""):
    if left is None or right is None:
        return {
            "检查项": name, "项目": item_desc, "金额一": left, "金额二": right,
            "差异": None, "容忍额": tolerance, "结论": "无法执行", "说明": note or "相关项目未获取到数据",
        }
    diff = left - right
    abs_diff = abs(diff)
    if abs_diff <= tolerance:
        status = "通过"
    elif abs_diff <= tolerance * 5:
        status = "注意"
    else:
        status = "不符"
    return {
        "检查项": name, "项目": item_desc, "金额一": left, "金额二": right,
        "差异": diff, "容忍额": tolerance, "结论": status, "说明": note,
    }


def validate(report: ReportSet, materiality) -> list[dict]:
    rows: list[dict] = []
    tolerance = max((materiality or 0.0) * cfg.DEFAULT_CONFIG["tie_tolerance_ratio"], 1.0)
    period_tag = "本期"

    bs = report.statement("资产负债表")
    inc = report.statement("利润表")
    cf = report.statement("现金流量表")
    eq = report.statement("所有者权益变动表")

    if bs:
        cur, prior = bs.get("资产总计")
        c2, p2 = bs.get("负债和所有者权益总计")
        rows.append(_tie_row("资产负债表平衡", f"资产总计 = 负债和所有者权益总计（{period_tag}）", cur, c2, tolerance))
        rows.append(_tie_row("资产负债表平衡", "资产总计 = 负债和所有者权益总计（上期）", prior, p2, tolerance))

        for tag, idx in (("本期", 0), ("上期", 1)):
            total = _pick(bs.get("资产总计"), idx)
            ca = _pick(bs.get("流动资产合计"), idx)
            nca = _pick(bs.get("非流动资产合计"), idx)
            rows.append(_tie_row("资产结构", f"资产总计 = 流动资产合计 + 非流动资产合计（{tag}）",
                                 total, _add(ca, nca), tolerance))
            liab = _pick(bs.get("负债合计"), idx)
            cl = _pick(bs.get("流动负债合计"), idx)
            ncl = _pick(bs.get("非流动负债合计"), idx)
            rows.append(_tie_row("负债结构", f"负债合计 = 流动负债合计 + 非流动负债合计（{tag}）",
                                 liab, _add(cl, ncl), tolerance))
            equity = _pick(bs.get("所有者权益合计"), idx)
            parts = _add(
                _pick(bs.get("实收资本"), idx), _pick(bs.get("资本公积"), idx),
                _pick(bs.get("盈余公积"), idx), _pick(bs.get("未分配利润"), idx),
                _pick(bs.get("其他综合收益"), idx),
            )
            stock = _pick(bs.get("库存股"), idx)
            if stock is not None:
                parts = parts - stock if parts is not None else None
            rows.append(_tie_row("权益结构", f"所有者权益合计 = 各权益项目合计（{tag}）",
                                 equity, parts, tolerance, "未包含少数股东权益等明细项目，仅供参考"))
            rows.append(_tie_row("资产负债权益", f"资产总计 = 负债合计 + 所有者权益合计（{tag}）",
                                 total, _add(liab, equity), tolerance))

    if inc:
        for tag, idx in (("本期", 0), ("上期", 1)):
            profit = _pick(inc.get("利润总额"), idx)
            tax = _pick(inc.get("所得税费用"), idx)
            net = _pick(inc.get("净利润"), idx)
            rows.append(_tie_row("利润表勾稽", f"净利润 = 利润总额 − 所得税费用（{tag}）",
                                 net, _sub(profit, tax), tolerance))
            revenue = _pick(inc.get("营业收入"), idx)
            cost = _pick(inc.get("营业成本"), idx)
            total_cost = _add(
                cost, _pick(inc.get("税金及附加"), idx), _pick(inc.get("销售费用"), idx),
                _pick(inc.get("管理费用"), idx), _pick(inc.get("研发费用"), idx),
                _pick(inc.get("财务费用"), idx),
            )
            calc = _sub(revenue, total_cost)
            inv = _pick(inc.get("投资收益"), idx)
            other = _pick(inc.get("其他收益"), idx)
            calc = _add(calc, inv, other)
            rows.append(_tie_row("利润表勾稽", f"营业利润 ≈ 营业收入 − 营业成本及费用 + 投资收益等（{tag}）",
                                 _pick(inc.get("营业利润"), idx), calc, tolerance,
                                 "未包含减值损失、资产处置收益等全部项目，参考性核对"))

    if cf:
        cur_close, prior_close = cf.get("期末现金及现金等价物余额")
        cur_open, prior_open = cf.get("期初现金及现金等价物余额")
        cur_net, prior_net = cf.get("现金及现金等价物净增加额")
        rows.append(_tie_row("现金流量表勾稽", "期末余额 = 期初余额 + 净增加额（本期）",
                             cur_close, _add(cur_open, cur_net), tolerance))
        rows.append(_tie_row("现金流量表勾稽", "期末余额 = 期初余额 + 净增加额（上期）",
                             prior_close, _add(prior_open, prior_net), tolerance))
        for tag, idx in (("本期", 0), ("上期", 1)):
            op = _pick(cf.get("经营活动产生的现金流量净额"), idx)
            iv = _pick(cf.get("投资活动产生的现金流量净额"), idx)
            fi = _pick(cf.get("筹资活动产生的现金流量净额"), idx)
            rows.append(_tie_row("现金流量表勾稽", f"净增加额 = 经营 + 投资 + 筹资净额（{tag}）",
                                 _pick(cf.get("现金及现金等价物净增加额"), idx), _add(op, iv, fi), tolerance))

    if eq:
        for tag, idx in (("本期", 0), ("上期", 1)):
            opening = _pick(eq.get("本年年初余额"), idx)
            closing = _pick(eq.get("本年年末余额"), idx)
            total_income = _pick(eq.get("综合收益总额"), idx)
            invested = _pick(eq.get("所有者投入和减少资本"), idx)
            distributed = _pick(eq.get("利润分配"), idx)
            calc = _add(opening, total_income, invested, distributed)
            rows.append(_tie_row("权益变动勾稽", f"年末余额 = 年初余额 + 综合收益总额 + 投入 − 分配（{tag}）",
                                 closing, calc, tolerance, "按表内填列方向计入，减少权益的项目以负数填列"))

    if eq and inc:
        eq_net, eq_net_prior = eq.get("净利润")
        is_net, is_net_prior = inc.get("净利润")
        rows.append(_tie_row("表间勾稽", "权益变动表净利润 = 利润表净利润（本期）", eq_net, is_net, tolerance))
        rows.append(_tie_row("表间勾稽", "权益变动表净利润 = 利润表净利润（上期）", eq_net_prior, is_net_prior, tolerance))

    # 单位与映射质量
    for name, st in report.statements.items():
        rows.append({
            "检查项": "数据质量", "项目": f"{name} 金额单位",
            "金额一": None, "金额二": None, "差异": None, "容忍额": None,
            "结论": "通过" if st.unit == "元" else "注意",
            "说明": f"识别单位：{st.unit}，已统一换算为元（换算系数 {st.unit_factor:g}）",
        })
        total = len(st.items)
        unmapped = len(st.unmapped)
        rows.append({
            "检查项": "数据质量", "项目": f"{name} 科目映射",
            "金额一": total, "金额二": unmapped, "差异": None, "容忍额": None,
            "结论": "通过" if unmapped == 0 else "注意",
            "说明": f"共解析 {total} 行，未映射 {unmapped} 行，详见未映射清单",
        })

    # 零分母检查
    zero_checks = [
        ("资产负债表", "流动负债合计"), ("资产负债表", "资产总计"),
        ("利润表", "营业收入"), ("利润表", "利润总额"),
    ]
    for statement, item in zero_checks:
        st = report.statement(statement)
        if not st:
            continue
        cur, prior = st.get(item)
        if cur in (0, None) or prior in (0, None):
            rows.append({
                "检查项": "数据质量", "项目": f"{statement} - {item} 零值检查",
                "金额一": cur, "金额二": prior, "差异": None, "容忍额": None,
                "结论": "注意",
                "说明": "存在零值或缺失，相关比率无法计算或需特别关注",
            })
    return rows


def _pick(pair, idx):
    if pair is None:
        return None
    return pair[idx]


def _add(*values):
    acc = 0.0
    seen = False
    for v in values:
        if v is None:
            continue
        acc += v
        seen = True
    return acc if seen else None


def _sub(a, b):
    if a is None or b is None:
        return None
    return a - b


# ------------------------------------------------------------------ 结构分析


def structure(report: ReportSet, materiality) -> list[dict]:
    rows: list[dict] = []
    bs = report.statement("资产负债表")
    inc = report.statement("利润表")

    def build(statement: StatementData, base_item: str, label: str):
        base_cur, base_prior = statement.get(base_item)
        for item in statement.mapping.values():
            if item.standard == base_item:
                continue
            if item.current is None and item.prior is None:
                continue
            pct_cur = safe_div(item.current, base_cur)
            pct_prior = safe_div(item.prior, base_prior)
            change_pp = None
            if pct_cur is not None and pct_prior is not None:
                change_pp = (pct_cur - pct_prior) * 100
            amount_change = None
            if item.current is not None and item.prior is not None:
                amount_change = item.current - item.prior
            flag = ""
            if (
                item.standard not in NO_FLAG_ITEMS
                and change_pp is not None
                and abs(change_pp) >= cfg.DEFAULT_CONFIG["structure_pp_threshold"]
                and amount_change is not None
                and abs(amount_change) >= (materiality or 0) * cfg.DEFAULT_CONFIG["structure_amount_threshold"]
            ):
                flag = "关注"
            rows.append({
                "报表": label,
                "项目": item.standard,
                "本期金额": item.current,
                "上期金额": item.prior,
                "本期占比": pct_cur,
                "上期占比": pct_prior,
                "占比变动(百分点)": change_pp,
                "金额变动": amount_change,
                "是否关注": flag,
                "基准": base_item,
                "基准本期金额": base_cur,
                "基准上期金额": base_prior,
            })

    if bs:
        build(bs, "资产总计", "资产负债表")
    if inc:
        build(inc, "营业收入", "利润表")
    return rows


# ------------------------------------------------------------------ 两年对比


def trend(report: ReportSet, materiality) -> list[dict]:
    rows: list[dict] = []
    for statement_name, statement in report.statements.items():
        threshold = cfg.DEFAULT_CONFIG["trend_rate_threshold"].get(statement_name, 0.30)
        amount_threshold = (materiality or 0) * cfg.DEFAULT_CONFIG["trend_amount_threshold"]
        for item in statement.mapping.values():
            if item.current is None and item.prior is None:
                continue
            change = None
            if item.current is not None and item.prior is not None:
                change = item.current - item.prior
            rate, note = growth_rate(item.current, item.prior)
            flag = ""
            if (
                item.standard not in NO_FLAG_ITEMS
                and rate is not None
                and abs(rate) >= threshold
                and change is not None
                and abs(change) >= amount_threshold
            ):
                flag = "关注"
            rows.append({
                "报表": statement_name,
                "项目": item.standard,
                "上期金额": item.prior,
                "本期金额": item.current,
                "变动额": change,
                "变动率": rate,
                "是否关注": flag,
                "备注": note or "",
            })
    return rows


# ------------------------------------------------------------------ 比率分析


TURNOVER_RATIOS = {"应收账款周转率", "应收账款周转天数", "存货周转率", "存货周转天数", "应付账款周转天数", "总资产周转率"}


def _turnover_note(name: str) -> str:
    return "上期按期末余额计算（缺上上期数据），与本期平均余额口径不同，仅供方向参考"


def compute_ratios(report: ReportSet) -> list[dict]:
    bs = report.statement("资产负债表")
    inc = report.statement("利润表")
    cf = report.statement("现金流量表")

    def bs_get(item, idx=None):
        if not bs:
            return None
        pair = bs.get(item)
        return pair if idx is None else pair[idx]

    def inc_get(item, idx=None):
        if not inc:
            return None
        pair = inc.get(item)
        return pair if idx is None else pair[idx]

    def cf_get(item, idx=None):
        if not cf:
            return None
        pair = cf.get(item)
        return pair if idx is None else pair[idx]

    results: dict[str, dict] = {}

    def put(name, group, current, prior, unit, direction, note=""):
        change = None
        if current is not None and prior is not None:
            change = current - prior
        judgement = ""
        if change is not None and direction in ("high", "low"):
            if abs(change) < 1e-9:
                judgement = "持平"
            elif (change > 0 and direction == "high") or (change < 0 and direction == "low"):
                judgement = "改善"
            else:
                judgement = "恶化"
        results[name] = {
            "分组": group, "指标": name, "本期": current, "上期": prior,
            "变动": change, "单位": unit, "方向": judgement, "备注": note,
        }

    ca_c, ca_p = _pair(bs, "流动资产合计")
    cl_c, cl_p = _pair(bs, "流动负债合计")
    inv_c, inv_p = _pair(bs, "存货")
    cash_c, cash_p = _pair(bs, "货币资金")
    ta_c, ta_p = _pair(bs, "资产总计")
    tl_c, tl_p = _pair(bs, "负债合计")
    equity_c, equity_p = _pair(bs, "所有者权益合计")
    ar_c, ar_p = _pair(bs, "应收账款")
    ap_c, ap_p = _pair(bs, "应付账款")
    rev_c, rev_p = _pair(inc, "营业收入")
    cost_c, cost_p = _pair(inc, "营业成本")
    op_c, op_p = _pair(inc, "营业利润")
    net_c, net_p = _pair(inc, "净利润")
    ebt_c, ebt_p = _pair(inc, "利润总额")
    tax_c, tax_p = _pair(inc, "所得税费用")
    interest_c, interest_p = _pair(inc, "利息费用")
    expense_c = _add(_pick(inc.get("销售费用"), 0) if inc else None,
                     _pick(inc.get("管理费用"), 0) if inc else None,
                     _pick(inc.get("研发费用"), 0) if inc else None,
                     _pick(inc.get("财务费用"), 0) if inc else None)
    expense_p = _add(_pick(inc.get("销售费用"), 1) if inc else None,
                     _pick(inc.get("管理费用"), 1) if inc else None,
                     _pick(inc.get("研发费用"), 1) if inc else None,
                     _pick(inc.get("财务费用"), 1) if inc else None)
    ocf_c, ocf_p = _pair(cf, "经营活动产生的现金流量净额")
    sale_cash_c, sale_cash_p = _pair(cf, "销售商品、提供劳务收到的现金")

    put("流动比率", "偿债能力", safe_div(ca_c, cl_c), safe_div(ca_p, cl_p), "倍", "neutral")
    put("速动比率", "偿债能力",
        safe_div(_sub(ca_c, inv_c), cl_c), safe_div(_sub(ca_p, inv_p), cl_p), "倍", "neutral")
    put("现金比率", "偿债能力", safe_div(cash_c, cl_c), safe_div(cash_p, cl_p), "倍", "neutral")
    put("资产负债率", "偿债能力",
        safe_div(tl_c, ta_c), safe_div(tl_p, ta_p), "%", "low")
    put("利息保障倍数", "偿债能力",
        safe_div(_add(ebt_c, interest_c), interest_c),
        safe_div(_add(ebt_p, interest_p), interest_p), "倍", "high",
        "需利润表列示利息费用" if interest_c is None else "")

    ar_avg = average(ar_c, ar_p)
    inv_avg = average(inv_c, inv_p)
    ta_avg = average(ta_c, ta_p)
    ap_avg = average(ap_c, ap_p)
    put("应收账款周转率", "营运能力",
        safe_div(rev_c, ar_avg), safe_div(rev_p, ar_p), "次", "high",
        _turnover_note("应收账款周转率"))
    cur_turn = safe_div(rev_c, ar_avg)
    prior_turn = safe_div(rev_p, ar_p)
    put("应收账款周转天数", "营运能力",
        safe_div(365.0, cur_turn), safe_div(365.0, prior_turn), "天", "low",
        _turnover_note("应收账款周转天数"))
    put("存货周转率", "营运能力",
        safe_div(cost_c, inv_avg), safe_div(cost_p, inv_p), "次", "high",
        _turnover_note("存货周转率"))
    cur_inv_turn = safe_div(cost_c, inv_avg)
    prior_inv_turn = safe_div(cost_p, inv_p)
    put("存货周转天数", "营运能力",
        safe_div(365.0, cur_inv_turn), safe_div(365.0, prior_inv_turn), "天", "low",
        _turnover_note("存货周转天数"))
    put("应付账款周转天数", "营运能力",
        safe_div(365.0, safe_div(cost_c, ap_avg)),
        safe_div(365.0, safe_div(cost_p, ap_p)), "天", "neutral",
        _turnover_note("应付账款周转天数"))
    put("总资产周转率", "营运能力",
        safe_div(rev_c, ta_avg), safe_div(rev_p, ta_p), "次", "high",
        _turnover_note("总资产周转率"))

    put("毛利率", "盈利能力",
        safe_div(_sub(rev_c, cost_c), rev_c), safe_div(_sub(rev_p, cost_p), rev_p), "%", "high")
    put("营业利润率", "盈利能力", safe_div(op_c, rev_c), safe_div(op_p, rev_p), "%", "high")
    put("净利率", "盈利能力", safe_div(net_c, rev_c), safe_div(net_p, rev_p), "%", "high")
    equity_avg = average(equity_c, equity_p)
    put("净资产收益率", "盈利能力",
        safe_div(net_c, equity_avg), safe_div(net_p, equity_p), "%", "high",
        "上期按期末权益计算" if equity_p else "")
    put("总资产报酬率", "盈利能力",
        safe_div(net_c, ta_avg), safe_div(net_p, ta_p), "%", "high",
        "上期按期末资产计算" if ta_p else "")
    put("期间费用率", "盈利能力", safe_div(expense_c, rev_c), safe_div(expense_p, rev_p), "%", "low")
    put("实际所得税税率", "盈利能力", safe_div(tax_c, ebt_c), safe_div(tax_p, ebt_p), "%", "neutral")

    put("净利润现金含量", "现金流质量", safe_div(ocf_c, net_c), safe_div(ocf_p, net_p), "倍", "high")
    put("收现比", "现金流质量",
        safe_div(sale_cash_c, rev_c), safe_div(sale_cash_p, rev_p), "倍", "high")
    put("资产现金回收率", "现金流质量",
        safe_div(ocf_c, ta_avg), safe_div(ocf_p, ta_p), "%", "high",
        "上期按期末资产计算" if ta_p else "")

    revenue_growth, _ = growth_rate(rev_c, rev_p)
    net_growth, _ = growth_rate(net_c, net_p)
    put("收入增长率", "成长性", revenue_growth, None, "%", "neutral")
    put("净利润增长率", "成长性", net_growth, None, "%", "neutral")

    net_margin = safe_div(net_c, rev_c)
    ta_turn = safe_div(rev_c, ta_avg)
    equity_mult = safe_div(ta_avg, equity_avg)
    put("净利率(杜邦)", "杜邦分解", net_margin, safe_div(net_p, rev_p), "%", "high")
    put("总资产周转率(杜邦)", "杜邦分解", ta_turn, safe_div(rev_p, ta_p), "次", "high",
        _turnover_note("总资产周转率(杜邦)"))
    put("权益乘数", "杜邦分解", equity_mult, safe_div(ta_p, equity_p), "倍", "neutral")

    ordered = []
    for spec in cfg.RATIO_DEFS:
        row = results.get(spec["name"])
        if row is None:
            continue
        missing = row["本期"] is None or (row["上期"] is None and row["分组"] != "成长性")
        if missing:
            row["备注"] = (row["备注"] + "；" if row["备注"] else "") + "无法计算 - 缺少相关项目或分母为零"
        ordered.append(row)
    return ordered


def _pair(statement: StatementData | None, item: str):
    if statement is None:
        return (None, None)
    return statement.get(item)


# ------------------------------------------------------------------ 期望值模型


@dataclass
class ExpectationModel:
    item: str
    statement: str
    kind: str
    driver: str
    confidence: str


EXPECTATION_MODELS = [
    ExpectationModel("营业成本", "利润表", "配比", "本期营业收入 × (1 − 上期毛利率)", "高"),
    ExpectationModel("税金及附加", "利润表", "配比", "本期营业收入 × 上期税负率", "高"),
    ExpectationModel("销售费用", "利润表", "配比", "本期营业收入 × 上期费用率", "中"),
    ExpectationModel("管理费用", "利润表", "配比", "本期营业收入 × 上期费用率", "中"),
    ExpectationModel("研发费用", "利润表", "配比", "本期营业收入 × 上期费用率", "中"),
    ExpectationModel("应收账款", "资产负债表", "驱动", "上期余额 × (1 + 收入增长率)", "中"),
    ExpectationModel("存货", "资产负债表", "驱动", "上期余额 × (1 + 营业成本增长率)", "中"),
    ExpectationModel("应付账款", "资产负债表", "驱动", "上期余额 × (1 + 营业成本增长率)", "中"),
    ExpectationModel("货币资金", "资产负债表", "驱动", "上期余额 × (1 + 资产总计增长率)", "低"),
    ExpectationModel("其他应收款", "资产负债表", "驱动", "上期余额 × (1 + 资产总计增长率)", "低"),
]


def expectation(report: ReportSet, materiality) -> list[dict]:
    bs = report.statement("资产负债表")
    inc = report.statement("利润表")

    rev_c, rev_p = _pair(inc, "营业收入")
    cost_c, cost_p = _pair(inc, "营业成本")
    ta_c, ta_p = _pair(bs, "资产总计")

    revenue_growth, _ = growth_rate(rev_c, rev_p)
    cost_growth, _ = growth_rate(cost_c, cost_p)
    asset_growth, _ = growth_rate(ta_c, ta_p)

    prior_gross_margin = None
    if rev_p not in (None, 0) and cost_p is not None:
        prior_gross_margin = (rev_p - cost_p) / rev_p

    rows: list[dict] = []
    for model in EXPECTATION_MODELS:
        st = report.statement(model.statement)
        if st is None:
            continue
        actual_c, actual_p = st.get(model.item)
        if actual_p is None:
            continue

        expected = None
        driver_note = ""
        if model.kind == "配比":
            if rev_c is None or rev_c == 0:
                continue
            prior_value_p = actual_p
            rate = safe_div(prior_value_p, rev_p)
            if model.item == "营业成本":
                if prior_gross_margin is None:
                    continue
                expected = rev_c * (1 - prior_gross_margin)
                driver_note = f"上期毛利率 {prior_gross_margin:.2%}"
            elif rate is not None:
                expected = rev_c * rate
                driver_note = f"上期费率 {rate:.2%}"
        else:
            growth = {"应收账款": revenue_growth, "存货": cost_growth, "应付账款": cost_growth}.get(
                model.item, asset_growth
            )
            if growth is None:
                continue
            expected = actual_p * (1 + growth)
            driver_note = f"驱动增长率 {growth:.2%}"

        if expected is None:
            continue

        diff = (actual_c - expected) if actual_c is not None else None
        diff_rate = safe_div(diff, abs(expected)) if diff is not None and expected != 0 else None
        tolerable = tolerable_difference(expected, model.statement, model.item, materiality)
        grade = grade_exception(abs(diff) if diff is not None else None, tolerable, materiality)
        grade_note = ""
        if model.confidence == "低" and grade == "L3 高风险":
            grade = "L2 需解释"
            grade_note = "驱动关系置信度低，等级封顶为 L2"

        direction = cfg.PROFIT_ASSET_DIRECTION.get(model.item, 0)
        impact = diff * direction if diff is not None else None
        if impact is None:
            risk = ""
        elif impact > 0:
            risk = "倾向于增加资产或利润，关注高估风险"
        elif impact < 0:
            risk = "倾向于减少资产或利润，关注低估风险"
        else:
            risk = "无方向性影响"

        rows.append({
            "报表": model.statement,
            "项目": model.item,
            "模型": model.kind,
            "驱动关系": model.driver,
            "驱动因子": driver_note,
            "上期金额": actual_p,
            "本期实际": actual_c,
            "期望值": expected,
            "差异": diff,
            "差异率": diff_rate,
            "可容忍差异": tolerable,
            "分级": grade,
            "方向判断": risk,
            "模型置信度": model.confidence,
            "备注": grade_note,
            "可能成因": "；".join(causes_for(model.item)[:4]),
            "建议程序": "；".join(procedures_for(model.item)[:4]),
            "人工结论": "",
        })
    return rows


# ------------------------------------------------------------------ 一致性检查


def consistency(report: ReportSet, materiality, ratio_map: dict) -> list[dict]:
    thresholds = cfg.DEFAULT_CONFIG["consistency"]
    bs = report.statement("资产负债表")
    inc = report.statement("利润表")
    cf = report.statement("现金流量表")
    rows: list[dict] = []

    rev_c, rev_p = _pair(inc, "营业收入")
    cost_c, cost_p = _pair(inc, "营业成本")
    ar_c, ar_p = _pair(bs, "应收账款")
    inv_c, inv_p = _pair(bs, "存货")
    other_c, other_p = _pair(bs, "其他应收款")
    ta_c, ta_p = _pair(bs, "资产总计")
    tl_c, tl_p = _pair(bs, "负债合计")
    net_c, net_p = _pair(inc, "净利润")
    ocf_c, ocf_p = _pair(cf, "经营活动产生的现金流量净额")

    rev_growth, _ = growth_rate(rev_c, rev_p)
    ar_growth, _ = growth_rate(ar_c, ar_p)
    inv_growth, _ = growth_rate(inv_c, inv_p)
    net_growth, _ = growth_rate(net_c, net_p)
    ocf_growth, _ = growth_rate(ocf_c, ocf_p)

    def add(name, basis, threshold, actual, triggered, note, cause_key, extra_procedures=None):
        procedures = list(procedures_for(cause_key))[:4]
        if extra_procedures:
            procedures.extend(extra_procedures)
        rows.append({
            "检查项": name,
            "判断依据": basis,
            "触发阈值": threshold,
            "实际值": actual,
            "是否触发": "触发" if triggered else "未触发",
            "说明": note,
            "可能成因": "；".join(causes_for(cause_key)[:4]),
            "建议程序": "；".join(procedures),
            "人工结论": "",
        })

    # 1 收入与应收账款背离
    if rev_growth is not None and ar_growth is not None:
        gap_pp = (ar_growth - rev_growth) * 100
        add("收入与应收账款背离", "应收账款增长率 − 收入增长率",
            f">{thresholds['ar_revenue_gap_pp']:.0f} 个百分点", gap_pp,
            gap_pp > thresholds["ar_revenue_gap_pp"],
            f"收入增长率 {rev_growth:.2%}，应收账款增长率 {ar_growth:.2%}",
            "应收账款")
    # 2 利润与经营现金流背离
    if net_growth is not None and ocf_growth is not None:
        gap_pp = (net_growth - ocf_growth) * 100
        add("利润与经营现金流背离", "净利润增长率 − 经营现金流净额增长率",
            f">{thresholds['profit_cash_gap_pp']:.0f} 个百分点", gap_pp,
            gap_pp > thresholds["profit_cash_gap_pp"],
            f"净利润增长率 {net_growth:.2%}，经营现金流增长率 {ocf_growth:.2%}",
            "经营活动产生的现金流量净额")
    # 3 毛利率异常变动
    gm_c = safe_div(_sub(rev_c, cost_c), rev_c)
    gm_p = safe_div(_sub(rev_p, cost_p), rev_p)
    if gm_c is not None and gm_p is not None:
        change_pp = (gm_c - gm_p) * 100
        add("毛利率异常变动", "毛利率变动（百分点）",
            f">{thresholds['gross_margin_change_pp']:.0f} 个百分点", change_pp,
            abs(change_pp) > thresholds["gross_margin_change_pp"],
            f"本期毛利率 {gm_c:.2%}，上期毛利率 {gm_p:.2%}",
            "毛利率")
    # 4 存货与收入背离
    if inv_growth is not None and rev_growth is not None:
        gap_pp = (inv_growth - rev_growth) * 100
        add("存货与收入背离", "存货增长率 − 收入增长率",
            f">{thresholds['inventory_revenue_gap_pp']:.0f} 个百分点", gap_pp,
            gap_pp > thresholds["inventory_revenue_gap_pp"],
            f"存货增长率 {inv_growth:.2%}，收入增长率 {rev_growth:.2%}",
            "存货")
    # 5 其他应收款异常增长
    if other_growth := growth_rate(other_c, other_p)[0]:
        amount = (other_c - other_p) if other_c is not None and other_p is not None else None
        triggered = (
            other_growth > thresholds["other_receivable_growth"]
            and amount is not None
            and (materiality is None or abs(amount) >= materiality)
        )
        add("其他应收款异常增长", "增幅与金额",
            f">{thresholds['other_receivable_growth']:.0%} 且金额达到重要性水平",
            other_growth, triggered,
            f"其他应收款增幅 {other_growth:.2%}，增加额 {amount:,.2f} 元" if amount is not None
            else f"其他应收款增幅 {other_growth:.2%}",
            "其他应收款")
    # 6 偿债能力恶化
    dr_c = safe_div(tl_c, ta_c)
    dr_p = safe_div(tl_p, ta_p)
    if dr_c is not None and dr_p is not None:
        rise_pp = (dr_c - dr_p) * 100
        add("偿债能力恶化", "资产负债率上升（百分点）",
            f">{thresholds['debt_ratio_rise_pp']:.0f} 个百分点", rise_pp,
            rise_pp > thresholds["debt_ratio_rise_pp"],
            f"本期资产负债率 {dr_c:.2%}，上期 {dr_p:.2%}",
            "短期借款")
    # 7 盈利质量
    cash_ratio = ratio_map.get("净利润现金含量", {}).get("本期")
    if cash_ratio is not None and net_c is not None:
        add("盈利质量不足", "净利润现金含量（经营活动现金流量净额 ÷ 净利润）",
            f"<{thresholds['cash_to_profit_min']:.1f} 倍",
            cash_ratio, net_c > 0 and cash_ratio < thresholds["cash_to_profit_min"],
            f"净利润 {net_c:,.2f} 元，经营现金流 {ocf_c:,.2f} 元" if ocf_c is not None else "",
            "经营活动产生的现金流量净额")
    # 8 回款质量
    collection = ratio_map.get("收现比", {}).get("本期")
    if collection is not None:
        add("回款质量不足", "收现比（销售商品提供劳务收到的现金 ÷ 营业收入）",
            f"<{thresholds['cash_collection_min']:.2f} 倍",
            collection, collection < thresholds["cash_collection_min"],
            f"本期收现比 {collection:.2f}", "应收账款")
    # 9 回款周期恶化
    ar_days_c = ratio_map.get("应收账款周转天数", {}).get("本期")
    ar_days_p = ratio_map.get("应收账款周转天数", {}).get("上期")
    if ar_days_c is not None and ar_days_p not in (None, 0):
        change = (ar_days_c - ar_days_p) / ar_days_p
        add("回款周期恶化", "应收账款周转天数增幅",
            f">{thresholds['ar_days_growth']:.0%}", change,
            change > thresholds["ar_days_growth"],
            f"本期周转天数 {ar_days_c:.1f} 天，上期 {ar_days_p:.1f} 天（上期口径见比率表备注）",
            "应收账款")
    return rows


# ------------------------------------------------------------------ 异常汇总


def build_exceptions(result: AnalysisResult) -> list[dict]:
    """生成异常汇总：合并结构分析与两年对比，再按项目去重，保留最高等级。"""
    rows: list[dict] = []

    # 1) 结构分析与两年对比指向同一现象，按（报表，项目）合并为一条
    focus: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []

    for row in result.structure:
        if row.get("是否关注") != "关注":
            continue
        key = (row["报表"], row["项目"])
        if key not in focus:
            focus[key] = {
                "报表": row["报表"], "项目/指标": row["项目"],
                "本期": row["本期金额"], "上期": row["上期金额"], "差异": row["金额变动"],
                "来源": ["结构分析"], "判定依据": [],
            }
            order.append(key)
        focus[key]["判定依据"].append(
            f"占总计比重由 {row['上期占比']:.2%} 变为 {row['本期占比']:.2%}，"
            f"变动 {row['占比变动(百分点)']:.2f} 个百分点（基准：{row['基准']}）"
        )

    for row in result.trend:
        if row.get("是否关注") != "关注":
            continue
        key = (row["报表"], row["项目"])
        if key not in focus:
            focus[key] = {
                "报表": row["报表"], "项目/指标": row["项目"],
                "本期": row["本期金额"], "上期": row["上期金额"], "差异": row["变动额"],
                "来源": [], "判定依据": [],
            }
            order.append(key)
        item = focus[key]
        item["来源"].append("两年对比")
        item["本期"] = item["本期"] if item["本期"] is not None else row["本期金额"]
        item["上期"] = item["上期"] if item["上期"] is not None else row["上期金额"]
        item["差异"] = item["差异"] if item["差异"] is not None else row["变动额"]
        if row["变动率"] is not None and row["变动率"] != 0:
            item["判定依据"].append(f"较上期变动 {row['变动率']:.2%}")
        else:
            item["判定依据"].append("变动率不适用（上期为零或为负），按绝对额关注")

    for key in order:
        item = focus[key]
        std = item["项目/指标"]
        rows.append({
            "等级": "L1 提示",
            "来源": "+".join(dict.fromkeys(item["来源"])),
            "报表": item["报表"], "项目/指标": std,
            "本期": item["本期"], "上期": item["上期"], "差异": item["差异"],
            "判定依据": "；".join(item["判定依据"]),
            "可能成因": "；".join(causes_for(std)[:4]),
            "建议程序": "；".join(procedures_for(std)[:4]),
            "人工结论": "",
        })

    for row in result.expectation:
        if not row.get("分级"):
            continue
        std = row["项目"]
        if row["差异"] is not None and row["差异率"] is not None:
            basis = (f"期望值 {row['期望值']:,.2f} 元，差异 {row['差异']:,.2f} 元"
                     f"（{row['差异率']:.2%}），可容忍差异 {row['可容忍差异']:,.2f} 元；{row['方向判断']}")
        else:
            basis = f"期望值 {row['期望值']:,.2f} 元，差异 {row['差异']:,.2f} 元"
        if row.get("备注"):
            basis = f"{basis}；{row['备注']}"
        rows.append({
            "等级": row["分级"], "来源": "期望值模型",
            "报表": row["报表"], "项目/指标": std,
            "本期": row["本期实际"], "上期": row["上期金额"], "差异": row["差异"],
            "判定依据": basis,
            "可能成因": row["可能成因"], "建议程序": row["建议程序"], "人工结论": "",
        })

    for row in result.consistency:
        if row.get("是否触发") != "触发":
            continue
        actual = row["实际值"]
        if isinstance(actual, (int, float)):
            actual_text = f"{actual:.2%}" if abs(actual) < 1 else f"{actual:,.2f}"
        else:
            actual_text = str(actual)
        rows.append({
            "等级": "L2 需解释", "来源": "一致性检查",
            "报表": "-", "项目/指标": row["检查项"],
            "本期": None, "上期": None, "差异": None,
            "判定依据": f"{row['判断依据']}，实际 {actual_text}，阈值 {row['触发阈值']}；{row['说明']}",
            "可能成因": row["可能成因"], "建议程序": row["建议程序"], "人工结论": "",
        })

    rows = _dedupe_by_item(rows)
    grade_order = {"L3 高风险": 0, "L2 需解释": 1, "L1 提示": 2}
    rows.sort(key=lambda r: grade_order.get(r["等级"], 9))
    ordered = []
    for i, row in enumerate(rows, start=1):
        new_row = {"编号": f"E{i:03d}"}
        new_row.update({k: v for k, v in row.items() if k != "编号"})
        ordered.append(new_row)
    return ordered


GRADE_RANK = {"L3 高风险": 3, "L2 需解释": 2, "L1 提示": 1}


def _dedupe_by_item(rows: list[dict]) -> list[dict]:
    """同一项目在多处触发时合并为一条，保留最高等级并汇总判定依据。"""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        key = row["项目/指标"]
        if key not in merged:
            merged[key] = dict(row)
            order.append(key)
            continue
        current = merged[key]
        keep_new = GRADE_RANK.get(row["等级"], 0) > GRADE_RANK.get(current["等级"], 0)
        base, other = (row, current) if keep_new else (current, row)
        combined = dict(base)
        combined["来源"] = "+".join(dict.fromkeys((current["来源"] + "+" + row["来源"]).split("+")))
        if other["判定依据"] and other["判定依据"] not in base["判定依据"]:
            combined["判定依据"] = f"{base['判定依据']}；{other['判定依据']}"
        for field in ("本期", "上期", "差异"):
            if combined[field] is None:
                combined[field] = other[field]
        if not combined.get("可能成因"):
            combined["可能成因"] = other.get("可能成因", "")
        if not combined.get("建议程序"):
            combined["建议程序"] = other.get("建议程序", "")
        merged[key] = combined
    return [merged[k] for k in order]
