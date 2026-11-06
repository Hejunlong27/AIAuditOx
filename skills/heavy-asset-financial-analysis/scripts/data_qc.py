#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重资产财务数据质量检查器
归属：skill `heavy-asset-financial-analysis` / 子技能 01（data-prep）

用法
  python data_qc.py --input standard_dataset.json --out data-quality-report.md
  python data_qc.py --input ds.json            # 打印到标准输出

检查项（12 条）
  1 核心数据缺失   2 单位疑误   3 期间一致性   4 科目归组   5 空值统计
  6 勾稽-资产      7 勾稽-现金  8 勾稽-利润   9 经营-财务匹配
 10 溯源覆盖率    11 可计算指标清单   12 无法计算指标及原因

输出 qc.status：pass / warn / fail（核心 4 类任一缺失 → fail，应停止下传）
"""

import argparse
import json
import sys

CORE_INCOME = ["revenue", "cost_of_sales", "operating_profit", "net_profit"]
CORE_BALANCE = [
    "cash", "accounts_receivable", "inventory", "total_current_assets", "total_assets",
    "total_current_liabilities", "total_liabilities", "total_equity",
]
CORE_CASHFLOW = ["cfo", "cfi", "cff", "cash_begin", "cash_end"]

COMPUTABLE_MAP = {
    "收入与成长性指标": [("income", "revenue")],
    "毛利与毛利率": [("income", "revenue"), ("income", "cost_of_sales")],
    "EBITDA / EBITDA率": [("income", "operating_profit"),
                          ("cashflow", "depreciation_amortization")],
    "净利率 / ROA / ROE": [("income", "net_profit"), ("balance", "total_assets"),
                           ("balance", "equity_attr_parent")],
    "主营利润占比": [("income", "operating_profit"), ("income", "investment_income")],
    "周转天数与CCC": [("income", "revenue"), ("income", "cost_of_sales"),
                      ("balance", "accounts_receivable"), ("balance", "inventory"),
                      ("balance", "accounts_payable")],
    "净现比 / 收现比": [("cashflow", "cfo"), ("income", "net_profit"),
                        ("cashflow", "cash_received_from_sales")],
    "CAPEX 覆盖率 / 自由现金流": [("cashflow", "cfo"), ("cashflow", "capex")],
    "有息负债与净负债率": [("balance", "total_interest_bearing_debt"), ("balance", "cash"),
                           ("balance", "total_equity")],
    "现金短债比 / 流动速动比率": [("balance", "short_term_loans"),
                                  ("balance", "current_portion_lt_debt"),
                                  ("balance", "total_current_assets"),
                                  ("balance", "total_current_liabilities")],
    "EBITDA/利息 与利息保障": [("income", "interest_expense")],
    "债务期限墙": [("debt_schedule", "*")],
    "房地产：去化率 / 回款率 / 土储货值": [("operating", "sales_amount"),
                                            ("operating", "cash_collection"),
                                            ("operating", "land_reserve_gmv")],
    "矿业：单位成本 / 储采比 / 价格敏感性": [("operating", "sales_volume"),
                                              ("operating", "unit_price"),
                                              ("operating", "unit_cost"),
                                              ("operating", "mineable_reserve")],
}


def load(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def series(ds, section, key):
    block = ds.get(section) or {}
    val = block.get(key)
    if isinstance(val, dict):
        return {k: v for k, v in val.items() if isinstance(v, (int, float))}
    if isinstance(val, (int, float)):
        return {"__value__": val}
    return {}


def val_at(ds, section, key, period):
    return series(ds, section, key).get(period)


def periods(ds):
    meta = ds.get("meta") or {}
    if meta.get("periods"):
        return list(meta["periods"])
    found = set()
    for sec in ("income", "balance", "cashflow", "operating"):
        for k in (ds.get(sec) or {}):
            v = ds[sec][k]
            if isinstance(v, dict):
                found.update(v.keys())
    return sorted(found)


def has(ds, section, key, period):
    return val_at(ds, section, key, period) is not None


def check(ds):
    ps = periods(ds)
    meta = ds.get("meta") or {}
    res = {"meta": meta, "periods": ps, "core_missing": [], "issues": [],
           "pass": [], "warn": [], "fail": [], "computable": [], "not_computable": []}

    # 1 核心数据缺失
    core = ([(("income"), k) for k in CORE_INCOME] + [("balance", k) for k in CORE_BALANCE]
            + [("cashflow", k) for k in CORE_CASHFLOW])
    for sec, k in core:
        miss = [p for p in ps if not has(ds, sec, k, p)]
        if miss:
            res["core_missing"].append({"field": f"{sec}.{k}", "missing_periods": miss})
    if res["core_missing"]:
        res["fail"].append(
            f"核心数据缺失 {len(res['core_missing'])} 项："
            + "、".join(x["field"] for x in res["core_missing"][:8])
            + ("…" if len(res["core_missing"]) > 8 else "")
            + " → 应暂停下传并索取数据")

    # 2 单位疑误（数量级校验）
    for p in ps:
        rev = val_at(ds, "income", "revenue", p)
        ta = val_at(ds, "balance", "total_assets", p)
        inv = val_at(ds, "balance", "inventory", p)
        if rev and ta and rev / ta > 10:
            res["warn"].append(f"{p}：收入/总资产 = {rev/ta:.1f}，数量级异常，疑单位错误")
        if inv is not None and ta and inv / ta > 1.05:
            res["warn"].append(f"{p}：存货 > 总资产，疑科目错位或单位错误")

    # 3 期间一致性
    for sec in ("income", "balance", "cashflow"):
        for k in (ds.get(sec) or {}):
            ks = list(series(ds, sec, k).keys())
            if ks and sorted(ks) != sorted(ps):
                res["warn"].append(
                    f"{sec}.{k} 期间不完整：{sorted(ks)} ≠ {sorted(ps)}")
                break

    # 4 科目归组（无法映射到标准字典的键）
    known = set()
    for sec in ("income", "balance", "cashflow", "operating"):
        known.add(sec)
    for sec in ("income", "balance", "cashflow", "operating"):
        for k in (ds.get(sec) or {}):
            if k in ("__extra__", "extra"):
                res["warn"].append(f"{sec} 存在未归组科目：{k}")
    unknown = [k for k in (ds.get("__unknown__") or {})]
    if unknown:
        res["warn"].append("存在未归组科目：" + "、".join(unknown[:10]))

    # 5 空值统计
    nulls = []
    for sec in ("income", "balance", "cashflow"):
        for k in (ds.get(sec) or {}):
            block = ds[sec][k]
            if isinstance(block, dict):
                for p, x in block.items():
                    if x is None:
                        nulls.append(f"{sec}.{k}@{p}")
    if nulls:
        res["issues"].append(f"显式空值 {len(nulls)} 处（示例：{', '.join(nulls[:5])}）")

    # 6 勾稽-资产
    for p in ps:
        a = val_at(ds, "balance", "total_assets", p)
        l = val_at(ds, "balance", "total_liabilities", p)
        e = val_at(ds, "balance", "total_equity", p)
        if None in (a, l, e) or not a:
            continue
        diff = a - (l + e)
        rate = abs(diff) / a
        tag = "通过" if rate <= 0.01 else "异常"
        (res["pass"] if rate <= 0.01 else res["fail"]).append(
            f"{p} 资产=负债+权益 差额 {diff:,.0f} 万元（{rate:.2%}）→ {tag}")

    # 7 勾稽-现金
    for p in ps:
        cb = val_at(ds, "cashflow", "cash_begin", p)
        ce = val_at(ds, "cashflow", "cash_end", p)
        cfo = val_at(ds, "cashflow", "cfo", p)
        cfi = val_at(ds, "cashflow", "cfi", p)
        cff = val_at(ds, "cashflow", "cff", p)
        if None in (cb, ce, cfo, cfi, cff):
            continue
        diff = ce - (cb + cfo + cfi + cff)
        rate = abs(diff) / abs(ce) if ce else 0
        tag = "通过" if rate <= 0.01 else "异常"
        (res["pass"] if rate <= 0.01 else res["fail"]).append(
            f"{p} 期末现金=期初+CFO+CFI+CFF 差额 {diff:,.0f} 万元（{rate:.2%}）→ {tag}")

    # 8 勾稽-利润（近似）
    for p in ps:
        rev = val_at(ds, "income", "revenue", p)
        op = val_at(ds, "income", "operating_profit", p)
        if rev is None or op is None:
            continue
        deduct = sum(x for x in (
            val_at(ds, "income", "cost_of_sales", p),
            val_at(ds, "income", "taxes_and_surcharges", p),
            val_at(ds, "income", "selling_exp", p),
            val_at(ds, "income", "admin_exp", p),
            val_at(ds, "income", "rd_exp", p),
            val_at(ds, "income", "finance_exp", p)) if x is not None)
        add = sum(x for x in (
            val_at(ds, "income", "investment_income", p),
            val_at(ds, "income", "fair_value_change", p),
            val_at(ds, "income", "other_income", p),
            val_at(ds, "income", "asset_disposal", p)) if x is not None)
        imp = sum(x for x in (
            val_at(ds, "income", "asset_impairment", p),
            val_at(ds, "income", "credit_impairment", p)) if x is not None)
        approx = rev - deduct + add + imp
        diff = op - approx
        rate = abs(diff) / abs(rev) if rev else 0
        tag = "通过" if rate <= 0.03 else "需复核"
        (res["pass"] if rate <= 0.03 else res["warn"]).append(
            f"{p} 营业利润勾稽 差额 {diff:,.0f} 万元（占收入 {rate:.2%}）→ {tag}")

    # 9 经营-财务匹配
    industry = (meta.get("industry") or "").lower()
    for p in ps:
        rev = val_at(ds, "income", "revenue", p)
        sa = val_at(ds, "operating", "sales_amount", p)
        if rev and sa:
            d = abs(sa - rev) / rev
            if d > 0.10:
                msg = (f"{p} 签约金额 {sa:,.0f} 与收入 {rev:,.0f} 偏差 {d:.1%}（>10%）")
                if industry in ("real_estate", "city_renewal", "industrial_park"):
                    res["issues"].append(
                        msg + " → 房地产行业签约与结算存在时滞，属正常差异，须在报告中说明结算节奏")
                else:
                    res["warn"].append(msg + " → 需追因")
        q = val_at(ds, "operating", "sales_volume", p)
        up = val_at(ds, "operating", "unit_price", p)
        if rev and q and up:
            implied = q * up / 1e4
            d = abs(implied - rev) / rev
            if d > 0.10:
                res["warn"].append(
                    f"{p} 产量×单价推算收入 {implied:,.0f} 与报表收入 {rev:,.0f} 偏差 {d:.1%}（>10%）→ 需追因")

    # 10 溯源覆盖率（同时接受 "section.key" 与 "key" 两种写法）
    prov = ds.get("provenance") or {}

    def covered(sec, k):
        return (f"{sec}.{k}" in prov) or (k in prov)

    keyfields = [("income", "revenue"), ("income", "net_profit"),
                 ("balance", "total_assets"), ("balance", "cash"),
                 ("balance", "total_liabilities"), ("cashflow", "cfo"),
                 ("cashflow", "capex")]
    hit = [f"{sec}.{k}" for sec, k in keyfields if covered(sec, k)]
    total = len(keyfields)
    rate = len(hit) / total
    if rate < 1:
        res["warn"].append(f"溯源覆盖率 {rate:.0%}（{len(hit)}/{total}），"
                           f"未标注：{'、'.join(f'{sec}.{k}' for sec, k in keyfields if not covered(sec, k))}")
    else:
        res["pass"].append(f"溯源覆盖率 100%（{total}/{total}）")

    # 11/12 可计算 / 无法计算
    for name, reqs in COMPUTABLE_MAP.items():
        ok = True
        missing = []
        for sec, k in reqs:
            if k == "*":
                if not ds.get(sec):
                    ok = False
                    missing.append(f"{sec}")
                continue
            if not any(val_at(ds, sec, k, p) is not None for p in ps):
                ok = False
                missing.append(f"{sec}.{k}")
        if ok:
            res["computable"].append(name)
        else:
            res["not_computable"].append((name, missing))

    status = "fail" if res["fail"] else ("warn" if res["warn"] else "pass")
    res["status"] = status
    return res


def render(res):
    m = res["meta"]
    L = []
    L.append(f"# 数据质量报告（{m.get('short_name') or m.get('company') or '未命名'}）")
    L.append("")
    L.append(f"- 口径：{m.get('scope', '—')} | 币种：{m.get('currency', 'CNY')} | "
             f"单位：{m.get('unit', '万元')} | 是否经审计：{'是' if m.get('audited') else '否/未声明'}")
    L.append(f"- 期间：{'、'.join(res['periods']) or '—'} | 基准期：{m.get('base_period', '—')}")
    L.append(f"- **qc.status：{res['status'].upper()}**")
    L.append("")

    L.append("## 一、核心数据缺失")
    if not res["core_missing"]:
        L.append("无。核心 4 类（资产 / 负债 / 收入 / 现金流）齐备。")
    else:
        L.append("| 缺失字段 | 缺失期间 |")
        L.append("|---|---|")
        for x in res["core_missing"]:
            L.append(f"| {x['field']} | {'、'.join(x['missing_periods'])} |")
        L.append("")
        L.append("> **处置**：核心数据缺失 → qc.status=fail，停止下传，向用户索取数据后再继续。")

    def block(title, items, empty="无。"):
        L.append("")
        L.append(f"## {title}")
        if not items:
            L.append(empty)
        else:
            for x in items:
                L.append(f"- {x}")

    block("二、勾稽与一致性检查（通过项）", res["pass"], "无。")
    block("三、需关注事项（warn）", res["warn"], "无。")
    block("四、异常事项（fail）", res["fail"], "无。")
    block("五、其他记录", res["issues"], "无。")

    L.append("")
    L.append("## 六、可计算指标清单")
    if res["computable"]:
        for x in res["computable"]:
            L.append(f"- {x}")
    else:
        L.append("无。")

    L.append("")
    L.append("## 七、无法计算指标及原因")
    if res["not_computable"]:
        L.append("| 指标 | 缺失字段 |")
        L.append("|---|---|")
        for name, miss in res["not_computable"]:
            L.append(f"| {name} | {'、'.join(miss)} |")
    else:
        L.append("无。")
    L.append("")
    L.append("---")
    L.append("> 说明：本报告仅做数据层面判定，不含经营与财务分析结论。"
             "所有差额已如实列示，未做调平处理。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="重资产财务数据质量检查器")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    ds = load(args.input)
    res = check(ds)
    md = render(res)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"已写入：{args.out}（qc.status={res['status']}）")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
