#!/usr/bin/env python
"""生成脱敏样例数据：某制造业公司 2025 年度与 2024 年度四张报表。

样例中刻意包含若干异常（毛利率上升、应收账款增长快于收入、其他应收款大幅增长、
经营现金流下降、成本低于按毛利率测算的期望值等），用于验证程序能否识别。
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="D9E2F3")
BOLD = Font(bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = "#,##0.00"


def _title(ws, text: str, span: int):
    ws.cell(row=1, column=1, value=text).font = BOLD
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)


def _header_row(ws, row: int, headers: list[str]):
    for c, text in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=text)
        cell.font = BOLD
        cell.fill = HEADER_FILL
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _data_rows(ws, start_row: int, rows: list[list], money_cols: list[int]):
    for i, row in enumerate(rows):
        r = start_row + i
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = BORDER
            if c in money_cols and isinstance(value, (int, float)):
                cell.number_format = MONEY


def build_balance_sheet(ws):
    _title(ws, "编制单位：示例制造有限公司        2025年12月31日        单位：元", 6)
    _header_row(ws, 2, ["资产", "期末余额", "年初余额", "负债和所有者权益", "期末余额", "年初余额"])
    rows = [
        ["流动资产：", None, None, "流动负债：", None, None],
        ["货币资金", 28600000, 19800000, "短期借款", 35000000, 18000000],
        ["应收票据", 5200000, 4100000, "应付票据", 6000000, 5000000],
        ["应收账款", 42300000, 26500000, "应付账款", 24800000, 21600000],
        ["预付款项", 3600000, 2900000, "合同负债", 9200000, 7800000],
        ["其他应收款", 6800000, 2400000, "应付职工薪酬", 5400000, 4600000],
        ["存货", 31500000, 24000000, "应交税费", 4600000, 3100000],
        [None, None, None, "其他应付款", 3200000, 2700000],
        ["流动资产合计", 118000000, 79700000, "流动负债合计", 88200000, 62800000],
        ["非流动资产：", None, None, "非流动负债：", None, None],
        ["固定资产", 62400000, 58900000, "长期借款", 20000000, 16000000],
        ["在建工程", 8600000, 5200000, "非流动负债合计", 20000000, 16000000],
        ["无形资产", 9800000, 10400000, "负债合计", 108200000, 78800000],
        ["递延所得税资产", 1200000, 1000000, "所有者权益：", None, None],
        [None, None, None, "实收资本", 50000000, 50000000],
        ["非流动资产合计", 82000000, 75500000, "资本公积", 12000000, 12000000],
        [None, None, None, "盈余公积", 6800000, 5400000],
        [None, None, None, "未分配利润", 23000000, 9000000],
        [None, None, None, "所有者权益合计", 91800000, 76400000],
        ["资产总计", 200000000, 155200000, "负债和所有者权益总计", 200000000, 155200000],
    ]
    _data_rows(ws, 3, rows, [2, 3, 5, 6])
    for col, width in zip("ABCDEF", [22, 16, 16, 24, 16, 16]):
        ws.column_dimensions[col].width = width


def build_income_statement(ws):
    _title(ws, "编制单位：示例制造有限公司        2025年度        单位：元", 3)
    _header_row(ws, 2, ["项目", "本期金额", "上期金额"])
    rows = [
        ["一、营业收入", 156000000, 120000000],
        ["减：营业成本", 103000000, 84000000],
        ["税金及附加", 1250000, 960000],
        ["销售费用", 7200000, 6000000],
        ["管理费用", 12600000, 9800000],
        ["研发费用", 3800000, 3200000],
        ["财务费用", 2100000, 1500000],
        ["其中：利息费用", 2050000, 1450000],
        ["加：其他收益", 0, 0],
        ["投资收益", 0, 0],
        ["二、营业利润", 26050000, 14540000],
        ["加：营业外收入", 300000, 200000],
        ["减：营业外支出", 150000, 100000],
        ["三、利润总额", 26200000, 14640000],
        ["减：所得税费用", 5500000, 3900000],
        ["四、净利润", 20700000, 10740000],
    ]
    _data_rows(ws, 3, rows, [2, 3])
    for col, width in zip("ABC", [24, 18, 18]):
        ws.column_dimensions[col].width = width


def build_cash_flow(ws):
    _title(ws, "编制单位：示例制造有限公司        2025年度        单位：元", 3)
    _header_row(ws, 2, ["项目", "本期金额", "上期金额"])
    rows = [
        ["一、经营活动产生的现金流量：", None, None],
        ["销售商品、提供劳务收到的现金", 138000000, 118000000],
        ["收到的税费返还", 1200000, 800000],
        ["收到其他与经营活动有关的现金", 2800000, 2200000],
        ["经营活动现金流入小计", 142000000, 121000000],
        ["购买商品、接受劳务支付的现金", 92000000, 74000000],
        ["支付给职工以及为职工支付的现金", 18500000, 15200000],
        ["支付的各项税费", 9800000, 7600000],
        ["支付其他与经营活动有关的现金", 8000000, 4400000],
        ["经营活动现金流出小计", 128500000, 101000000],
        ["经营活动产生的现金流量净额", 13500000, 20000000],
        ["二、投资活动产生的现金流量：", None, None],
        ["购建固定资产、无形资产和其他长期资产支付的现金", 15800000, 11000000],
        ["投资活动现金流出小计", 15800000, 11000000],
        ["投资活动产生的现金流量净额", -15800000, -11000000],
        ["三、筹资活动产生的现金流量：", None, None],
        ["取得借款收到的现金", 45000000, 30000000],
        ["筹资活动现金流入小计", 45000000, 30000000],
        ["偿还债务支付的现金", 30000000, 25000000],
        ["分配股利、利润或偿付利息支付的现金", 3900000, 2800000],
        ["筹资活动现金流出小计", 33900000, 27800000],
        ["筹资活动产生的现金流量净额", 11100000, 2200000],
        ["四、现金及现金等价物净增加额", 8800000, 11200000],
        ["加：期初现金及现金等价物余额", 19800000, 8600000],
        ["五、期末现金及现金等价物余额", 28600000, 19800000],
    ]
    _data_rows(ws, 3, rows, [2, 3])
    for col, width in zip("ABC", [46, 18, 18]):
        ws.column_dimensions[col].width = width


def build_equity_statement(ws):
    _title(ws, "编制单位：示例制造有限公司        2025年度        单位：元", 11)
    ws.cell(row=2, column=1, value="项目").font = BOLD
    ws.cell(row=2, column=1).fill = HEADER_FILL
    ws.cell(row=2, column=1).border = BORDER
    ws.cell(row=2, column=2, value="本期金额").font = BOLD
    ws.merge_cells(start_row=2, start_column=2, end_row=2, end_column=6)
    ws.cell(row=2, column=7, value="上期金额").font = BOLD
    ws.merge_cells(start_row=2, start_column=7, end_row=2, end_column=11)
    for c in range(2, 12):
        ws.cell(row=2, column=c).fill = HEADER_FILL
        ws.cell(row=2, column=c).border = BORDER
        ws.cell(row=2, column=c).alignment = Alignment(horizontal="center")

    components = ["实收资本", "资本公积", "盈余公积", "未分配利润", "所有者权益合计"]
    _header_row(ws, 3, ["项目"] + components + components)

    rows = [
        ["一、上年年末余额", 50000000, 12000000, 5400000, 9000000, 76400000,
         50000000, 12000000, 4000000, 260000, 66260000],
        ["二、本年年初余额", 50000000, 12000000, 5400000, 9000000, 76400000,
         50000000, 12000000, 4000000, 260000, 66260000],
        ["三、本年增减变动金额", 0, 0, 1400000, 14000000, 15400000,
         0, 0, 1400000, 8740000, 10140000],
        ["（一）综合收益总额", 0, 0, 0, 20700000, 20700000,
         0, 0, 0, 10740000, 10740000],
        ["1.净利润", 0, 0, 0, 20700000, 20700000,
         0, 0, 0, 10740000, 10740000],
        ["（二）所有者投入和减少资本", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        ["（三）利润分配", 0, 0, 1400000, -6700000, -5300000,
         0, 0, 1400000, -2000000, -600000],
        ["四、本年年末余额", 50000000, 12000000, 6800000, 23000000, 91800000,
         50000000, 12000000, 5400000, 9000000, 76400000],
    ]
    _data_rows(ws, 4, rows, list(range(2, 12)))
    ws.column_dimensions["A"].width = 26
    for c in range(2, 12):
        ws.column_dimensions[get_column_letter(c)].width = 15


def main() -> None:
    outdir = Path(__file__).resolve().parent.parent / "samples"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / "示例-四张报表.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "资产负债表"
    build_balance_sheet(ws)
    build_income_statement(wb.create_sheet("利润表"))
    build_cash_flow(wb.create_sheet("现金流量表"))
    build_equity_statement(wb.create_sheet("所有者权益变动表"))
    wb.save(path)
    print(f"已生成样例：{path}")


if __name__ == "__main__":
    main()
