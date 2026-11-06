#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重资产企业财务指标批量计算器
归属：skill `heavy-asset-financial-analysis` / 子技能 02（statement-analysis）
      矿业价格敏感性部分供子技能 04（mining）使用。

用法
  python fin_metrics.py --input standard_dataset.json --out metrics.md
  python fin_metrics.py --input ds.json --industry real_estate --json-out metrics.json
  python fin_metrics.py --input ds.json --industry mining --sensitivity

约定
  - 金额单位统一为「万元」；比率输出为百分比。
  - 缺失值用 null 表示。缺失项不计算，输出 "—"，绝不按 0 处理。
  - 周转率用「平均余额」=（期初+期末）/2；无上期数据时退化为期末余额。
  - 利润表中减值损失填负数（asset_impairment / credit_impairment）。
  - 矿业敏感性假设：operating.sales_volume 单位=吨，unit_price / unit_cost / cash_cost 单位=元/吨，
    结果自动折算为万元（÷10000）。销量不随价格变化（刚性假设），除非传入 --volume-elasticity。
  - 敏感性基准情景按报表 EBITDA 校准，使基准净利润与报表口径可比。
"""

import argparse
import json
import sys

FIELDS = {
    "income": [
        "revenue", "cost_of_sales", "taxes_and_surcharges", "selling_exp", "admin_exp",
        "rd_exp", "finance_exp", "interest_expense", "investment_income",
        "fair_value_change", "asset_impairment", "credit_impairment", "asset_disposal",
        "other_income", "operating_profit", "depreciation_amortization", "non_recurring",
        "income_tax", "net_profit", "net_profit_attr_parent", "minority_interest_pl",
    ],
    "balance": [
        "cash", "restricted_cash", "short_term_investments", "notes_receivable",
        "accounts_receivable", "other_receivable", "prepayments", "inventory",
        "contract_assets", "total_current_assets", "long_term_equity_invest",
        "investment_property", "fixed_assets", "cip", "right_of_use_assets",
        "intangible_assets", "goodwill", "deferred_tax_assets", "total_assets",
        "short_term_loans", "notes_payable", "accounts_payable", "contract_liabilities",
        "advance_receipts", "other_payable", "current_portion_lt_debt",
        "other_current_liabilities", "total_current_liabilities", "long_term_loans",
        "bonds_payable", "lease_liabilities", "other_interest_bearing",
        "total_interest_bearing_debt", "total_liabilities", "total_equity",
        "equity_attr_parent", "minority_interest",
    ],
    "cashflow": [
        "cfo", "cfi", "cff", "capex", "capex_maintenance", "capex_growth",
        "depreciation_amortization", "interest_paid", "dividends_paid",
        "borrowings_received", "borrowings_repaid", "cash_received_from_sales",
        "cash_begin", "cash_end", "net_increase_cash",
    ],
    "operating": [
        "sales_amount", "sales_area", "sales_price", "cash_collection", "collection_rate",
        "land_reserve_area", "land_reserve_gmv", "land_cost", "construction_cost",
        "contracted_not_delivered", "resource_reserve", "mineable_reserve", "ore_grade",
        "capacity", "production_volume", "sales_volume", "recovery_rate", "unit_price",
        "unit_cost", "cash_cost", "stripping_ratio", "mine_life", "royalty",
    ],
}

DEFAULT_TAX_RATE = 0.25
INTEREST_BEARING_PARTS = [
    "short_term_loans", "current_portion_lt_debt", "long_term_loans",
    "bonds_payable", "lease_liabilities", "other_interest_bearing",
]


# ---------------------------------------------------------------- 基础工具

def load_dataset(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def s(ds, section, key):
    """取一条时间序列，返回 {period: float}。"""
    block = ds.get(section) or {}
    val = block.get(key)
    if isinstance(val, dict):
        return {k: x for k, x in val.items() if isinstance(x, (int, float))}
    if isinstance(val, (int, float)):
        base = (ds.get("meta") or {}).get("base_period")
        return {base: val} if base else {}
    return {}


def v(ds, section, key, period):
    return s(ds, section, key).get(period)


def periods(ds):
    meta = ds.get("meta") or {}
    if meta.get("periods"):
        return list(meta["periods"])
    found = set()
    for sec in ("income", "balance", "cashflow", "operating"):
        for k in (ds.get(sec) or {}):
            val = ds[sec][k]
            if isinstance(val, dict):
                found.update(val.keys())
    return sorted(found)


def div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def yoy(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return cur / prev - 1


def cagr(first, last, years):
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1


def prev_period(ps, p):
    try:
        i = ps.index(p)
    except ValueError:
        return None
    return ps[i - 1] if i > 0 else None


def avg_balance(ds, key, period, ps):
    """平均余额 =（上期期末 + 本期期末）/2；无上期则用期末值。"""
    cur = v(ds, "balance", key, period)
    if cur is None:
        return None
    pp = prev_period(ps, period)
    prev = v(ds, "balance", key, pp) if pp else None
    if prev is None:
        return cur
    return (cur + prev) / 2.0


# ---------------------------------------------------------------- 派生量

def interest_bearing_debt(ds, period):
    direct = v(ds, "balance", "total_interest_bearing_debt", period)
    if direct is not None:
        return direct
    parts = [v(ds, "balance", k, period) for k in INTEREST_BEARING_PARTS]
    if all(x is None for x in parts):
        return None
    return sum(x for x in parts if x is not None)


def ebitda(ds, period):
    op = v(ds, "income", "operating_profit", period)
    if op is None:
        return None
    da = v(ds, "income", "depreciation_amortization", period)
    if da is None:
        da = v(ds, "cashflow", "depreciation_amortization", period)
    itr = v(ds, "income", "interest_expense", period)
    return op + (da or 0) + (itr or 0)


def free_cash_flow(ds, period):
    cfo = v(ds, "cashflow", "cfo", period)
    if cfo is None:
        return None
    return cfo - (v(ds, "cashflow", "capex", period) or 0)


def total_assets(ds, period):
    ta = v(ds, "balance", "total_assets", period)
    return ta if ta is not None else v(ds, "balance", "total_current_assets", period)


def core_profit(ds, period):
    """主营利润 = 营业利润 − 投资收益 − 公允价值变动 − 其他收益 − 资产处置收益"""
    op = v(ds, "income", "operating_profit", period)
    if op is None:
        return None
    deduct, hit = 0.0, False
    for k in ("investment_income", "fair_value_change", "other_income", "asset_disposal"):
        x = v(ds, "income", k, period)
        if x is not None:
            deduct += x
            hit = True
    return op - deduct if hit else op


# ---------------------------------------------------------------- 指标计算

def compute(ds):
    ps = periods(ds)
    base = (ds.get("meta") or {}).get("base_period") or (ps[-1] if ps else None)
    out = {"meta": ds.get("meta") or {}, "base_period": base, "periods": ps, "rows": {}}

    def put(name, unit, values, note=""):
        out["rows"][name] = {"unit": unit, "values": values, "note": note}

    def series_of(fn):
        return {p: fn(p) for p in ps}

    # --- 规模与成长
    put("营业收入", "万元", series_of(lambda p: v(ds, "income", "revenue", p)))
    put("营业收入同比", "%", series_of(
        lambda p: yoy(v(ds, "income", "revenue", p),
                      v(ds, "income", "revenue", prev_period(ps, p))) if prev_period(ps, p) else None))
    if len(ps) >= 2:
        put("营业收入CAGR", "%",
            {ps[-1]: cagr(v(ds, "income", "revenue", ps[0]),
                          v(ds, "income", "revenue", ps[-1]), len(ps) - 1)},
            f"区间 {ps[0]}–{ps[-1]}")
    put("归母净利润", "万元", series_of(lambda p: v(ds, "income", "net_profit_attr_parent", p)))
    put("总资产", "万元", series_of(lambda p: v(ds, "balance", "total_assets", p)))
    put("总资产同比", "%", series_of(
        lambda p: yoy(v(ds, "balance", "total_assets", p),
                      v(ds, "balance", "total_assets", prev_period(ps, p))) if prev_period(ps, p) else None))

    # --- 盈利
    put("毛利", "万元", series_of(
        lambda p: (v(ds, "income", "revenue", p) - v(ds, "income", "cost_of_sales", p))
        if (v(ds, "income", "revenue", p) is not None
            and v(ds, "income", "cost_of_sales", p) is not None) else None))
    put("毛利率", "%", series_of(
        lambda p: div(v(ds, "income", "revenue", p) - v(ds, "income", "cost_of_sales", p),
                      v(ds, "income", "revenue", p))
        if v(ds, "income", "cost_of_sales", p) is not None else None))
    put("EBITDA", "万元", series_of(lambda p: ebitda(ds, p)))
    put("EBITDA率", "%", series_of(lambda p: div(ebitda(ds, p), v(ds, "income", "revenue", p))))
    put("净利润率", "%", series_of(
        lambda p: div(v(ds, "income", "net_profit", p), v(ds, "income", "revenue", p))))
    put("主营利润", "万元", series_of(lambda p: core_profit(ds, p)))
    put("主营利润占比", "%", series_of(
        lambda p: div(core_profit(ds, p), v(ds, "income", "operating_profit", p))))
    put("期间费用率", "%", series_of(
        lambda p: div(sum(x for x in (
            v(ds, "income", "selling_exp", p), v(ds, "income", "admin_exp", p),
            v(ds, "income", "rd_exp", p), v(ds, "income", "finance_exp", p)) if x is not None),
            v(ds, "income", "revenue", p))))
    put("财务费用率", "%", series_of(
        lambda p: div(v(ds, "income", "finance_exp", p), v(ds, "income", "revenue", p))))

    # --- 回报
    put("ROA", "%", series_of(
        lambda p: div(v(ds, "income", "net_profit", p), avg_balance(ds, "total_assets", p, ps))))
    put("ROE", "%", series_of(
        lambda p: div(v(ds, "income", "net_profit_attr_parent", p),
                      avg_balance(ds, "equity_attr_parent", p, ps)
                      or avg_balance(ds, "total_equity", p, ps))))

    # --- 营运效率
    put("应收账款周转天数", "天", series_of(
        lambda p: div(360 * avg_balance(ds, "accounts_receivable", p, ps),
                      v(ds, "income", "revenue", p))
        if avg_balance(ds, "accounts_receivable", p, ps) is not None else None))
    put("存货周转天数", "天", series_of(
        lambda p: div(360 * avg_balance(ds, "inventory", p, ps), v(ds, "income", "cost_of_sales", p))
        if avg_balance(ds, "inventory", p, ps) is not None else None))
    put("应付账款周转天数", "天", series_of(
        lambda p: div(360 * avg_balance(ds, "accounts_payable", p, ps),
                      v(ds, "income", "cost_of_sales", p))
        if avg_balance(ds, "accounts_payable", p, ps) is not None else None))

    def ccc(p):
        ar = out["rows"]["应收账款周转天数"]["values"].get(p)
        iv = out["rows"]["存货周转天数"]["values"].get(p)
        ap = out["rows"]["应付账款周转天数"]["values"].get(p)
        if ar is None or iv is None:
            return None
        return ar + iv - (ap or 0)
    put("现金转换周期", "天", series_of(ccc))
    put("总资产周转率", "次", series_of(
        lambda p: div(v(ds, "income", "revenue", p), avg_balance(ds, "total_assets", p, ps))))

    # --- 现金流
    put("经营现金流净额", "万元", series_of(lambda p: v(ds, "cashflow", "cfo", p)))
    put("自由现金流", "万元", series_of(lambda p: free_cash_flow(ds, p)))
    put("净现比", "倍", series_of(
        lambda p: div(v(ds, "cashflow", "cfo", p), v(ds, "income", "net_profit", p))))
    put("收现比", "倍", series_of(
        lambda p: div(v(ds, "cashflow", "cash_received_from_sales", p),
                      v(ds, "income", "revenue", p))))
    put("CAPEX", "万元", series_of(lambda p: v(ds, "cashflow", "capex", p)))
    put("CAPEX/收入", "%", series_of(
        lambda p: div(v(ds, "cashflow", "capex", p), v(ds, "income", "revenue", p))))
    put("CAPEX现金覆盖率", "倍", series_of(
        lambda p: div(v(ds, "cashflow", "cfo", p), v(ds, "cashflow", "capex", p))))

    def financing_dep(p):
        br = v(ds, "cashflow", "borrowings_received", p)
        cfo = v(ds, "cashflow", "cfo", p)
        if br is None or cfo is None:
            return None
        denom = cfo + (v(ds, "cashflow", "capex", p) or 0)
        return br / denom if denom > 0 else None
    put("融资依赖度", "%", series_of(financing_dep),
        "分母 = CFO + CAPEX；分母 ≤ 0 时指标不适用，显示「—」")

    # --- 债务与偿债
    put("有息负债", "万元", series_of(lambda p: interest_bearing_debt(ds, p)))
    put("净有息负债", "万元", series_of(
        lambda p: (interest_bearing_debt(ds, p) - v(ds, "balance", "cash", p))
        if (interest_bearing_debt(ds, p) is not None
            and v(ds, "balance", "cash", p) is not None) else None))
    put("资产负债率", "%", series_of(
        lambda p: div(v(ds, "balance", "total_liabilities", p), total_assets(ds, p))))
    put("净负债率", "%", series_of(
        lambda p: div(interest_bearing_debt(ds, p) - v(ds, "balance", "cash", p),
                      v(ds, "balance", "total_equity", p))
        if (interest_bearing_debt(ds, p) is not None
            and v(ds, "balance", "cash", p) is not None) else None))
    put("流动比率", "倍", series_of(
        lambda p: div(v(ds, "balance", "total_current_assets", p),
                      v(ds, "balance", "total_current_liabilities", p))))
    put("速动比率", "倍", series_of(
        lambda p: div(v(ds, "balance", "total_current_assets", p)
                      - (v(ds, "balance", "inventory", p) or 0),
                      v(ds, "balance", "total_current_liabilities", p))
        if v(ds, "balance", "total_current_assets", p) is not None else None))
    put("现金短债比", "倍", series_of(
        lambda p: div(v(ds, "balance", "cash", p),
                      (v(ds, "balance", "short_term_loans", p) or 0)
                      + (v(ds, "balance", "current_portion_lt_debt", p) or 0))
        if (v(ds, "balance", "short_term_loans", p) is not None
            or v(ds, "balance", "current_portion_lt_debt", p) is not None) else None))
    put("EBITDA/利息", "倍", series_of(
        lambda p: div(ebitda(ds, p), v(ds, "income", "interest_expense", p))))
    put("经营现金流/有息负债", "%", series_of(
        lambda p: div(v(ds, "cashflow", "cfo", p), interest_bearing_debt(ds, p))))
    put("短债占有息负债比", "%", series_of(
        lambda p: div((v(ds, "balance", "short_term_loans", p) or 0)
                      + (v(ds, "balance", "current_portion_lt_debt", p) or 0),
                      interest_bearing_debt(ds, p))
        if interest_bearing_debt(ds, p) else None))

    # --- 结构与集中度
    put("重资产程度", "%", series_of(
        lambda p: div(sum(x for x in (
            v(ds, "balance", "fixed_assets", p), v(ds, "balance", "cip", p),
            v(ds, "balance", "investment_property", p),
            v(ds, "balance", "intangible_assets", p)) if x is not None),
            total_assets(ds, p))))
    put("存货/总资产", "%", series_of(
        lambda p: div(v(ds, "balance", "inventory", p), total_assets(ds, p))))
    put("应收/总资产", "%", series_of(
        lambda p: div(v(ds, "balance", "accounts_receivable", p), total_assets(ds, p))))
    put("其他应收款/总资产", "%", series_of(
        lambda p: div(v(ds, "balance", "other_receivable", p), total_assets(ds, p))))
    put("商誉/归母净资产", "%", series_of(
        lambda p: div(v(ds, "balance", "goodwill", p), v(ds, "balance", "equity_attr_parent", p))))
    put("受限资金/货币资金", "%", series_of(
        lambda p: div(v(ds, "balance", "restricted_cash", p), v(ds, "balance", "cash", p))))
    return out


def mining_sensitivity(ds, elasticity=0.0, tax_rate=DEFAULT_TAX_RATE):
    """七档价格敏感性。基准情景按报表 EBITDA 校准，使基准净利润与报表口径可比。"""
    ps = periods(ds)
    base = (ds.get("meta") or {}).get("base_period") or ps[-1]
    q = v(ds, "operating", "sales_volume", base)
    p = v(ds, "operating", "unit_price", base)
    c = v(ds, "operating", "cash_cost", base)
    if c is None:
        c = v(ds, "operating", "unit_cost", base)
    if q is None or p is None or c is None:
        return None
    da = v(ds, "income", "depreciation_amortization", base)
    if da is None:
        da = v(ds, "cashflow", "depreciation_amortization", base) or 0
    itr = v(ds, "income", "interest_expense", base)
    capex = v(ds, "cashflow", "capex", base) or 0
    if itr == 0:
        itr = None  # 无法计算利息覆盖与偿债临界价

    # 校准：报表 EBITDA 与「销量×(单价−现金成本)」的差额作为固定项
    # （含期间费用、税金及附加、减值、投资收益等），全部情景保持不变。
    model_base = q * (p - c) / 1e4
    ebitda_actual = ebitda(ds, base)
    other = (ebitda_actual - model_base) if ebitda_actual is not None else 0.0

    rows = []
    for delta in (-0.30, -0.20, -0.10, 0.0, 0.10, 0.20, 0.30):
        pn = p * (1 + delta)
        qn = q * (1 - elasticity * abs(delta))
        revenue = qn * pn / 1e4
        cash_cost_total = qn * c / 1e4
        ebitda_v = revenue - cash_cost_total + other
        pretax = ebitda_v - da - (itr or 0)
        net = pretax * (1 - tax_rate)
        cfo = net + da
        fcf = cfo - capex
        rows.append({
            "情景": f"{delta:+.0%}" if delta else "基准",
            "单价(元/吨)": pn, "销量(吨)": qn, "收入(万元)": revenue,
            "EBITDA(万元)": ebitda_v, "净利润(万元)": net,
            "经营现金流(万元)": cfo, "自由现金流(万元)": fcf,
            "EBITDA/利息(倍)": (ebitda_v / itr) if itr else None,
        })

    def price_from(target_contribution):
        """由 Q×(P−C) + other = target 反解 P。"""
        return c + (target_contribution - other) * 1e4 / q

    return {
        "base": {"销量(吨)": q, "单价(元/吨)": p, "现金成本(元/吨)": c,
                 "折旧摊销(万元)": da, "利息支出(万元)": itr, "CAPEX(万元)": capex,
                 "所得税率": tax_rate, "校准差额(万元)": other,
                 "报表EBITDA(万元)": ebitda_actual, "模型EBITDA(万元)": model_base},
        "rows": rows,
        "breakeven": {
            "盈亏平衡价(元/吨)": price_from(da + (itr or 0)) if q else None,
            "现金平衡价(元/吨)": price_from(da + (itr or 0) - da / (1 - tax_rate)) if q else None,
            "偿债临界价(元/吨)": price_from(itr) if (q and itr) else None,
        },
    }


# ---------------------------------------------------------------- 输出

def fmt_cell(unit, val):
    if val is None:
        return "—"
    if unit == "%":
        return f"{val * 100:.1f}%"
    if unit == "天":
        return f"{val:,.0f}"
    if unit in ("倍", "次"):
        return f"{val:.2f}"
    return f"{val:,.0f}"


def render(result):
    L = []
    meta = result["meta"]
    ps = result["periods"]
    L.append(f"# 财务指标计算结果（{meta.get('short_name') or meta.get('company') or '未命名'}）")
    L.append("")
    L.append(f"- 口径：{meta.get('scope', '—')} | 币种：{meta.get('currency', 'CNY')} | "
             f"单位：{meta.get('unit', '万元')} | 期间：{'、'.join(ps) if ps else '—'}")
    L.append(f"- 基准期：{result['base_period']} | 行业：{meta.get('industry', '—')}")
    L.append("")
    L.append("| 指标 | 单位 | " + " | ".join(ps) + " |")
    L.append("|---|---|" + "---:|" * len(ps))
    notes = []
    for name, item in result["rows"].items():
        vals = [fmt_cell(item["unit"], item["values"].get(p)) for p in ps]
        if all(x == "—" for x in vals):
            continue
        L.append(f"| {name} | {item['unit']} | " + " | ".join(vals) + " |")
        if item.get("note"):
            notes.append(f"- **{name}**：{item['note']}")
    L.append("")
    if notes:
        L.append("### 口径说明")
        L.extend(notes)
        L.append("")
    L.append("> 说明：比率按百分比展示；周转天数按平均余额计算；"
             "缺失项显示为「—」，未按 0 参与计算。")
    return "\n".join(L)


def render_sensitivity(sens):
    if not sens:
        return "\n## 价格敏感性\n\n缺少 sales_volume / unit_price / cash_cost（或 unit_cost），无法测算。\n"
    b = sens["base"]
    L = ["", "## 矿业价格敏感性（七档情景）", ""]
    itr_txt = "—" if b["利息支出(万元)"] is None else f"{b['利息支出(万元)']:,.0f}"
    L.append(f"基准假设：销量 {b['销量(吨)']:,.0f} 吨，单价 {b['单价(元/吨)']:,.0f} 元/吨，"
             f"现金成本 {b['现金成本(元/吨)']:,.0f} 元/吨，折旧摊销 {b['折旧摊销(万元)']:,.0f} 万元，"
             f"利息支出 {itr_txt} 万元，所得税率 {b['所得税率']:.0%}")
    L.append("")
    L.append("| 情景 | 单价(元/吨) | 收入(万元) | EBITDA(万元) | 净利润(万元) | 经营现金流(万元) | 自由现金流(万元) | EBITDA/利息 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in sens["rows"]:
        cover = r["EBITDA/利息(倍)"]
        L.append("| {} | {:,.0f} | {:,.0f} | {:,.0f} | {:,.0f} | {:,.0f} | {:,.0f} | {} |".format(
            r["情景"], r["单价(元/吨)"], r["收入(万元)"], r["EBITDA(万元)"],
            r["净利润(万元)"], r["经营现金流(万元)"], r["自由现金流(万元)"],
            "—" if cover is None else f"{cover:.2f}"))
    L.append("")
    L.append("### 三条临界线")
    L.append("")
    L.append("| 临界线 | 价格(元/吨) | 相对基准价缓冲 |")
    L.append("|---|---:|---:|")
    for k, val in sens["breakeven"].items():
        if val is None:
            L.append(f"| {k} | — | — |")
        else:
            L.append(f"| {k} | {val:,.0f} | {val / b['单价(元/吨)'] - 1:+.1%} |")
    L.append("")
    actual = 0 if b["报表EBITDA(万元)"] is None else b["报表EBITDA(万元)"]
    L.append(f"**校准说明**：模型基准 EBITDA {b['模型EBITDA(万元)']:,.0f} 万元，"
             f"报表口径 EBITDA {actual:,.0f} 万元，"
             f"差额 {b['校准差额(万元)']:,.0f} 万元作为固定项（含期间费用、税金及附加、减值、投资收益等）"
             f"在全部情景中保持不变。因此基准情景净利润与报表净利润同口径，可直接比对。")
    L.append("")
    L.append("> 假设：销量不随价格变化（刚性）；单位成本不变；折旧摊销不变；"
             "经营现金流 = 净利润 + 折旧摊销（简化口径）。此为情景测算，非预测。")
    L.append(">")
    L.append("> **口径提醒**：上表经营现金流为简化口径，**不含营运资金变动**（应收、存货、应付）。"
             "若报表 CFO 与简化口径差异较大（例如报表 CFO 因存货与应收占用而显著更低），"
             "**偿债判断应以报表 CFO 为准**，本表仅用于价格弹性方向性比较。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="重资产企业财务指标批量计算器")
    ap.add_argument("--input", required=True, help="standard_dataset.json 路径")
    ap.add_argument("--out", help="Markdown 输出路径（缺省打印到标准输出）")
    ap.add_argument("--json-out", help="指标 JSON 输出路径")
    ap.add_argument("--industry", help="real_estate / mining / ...")
    ap.add_argument("--sensitivity", action="store_true", help="附加矿业价格敏感性测算")
    ap.add_argument("--tax-rate", type=float, default=DEFAULT_TAX_RATE, help="所得税率，默认 0.25")
    args = ap.parse_args()

    ds = load_dataset(args.input)
    if args.industry:
        ds.setdefault("meta", {})["industry"] = args.industry

    result = compute(ds)
    md = render(result)
    want_sens = args.sensitivity or (ds.get("meta") or {}).get("industry") == "mining"
    sens = mining_sensitivity(ds, tax_rate=args.tax_rate) if want_sens else None
    if want_sens:
        md += "\n" + render_sensitivity(sens)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"已写入：{args.out}")
    else:
        print(md)

    if args.json_out:
        payload = dict(result)
        if want_sens:
            payload["sensitivity"] = sens
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        print(f"已写入：{args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
