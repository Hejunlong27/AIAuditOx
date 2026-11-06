"""输出：Excel 分析工作簿、Word 分析底稿、异常清单 CSV、运行日志、修订记录。

Excel 严格对齐 AuditOx 四段式底稿制式：
    【底稿名称】 / 一、项目基本信息 / 二、审计目标和程序说明 /
    三、审计程序执行结果 / 四、审计说明

制式要点：宋体；标题 16pt 加粗居中；副标题 9pt 灰字；节标题 12pt 加粗、
E8E8E8 底纹全边框；表头 10pt 加粗、D9D9D9 底纹；正文 10pt；
金额 #,##0.00、百分比 0.00%；可计算的列一律写入 Excel 公式，不硬编码结果。
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.datavalidation import DataValidation

from .analysis import AnalysisResult
from . import config as cfg


# ------------------------------------------------------------ 制式样式常量

FONT_NAME = "宋体"

TITLE_FONT = Font(name=FONT_NAME, size=16, bold=True)
SUBTITLE_FONT = Font(name=FONT_NAME, size=9, color="FF666666")
NOTE_FONT = Font(name=FONT_NAME, size=9, color="FFC00000")
SECTION_FONT = Font(name=FONT_NAME, size=12, bold=True)
TABLE_HEADER_FONT = Font(name=FONT_NAME, size=10, bold=True)
BODY_FONT = Font(name=FONT_NAME, size=10)
LABEL_FONT = Font(name=FONT_NAME, size=10, bold=True)
EXAMPLE_FONT = Font(name=FONT_NAME, size=10, italic=True, color="FF808080")

SECTION_FILL = PatternFill("solid", fgColor="FFE8E8E8")
TABLE_HEADER_FILL = PatternFill("solid", fgColor="FFD9D9D9")

_THIN = Side(style="thin", color="FF000000")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

MONEY_FMT = "#,##0.00"
PERCENT_FMT = "0.00%"
NUMBER_FMT = "0.00"

# 工作簿索引号：通用辅助类 A，程序 9（报表分析）
INDEX_PREFIX = "A-9"

# 列宽：openpyxl 新建列维度自带默认宽度 13，若直接与目标宽度取较大者会把窄列卡死，
# 因此改为先在 worksheet 上登记期望宽度，最后统一落笔。
MIN_COL_WIDTH = 3.0

CENTER_HEADERS = {
    "序号", "编号", "报表", "等级", "来源", "是否关注", "是否触发", "单位", "方向",
    "分级", "模型", "模型置信度", "是否已实施", "对应认定", "检查项", "项目",
    "分组", "基准",
}

TEXT_HEADERS = {
    "检查项", "项目", "结论", "说明", "报表", "是否关注", "是否触发", "备注",
    "等级", "来源", "项目/指标", "判定依据", "可能成因", "建议程序", "人工结论",
    "编号", "模型", "驱动关系", "驱动因子", "方向判断", "模型置信度", "分组",
    "指标", "单位", "方向", "判断依据", "触发阈值", "审计程序", "对应认定",
    "是否已实施", "执行结果说明", "未映射项目", "内容", "基准", "数据来源与年份",
}

WIDTH_BY_HEADER = {
    "序号": 5, "编号": 8, "报表": 10, "项目": 22, "项目/指标": 22, "指标": 20,
    "检查项": 16, "等级": 11, "来源": 14, "本期": 16, "上期": 16, "差异": 16,
    "金额一": 16, "金额二": 16, "容忍额": 16, "本期金额": 16, "上期金额": 16,
    "变动额": 16, "变动率": 11, "本期占比": 11, "上期占比": 11,
    "占比变动(百分点)": 13, "金额变动": 16, "是否关注": 10, "基准": 12,
    "基准本期金额": 16, "基准上期金额": 16, "单位": 6, "方向": 10, "备注": 30,
    "模型": 8, "驱动关系": 26, "驱动因子": 16, "本期实际": 16, "期望值": 16,
    "差异率": 11, "可容忍差异": 16, "分级": 11, "方向判断": 26, "模型置信度": 10,
    "可能成因": 44, "建议程序": 44, "人工结论": 18, "判定依据": 44, "说明": 44,
    "是否触发": 10, "判断依据": 20, "触发阈值": 18, "实际值": 12,
    "审计程序": 46, "对应认定": 12, "是否已实施": 10, "执行结果说明": 32,
    "本被审计单位本期": 16, "本被审计单位上期": 16, "行业中位数": 14,
    "行业上四分位": 14, "行业下四分位": 14, "偏离程度": 14, "数据来源与年份": 24,
    "未映射项目": 80, "内容": 80,
}

TEXT_PRIORITY = (
    "审计程序", "执行结果说明", "说明", "判定依据", "可能成因", "建议程序", "备注",
    "未映射项目", "内容", "驱动关系", "方向判断", "项目", "项目/指标", "检查项",
    "来源", "报表", "模型",
)

SHEET_TEMPLATE = [
    "说明与参数", "数据校验", "结构分析", "两年对比", "比率分析", "期望值模型",
    "一致性检查", "异常汇总", "未映射清单", "行业对比（待填）", "图表",
]

# 单位敏感的列：同一列可能出现倍、天、次、百分比等不同单位，需按行单位决定格式
UNIT_SENSITIVE_HEADERS = {"本期", "上期", "变动", "本被审计单位本期", "本被审计单位上期"}
UNIT_FORMATS = {"%": PERCENT_FMT, "倍": NUMBER_FMT, "次": NUMBER_FMT, "天": NUMBER_FMT}


def sheet_index(number: int) -> str:
    """返回底稿索引号，如 A-9-01。"""
    return f"{INDEX_PREFIX}-{number:02d}"


def sheet_name(number: int) -> str:
    """工作表名 = 索引号 + 底稿名称。"""
    return f"{sheet_index(number)} {SHEET_TEMPLATE[number - 1]}"


# ------------------------------------------------------------------ 格式工具


def column_format(header: str) -> str | None:
    h = str(header)
    if "百分点" in h:
        return NUMBER_FMT
    if "率" in h or "占比" in h:
        return PERCENT_FMT
    if h in TEXT_HEADERS:
        return None
    if h == "实际值":
        return "0.0000"
    if "天" in h or "次" in h or "倍" in h:
        return NUMBER_FMT
    if any(k in h for k in ("金额", "差异", "期望值", "容忍", "变动", "基准", "测算", "本期", "上期")):
        return MONEY_FMT
    return None


def fmt_value(value, header: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        h = str(header)
        if "百分点" in h:
            return f"{value:,.2f}"
        if "率" in h or "占比" in h:
            return f"{value:,.2%}"
        if "天" in h or "次" in h or "倍" in h:
            return f"{value:,.2f}"
        if h == "实际值":
            return f"{value:,.4f}"
        return f"{value:,.2f}"
    return str(value)


def cell_format(header: str, row) -> str | None:
    fmt = column_format(header)
    unit = row.get("单位") if isinstance(row, dict) else None
    if isinstance(unit, str) and header in UNIT_SENSITIVE_HEADERS:
        fmt = UNIT_FORMATS.get(unit, fmt)
    return fmt


def fmt_cell(value, header: str, row) -> str:
    unit = row.get("单位") if isinstance(row, dict) else None
    if isinstance(value, (int, float)) and header in UNIT_SENSITIVE_HEADERS and isinstance(unit, str):
        if unit == "%":
            return f"{value:,.2%}"
        if unit in ("倍", "次", "天"):
            return f"{value:,.2f}"
    return fmt_value(value, header)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _register_width(ws, index: int, width: float) -> None:
    """登记某列的期望宽度（取各表最大值），不直接写入列维度。"""
    store = ws.__dict__.setdefault("_fs_widths", {})
    letter = get_column_letter(index)
    store[letter] = max(store.get(letter, 0.0), float(width))


def _apply_widths(ws) -> None:
    """把登记的期望宽度统一写入列维度，保证同一张工作表的列宽固定、可复现。"""
    store = ws.__dict__.get("_fs_widths") or {}
    for letter, width in store.items():
        ws.column_dimensions[letter].width = round(max(MIN_COL_WIDTH, width), 2)


def _setup_print(ws) -> None:
    """打印设置：A4 横向；过宽的表按 2～3 页宽输出，避免缩得无法阅读；
    跨页重复标题行与前两列，水平居中。"""
    total = sum((ws.__dict__.get("_fs_widths") or {}).values())
    pages_wide = 1 if total <= 150 else (2 if total <= 300 else 3)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = pages_wide
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:2"
    ws.print_title_cols = "A:B"
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5


def _distribute_spans(headers: list[str], layout_cols: int) -> list[int]:
    """把 layout_cols 列分配给各逻辑列，多余宽度优先给文本列，避免表格右端留空。"""
    n = len(headers)
    if n == 0:
        return []
    spans = [1] * n
    extra = layout_cols - n
    if extra <= 0:
        return spans
    priority = [i for i, h in enumerate(headers) if h in TEXT_PRIORITY]
    if not priority:
        priority = [i for i, h in enumerate(headers) if column_format(h) is None] or list(range(n))
    for k in range(extra):
        spans[priority[k % len(priority)]] += 1
    return spans


# ------------------------------------------------------------------ Excel 制式构件


def _merge_cell(ws, row, c1, c2, value, font, *, align="left", valign="center",
                wrap=False, fill=None, border=None, height=None, number_format=None):
    if c2 > c1:
        ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    cell = ws.cell(row=row, column=c1, value=value)
    cell.font = font
    cell.alignment = Alignment(horizontal=align, vertical=valign, wrap_text=wrap)
    if number_format:
        cell.number_format = number_format
    if fill is not None or border is not None:
        for c in range(c1, c2 + 1):
            target = ws.cell(row=row, column=c)
            if fill is not None:
                target.fill = fill
            if border is not None:
                target.border = border
    if height:
        ws.row_dimensions[row].height = height
    return cell


def _title_block(ws, title: str, subtitle: str, ncols: int):
    _merge_cell(ws, 1, 1, ncols, title, TITLE_FONT, align="center", height=30)
    _merge_cell(ws, 2, 1, ncols, subtitle, SUBTITLE_FONT, align="center", wrap=True, height=16)
    return 3


def _section_row(ws, row, ncols, text):
    _merge_cell(ws, row, 1, ncols, text, SECTION_FONT, align="left", wrap=True,
                fill=SECTION_FILL, border=BORDER, height=20)
    return row + 1


def _info_cell(ws, row, c1, c2, label, value):
    """合并整段写一个要素：标签加粗、内容常规，避免窄列裁切。"""
    if c2 > c1:
        ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    cell = ws.cell(row=row, column=c1)
    cell.value = CellRichText([
        TextBlock(InlineFont(b=True), f"{label}："),
        "" if value in (None, "") else str(value),
    ])
    cell.font = BODY_FONT
    cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
    for c in range(c1, c2 + 1):
        ws.cell(row=row, column=c).border = BORDER


def _info_block(ws, row, ncols, entity, period, index):
    """表头七要素：被审计单位、审计期间、索引号、编制人、编制日期、审核人、审核日期。"""
    groups = [
        [("被审计单位", entity)],
        [("审计期间", period), ("索引号", index)],
        [("编制人", ""), ("编制日期", "")],
        [("审核人", ""), ("审核日期", "")],
    ]
    for pairs in groups:
        k = len(pairs)
        seg = max(1, ncols // k)
        starts = [1 + i * seg for i in range(k)]
        ends = [starts[i] + seg - 1 for i in range(k)]
        ends[-1] = ncols
        for (label, value), s, e in zip(pairs, starts, ends):
            _info_cell(ws, row, s, e, label, value)
        ws.row_dimensions[row].height = 20
        row += 1
    return row


def _objective_row(ws, row, ncols, text):
    _merge_cell(ws, row, 1, ncols, text, BODY_FONT, align="left", wrap=True, height=30)
    return row + 1


def _procedure_table(ws, row, ncols, procedures):
    """二、审计目标和程序说明 的程序表（含 是否已实施 下拉）。"""
    headers = ["序号", "审计程序", "对应认定", "是否已实施", "执行结果说明"]
    rest = ncols - 3
    proc = max(2, rest // 2)
    note = max(1, rest - proc)
    spans = [1, proc, 1, 1, note]
    spans[-1] += ncols - sum(spans)
    rows = [
        {"序号": i, "审计程序": text, "对应认定": attest, "是否已实施": "是",
         "执行结果说明": outcome}
        for i, (text, attest, outcome) in enumerate(procedures, start=1)
    ]
    next_row = _data_table(ws, row, headers, rows, spans=spans)
    col_letter = get_column_letter(1 + 1 + proc + 1)
    dv = DataValidation(type="list", formula1='"是,否,不适用"', allow_blank=True)
    dv.error = "请选择：是 / 否 / 不适用"
    dv.errorTitle = "输入不合规"
    ws.add_data_validation(dv)
    dv.add(f"{col_letter}{row + 1}:{col_letter}{row + len(rows)}")
    return next_row


def _data_table(ws, row, headers, rows, *, spans=None, formulas=None, formats=None):
    """写一张数据表：10pt 加粗 D9D9D9 表头、10pt 正文、全边框、可复算公式。"""
    spans = spans or [1] * len(headers)
    ncols = sum(spans)

    header_col: dict[str, str] = {}
    col = 1
    for header, span in zip(headers, spans):
        c1, c2 = col, col + span - 1
        if span > 1:
            ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
        cell = ws.cell(row=row, column=c1, value=header)
        cell.font = TABLE_HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for cc in range(c1, c2 + 1):
            target = ws.cell(row=row, column=cc)
            target.fill = TABLE_HEADER_FILL
            target.border = BORDER
        header_col[header] = get_column_letter(c1)
        col = c2 + 1
    ws.row_dimensions[row].height = 24

    r = row + 1
    for data in rows:
        col = 1
        max_len = 0
        for header, span in zip(headers, spans):
            c1, c2 = col, col + span - 1
            if span > 1:
                ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
            formula = formulas(header, r, data, header_col) if formulas else None
            value = formula if formula else data.get(header)
            cell = ws.cell(row=r, column=c1, value=value)
            cell.font = BODY_FONT
            fmt = formats(header, data) if formats else cell_format(header, data)
            numeric = formula is not None or _is_number(data.get(header))
            if numeric:
                cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=False)
                if fmt:
                    cell.number_format = fmt
            elif header in CENTER_HEADERS:
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                max_len = max(max_len, len(str(value)) if value is not None else 0)
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
                max_len = max(max_len, len(str(value)) if value is not None else 0)
            for cc in range(c1, c2 + 1):
                ws.cell(row=r, column=cc).border = BORDER
            col = c2 + 1
        ws.row_dimensions[r].height = 18 if max_len <= 16 else (30 if max_len <= 60 else 45)
        r += 1

    desired = [0.0] * ncols
    col = 1
    for header, span in zip(headers, spans):
        width = WIDTH_BY_HEADER.get(header, 16)
        per = max(3.0, width / span)
        for k in range(span):
            desired[col - 1 + k] = max(desired[col - 1 + k], per)
        col += span
    for i, width in enumerate(desired, start=1):
        _register_width(ws, i, width)
    return r


def _audit_notes(ws, row, ncols, notes, companion):
    """四、审计说明：编号说明行 + 签字行 + 修订记录伴随声明。"""
    for i, note in enumerate(notes, start=1):
        _merge_cell(ws, row, 1, ncols, f"{i}、{note}", BODY_FONT, align="left",
                    wrap=True, height=20)
        row += 1
    _merge_cell(ws, row, 1, ncols,
                "编制人：____________　日期：____________　　　　审核人：____________　日期：____________",
                BODY_FONT, align="left", height=20)
    row += 1
    _merge_cell(ws, row, 1, ncols,
                f"注：本底稿由分析程序自动生成，同路径伴随《{companion}》，每次修订同步登记。",
                NOTE_FONT, align="left", wrap=True, height=20)
    return row + 1


def _compose_sheet(ws, *, index, title, subtitle, entity, period, objective, procedures,
                   notes, layout_cols, companion, headers=None, rows=None, spans=None,
                   formulas=None, formats=None, kv_rows=None, red_note=None):
    """按四段式制式组装一张底稿工作表。"""
    ncols = layout_cols
    row = _title_block(ws, title, subtitle, ncols)
    row = 4
    if red_note:
        _merge_cell(ws, row, 1, ncols, red_note, NOTE_FONT, align="left", wrap=True, height=26)
        row += 1

    row = _section_row(ws, row, ncols, "一、项目基本信息")
    row = _info_block(ws, row, ncols, entity, period, index)

    row = _section_row(ws, row, ncols, "二、审计目标和程序说明")
    row = _objective_row(ws, row, ncols, objective)
    row = _procedure_table(ws, row, ncols, procedures)

    row = _section_row(ws, row, ncols, "三、审计程序执行结果")
    if kv_rows is not None:
        table_headers = headers or ["项目", "内容"]
        table_spans = spans or _distribute_spans(table_headers, ncols)
        table_rows = [{"项目": k, "内容": v} for k, v in kv_rows]
        row = _data_table(ws, row, table_headers, table_rows, spans=table_spans)
    else:
        table_headers = headers or []
        table_spans = spans or _distribute_spans(table_headers, ncols)
        row = _data_table(ws, row, table_headers, rows or [], spans=table_spans,
                          formulas=formulas, formats=formats)

    row = _section_row(ws, row, ncols, "四、审计说明")
    row = _audit_notes(ws, row, ncols, notes, companion)
    _apply_widths(ws)
    return row


# ------------------------------------------------------------ 各表公式定义


def _tie_formulas(header, r, data, cols):
    if header == "差异" and _is_number(data.get("金额一")) and _is_number(data.get("金额二")) \
            and data.get("差异") is not None:
        return f"={cols['金额一']}{r}-{cols['金额二']}{r}"
    return None


def _structure_formulas(header, r, data, cols):
    base_c = data.get("基准本期金额")
    base_p = data.get("基准上期金额")
    if header == "本期占比" and _is_number(data.get("本期金额")) and _is_number(base_c) and base_c:
        return f"={cols['本期金额']}{r}/{cols['基准本期金额']}{r}"
    if header == "上期占比" and _is_number(data.get("上期金额")) and _is_number(base_p) and base_p:
        return f"={cols['上期金额']}{r}/{cols['基准上期金额']}{r}"
    if header == "占比变动(百分点)" and data.get("本期占比") is not None and data.get("上期占比") is not None:
        return f"=({cols['本期占比']}{r}-{cols['上期占比']}{r})*100"
    if header == "金额变动" and _is_number(data.get("本期金额")) and _is_number(data.get("上期金额")):
        return f"={cols['本期金额']}{r}-{cols['上期金额']}{r}"
    return None


def _trend_formulas(header, r, data, cols):
    if header == "变动额" and _is_number(data.get("本期金额")) and _is_number(data.get("上期金额")):
        return f"={cols['本期金额']}{r}-{cols['上期金额']}{r}"
    if header == "变动率" and _is_number(data.get("本期金额")) and _is_number(data.get("上期金额")) \
            and data["上期金额"] > 0:
        return f"={cols['变动额']}{r}/{cols['上期金额']}{r}"
    return None


def _ratio_formulas(header, r, data, cols):
    if header == "变动" and _is_number(data.get("本期")) and _is_number(data.get("上期")):
        return f"={cols['本期']}{r}-{cols['上期']}{r}"
    return None


def _expectation_formulas(header, r, data, cols):
    if header == "差异" and _is_number(data.get("本期实际")) and _is_number(data.get("期望值")):
        return f"={cols['本期实际']}{r}-{cols['期望值']}{r}"
    if header == "差异率" and _is_number(data.get("期望值")) and data["期望值"] != 0 \
            and _is_number(data.get("差异")):
        return f"={cols['差异']}{r}/ABS({cols['期望值']}{r})"
    return None


def _exception_formulas(header, r, data, cols):
    if header == "差异" and _is_number(data.get("本期")) and _is_number(data.get("上期")):
        return f"={cols['本期']}{r}-{cols['上期']}{r}"
    return None


def _industry_formulas(header, r, data, cols):
    if header == "偏离程度":
        return (f'=IF({cols["行业中位数"]}{r}="","",'
                f'{cols["本被审计单位本期"]}{r}-{cols["行业中位数"]}{r})')
    return None


def _industry_formats(header, row):
    unit = row.get("单位")
    if header in ("本被审计单位本期", "本被审计单位上期", "行业中位数",
                  "行业上四分位", "行业下四分位", "偏离程度"):
        if unit == "%":
            return PERCENT_FMT
        if unit in ("倍", "次", "天"):
            return NUMBER_FMT
    return cell_format(header, row)


# ------------------------------------------------------------ Excel 主入口


def write_excel(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True

    meta = result.meta
    entity = meta.get("entity") or "（待填）"
    period = meta.get("period") or "（待填）"
    companion = f"{path.stem}-修订记录.md"

    materiality_text = (f"{meta.get('materiality'):,.2f} 元" if meta.get("materiality")
                        else "未提供")

    # ---------------- 说明与参数 ----------------
    ws = wb.active
    ws.title = sheet_name(1)
    params = [
        ("被审计单位", entity),
        ("期间", period),
        ("输入文件", meta.get("input")),
        ("生成时间", meta.get("run_time")),
        ("程序版本", cfg.VERSION),
        ("索引号", sheet_index(1)),
        ("整体重要性水平", materiality_text),
        ("重要性水平来源", meta.get("materiality_source", "")),
        ("可容忍差异比例", f"{cfg.DEFAULT_CONFIG['tolerable_ratio_of_materiality']:.0%} × 重要性水平"),
        ("容差率", "收入/成本 5%，费用 8%，资产负债 10%"),
        ("结构分析阈值",
         f"占比变动 ≥ {cfg.DEFAULT_CONFIG['structure_pp_threshold']:.0f} 个百分点且金额达到重要性水平 30%"),
        ("两年对比阈值", "资产负债表 30%、利润表 20%、现金流量表 30%，且金额达到重要性水平 30%"),
        ("异常分级", "L1 提示 / L2 需解释 / L3 高风险"),
        ("行业对比", "本版本不内置行业数据，相关列由使用人填列"),
        ("单位", "元"),
    ]
    _compose_sheet(
        ws, index=sheet_index(1), title="分析程序说明与参数表",
        subtitle=f"{sheet_index(1)}　分析程序底稿（通用辅助类）　认定：CEAVP",
        entity=entity, period=period,
        objective="说明本底稿的编制依据、数据来源、重要性水平与阈值口径，便于复核与追溯。",
        procedures=[
            ("列示底稿编制依据、数据来源、重要性水平与阈值口径。", "A", "见第三部分参数表"),
            ("说明分析程序的适用范围与能力边界（两期对比）。", "A", "见第三部分参数表"),
        ],
        notes=[
            "本表由分析程序自动生成，金额单位为元；如原始报表以千元或万元填列，程序已统一换算。",
            "重要参数（重要性水平、期间、被审计单位）由使用人确认后生效。",
            "结论栏一律留空，由项目组填写；程序不代写审计结论。",
        ],
        layout_cols=12, companion=companion, kv_rows=params,
        red_note="说明：本工作簿由分析程序生成，结论与定性由项目组作出；如与人工底稿不一致，以人工复核结论为准。",
    )

    # ---------------- 数据校验 ----------------
    ws = wb.create_sheet(sheet_name(2))
    headers = ["检查项", "项目", "金额一", "金额二", "差异", "容忍额", "结论", "说明"]
    _compose_sheet(
        ws, index=sheet_index(2), title="数据校验底稿",
        subtitle=f"{sheet_index(2)}　数据校验（勾稽 / 单位 / 映射）　认定：C、E",
        entity=entity, period=period,
        objective="验证四张报表内部与相互之间的勾稽关系，以及金额单位与科目映射的完整性，为后续分析提供可靠数据基础。",
        procedures=[
            ("核对报表内部勾稽关系（资产=负债+权益、利润表勾稽、现金流量表勾稽）。", "C、E", "见第三部分"),
            ("核对表间勾稽关系（权益变动表与利润表净利润）。", "C、E", "见第三部分"),
            ("检查金额单位识别与科目映射完整性，未映射项目单独列示。", "C", "见第三部分"),
        ],
        notes=[
            "差异 = 金额一 − 金额二，由表内公式计算；结论按容忍额自动判定为通过 / 注意 / 不符。",
            "容忍额按重要性水平的 1% 与最小 1 元取高者，用于容忍四舍五入与单位进位。",
            "结论为“注意”或“不符”的项目，应查明原因并在人工结论栏说明。",
        ],
        layout_cols=12, companion=companion,
        headers=headers, rows=result.validation, formulas=_tie_formulas,
    )

    # ---------------- 结构分析 ----------------
    ws = wb.create_sheet(sheet_name(3))
    headers = ["报表", "项目", "本期金额", "上期金额", "本期占比", "上期占比",
               "占比变动(百分点)", "金额变动", "是否关注", "基准", "基准本期金额", "基准上期金额"]
    _compose_sheet(
        ws, index=sheet_index(3), title="结构分析底稿",
        subtitle=f"{sheet_index(3)}　结构分析（占总额比重及两期变动）　认定：A",
        entity=entity, period=period,
        objective="分析各报表项目占总额的比重及两期结构变动，识别结构性异常。",
        procedures=[
            ("计算各项目占总额的比重（资产负债表按资产总计、利润表按营业收入）。", "A", "见第三部分"),
            ("比较两期占比变动（百分点），结合金额变动判断是否关注。", "A", "见第三部分"),
        ],
        notes=[
            "本期占比 = 本期金额 ÷ 基准本期金额；上期占比 = 上期金额 ÷ 基准上期金额；占比变动 = (本期占比 − 上期占比) × 100，均为表内公式。",
            f"占比变动 ≥ {cfg.DEFAULT_CONFIG['structure_pp_threshold']:.0f} 个百分点且金额变动达到重要性水平 30% 时标注“关注”。",
            "汇总数与现金余额类项目不单独提示，其变动由明细项目与业务实质决定。",
        ],
        layout_cols=12, companion=companion,
        headers=headers, rows=result.structure, formulas=_structure_formulas,
    )

    # ---------------- 两年对比 ----------------
    ws = wb.create_sheet(sheet_name(4))
    headers = ["报表", "项目", "上期金额", "本期金额", "变动额", "变动率", "是否关注", "备注"]
    _compose_sheet(
        ws, index=sheet_index(4), title="两年对比底稿",
        subtitle=f"{sheet_index(4)}　两年对比（变动额与变动率）　认定：A、E",
        entity=entity, period=period,
        objective="比较各项目本期与上期的变动额与变动率，识别重大波动并追溯原因。",
        procedures=[
            ("计算各项目本期较上期的变动额与变动率。", "E", "见第三部分"),
            ("对超过阈值且金额重大的项目标注“关注”，进入异常汇总。", "A", "见第三部分"),
        ],
        notes=[
            "变动额 = 本期金额 − 上期金额；变动率 = 变动额 ÷ 上期金额，均为表内公式。",
            "上期金额为零或为负时，变动率在数学上不成立或无意义，一律标注“变动率不适用”，改按绝对额变动判断。",
            "本版本仅两期数据，未执行时间序列统计离群分析，以变动率法与结构变动法替代。",
        ],
        layout_cols=12, companion=companion,
        headers=headers, rows=result.trend, formulas=_trend_formulas,
    )

    # ---------------- 比率分析 ----------------
    ws = wb.create_sheet(sheet_name(5))
    headers = ["分组", "指标", "本期", "上期", "变动", "单位", "方向", "备注"]
    _compose_sheet(
        ws, index=sheet_index(5), title="财务比率分析底稿",
        subtitle=f"{sheet_index(5)}　比率分析（五组比率 + 杜邦分解）　认定：A",
        entity=entity, period=period,
        objective="计算偿债能力、营运能力、盈利能力、现金流质量与成长性比率并作杜邦分解，评价被审计单位的财务表现与变动趋势。",
        procedures=[
            ("计算偿债能力、营运能力、盈利能力、现金流质量与成长性比率。", "A", "见第三部分"),
            ("执行杜邦分解，验证净资产收益率与净利率、总资产周转率、权益乘数的恒等关系。", "A", "见第三部分"),
            ("按单位标注比率格式（%、倍、次、天），周转率采用两期平均余额。", "E", "见第三部分"),
        ],
        notes=[
            "变动 = 本期 − 上期，由表内公式计算；方向判断为参考，不构成审计结论。",
            "周转类比率本期采用两期平均余额，上期因缺少上上期数据按期末余额计算，口径差异已在备注列说明。",
            "分母为零或缺少相关项目时，比率标记“无法计算”，并已注明原因。",
        ],
        layout_cols=12, companion=companion,
        headers=headers, rows=result.ratios, formulas=_ratio_formulas,
    )

    # ---------------- 期望值模型 ----------------
    ws = wb.create_sheet(sheet_name(6))
    headers = ["报表", "项目", "模型", "驱动关系", "驱动因子", "上期金额", "本期实际", "期望值",
               "差异", "差异率", "可容忍差异", "分级", "方向判断", "模型置信度", "备注",
               "可能成因", "建议程序", "人工结论"]
    _compose_sheet(
        ws, index=sheet_index(6), title="期望值分析底稿",
        subtitle=f"{sheet_index(6)}　期望值模型（业务驱动关系测算）　认定：A、E",
        entity=entity, period=period,
        objective="按业务驱动关系测算各项目的期望值，与实际数比较并评价差异，识别偏离预期的项目。",
        procedures=[
            ("按收入、成本、费用与业务量驱动关系测算期望值。", "A", "见第三部分"),
            ("计算差异与差异率，并与可容忍差异比较后分级。", "E", "见第三部分"),
            ("对低置信度模型封顶等级为 L2，避免过度定级。", "A", "见第三部分"),
        ],
        notes=[
            "差异 = 本期实际 − 期望值；差异率 = 差异 ÷ |期望值|，均为表内公式。",
            "可容忍差异 = max（重要性水平 × 50%，|期望值| × 容差率）；容差率收入成本 5%、费用 8%、资产负债 10%。",
            "期望值模型依赖驱动关系假设，置信度为“低”的模型已封顶为 L2；测算结果仅供参考。",
            "“可能成因”“建议程序”为线索与建议，“人工结论”栏留空由项目组填写。",
        ],
        layout_cols=18, companion=companion,
        headers=headers, rows=result.expectation, formulas=_expectation_formulas,
    )

    # ---------------- 一致性检查 ----------------
    ws = wb.create_sheet(sheet_name(7))
    headers = ["检查项", "判断依据", "触发阈值", "实际值", "是否触发", "说明",
               "可能成因", "建议程序", "人工结论"]
    _compose_sheet(
        ws, index=sheet_index(7), title="一致性检查底稿",
        subtitle=f"{sheet_index(7)}　跨科目一致性检查　认定：A、C",
        entity=entity, period=period,
        objective="识别科目之间相互矛盾或不匹配的变动关系，发现可能与错报或舞弊相关的迹象。",
        procedures=[
            ("检查收入与应收账款、利润与经营现金流、存货与收入等匹配关系。", "A、C", "见第三部分"),
            ("检查毛利率、资产负债率、收现比与周转天数等的异常变动。", "A", "见第三部分"),
        ],
        notes=[
            "“实际值”为触发指标的计算结果，单位随检查项不同（百分点、倍等），已在判断依据中说明。",
            "是否触发按阈值自动判定；触发项进入异常汇总，等级为 L2 需解释。",
            "一致性检查仅提示矛盾现象，具体原因需向被审计单位询问并取得支持性资料。",
        ],
        layout_cols=12, companion=companion,
        headers=headers, rows=result.consistency,
    )

    # ---------------- 异常汇总 ----------------
    ws = wb.create_sheet(sheet_name(8))
    headers = ["编号", "等级", "来源", "报表", "项目/指标", "本期", "上期", "差异",
               "判定依据", "可能成因", "建议程序", "人工结论"]
    _compose_sheet(
        ws, index=sheet_index(8), title="异常事项汇总底稿",
        subtitle=f"{sheet_index(8)}　异常汇总（L1/L2/L3 分级）　认定：CEAVP",
        entity=entity, period=period,
        objective="汇总全部异常事项，标注等级、来源、判定依据、可能成因与建议程序，供项目组判断与记录结论。",
        procedures=[
            ("合并结构分析、两年对比、期望值模型与一致性检查的异常事项。", "CEAVP", "见第三部分"),
            ("按项目去重并保留最高等级，按 L3→L2→L1 排序。", "CEAVP", "见第三部分"),
        ],
        notes=[
            "等级表示关注强度，不是审计结论：L1 提示 / L2 需解释 / L3 高风险。",
            "差异 = 本期 − 上期，由表内公式计算；同一项目在多处触发时已合并保留最高等级。",
            "可能成因与建议程序为线索与建议，人工结论栏一律留空由项目组填写。",
        ],
        layout_cols=12, companion=companion,
        headers=headers, rows=result.exceptions, formulas=_exception_formulas,
    )

    # ---------------- 未映射清单 ----------------
    ws = wb.create_sheet(sheet_name(9))
    unmapped_rows = [{"报表": s, "未映射项目": raw} for s, raw in result.unmapped]
    _compose_sheet(
        ws, index=sheet_index(9), title="未映射项目清单",
        subtitle=f"{sheet_index(9)}　未映射项目（需人工确认）　认定：C",
        entity=entity, period=period,
        objective="完整列示未能自动映射到标准科目的报表项目，供人工确认对应关系，避免静默丢弃。",
        procedures=[
            ("列示各报表中未识别的项目名称。", "C", "见第三部分"),
            ("人工确认对应关系后，更新科目映射规则或标注“无需参与分析”。", "C", "人工执行"),
        ],
        notes=[
            "未映射项目不做静默丢弃，全部在此列示；未确认前，相关项目不参与比率与期望值测算。",
            "确认为同一项目的别名时，可在 rules/01-科目映射.md 中补充后重新运行。",
        ],
        layout_cols=12, companion=companion,
        headers=["报表", "未映射项目"], rows=unmapped_rows,
    )

    # ---------------- 行业对比（待填） ----------------
    ws = wb.create_sheet(sheet_name(10))
    industry_rows = []
    for row in result.ratios:
        industry_rows.append({
            "分组": row["分组"], "指标": row["指标"], "单位": row["单位"],
            "本被审计单位本期": row["本期"], "本被审计单位上期": row["上期"],
            "行业中位数": None, "行业上四分位": None, "行业下四分位": None,
            "偏离程度": None, "数据来源与年份": "",
        })
    _compose_sheet(
        ws, index=sheet_index(10), title="行业对比表（使用人填列）",
        subtitle=f"{sheet_index(10)}　行业/同行业比率对照　认定：A",
        entity=entity, period=period,
        objective="预留行业中位数与四分位列，由使用人从所内数据库或公开来源取得行业比率后填列，作为异常判定的对照基准。",
        procedures=[
            ("从所内数据库或公开来源取得行业比率并注明来源与年份。", "A", "人工执行"),
            ("填列行业中位数与四分位后，表内自动计算偏离程度。", "A", "人工执行"),
        ],
        notes=[
            "本版本不内置行业数据，本表相关列由使用人填列；未填列时偏离程度显示为空白。",
            "偏离程度 = 本被审计单位本期 − 行业中位数（表内公式），应结合行业口径与年份可比性解读。",
            "行业数据来源与年份必须注明，作为底稿可追溯性的一部分。",
        ],
        layout_cols=12, companion=companion,
        headers=["分组", "指标", "单位", "本被审计单位本期", "本被审计单位上期",
                 "行业中位数", "行业上四分位", "行业下四分位", "偏离程度", "数据来源与年份"],
        rows=industry_rows, formulas=_industry_formulas, formats=_industry_formats,
    )

    # ---------------- 图表 ----------------
    ws = wb.create_sheet(sheet_name(11))
    _chart_sheet(ws, result, index=sheet_index(11), entity=entity, period=period,
                 companion=companion)

    for sheet in wb.worksheets:
        _setup_print(sheet)
    wb.save(path)
    return path


def _chart_sheet(ws, result: AnalysisResult, *, index, entity, period, companion):
    ncols = 12
    _title_block(ws, "关键项目两期对比图", f"{index}　图表（数据区与对比图）　认定：A", ncols)
    row = 4
    row = _section_row(ws, row, ncols, "一、项目基本信息")
    row = _info_block(ws, row, ncols, entity, period, index)
    row = _section_row(ws, row, ncols, "二、审计目标和程序说明")
    row = _objective_row(ws, row, ncols, "以图表呈现收入、成本、利润与资产、负债、权益等关键项目的两期对比，便于复核人员快速把握总体变动。")
    row = _procedure_table(ws, row, ncols, [
        ("选取收入、成本、净利润与资产、负债、所有者权益、货币资金、应收账款、存货等关键项目。", "A", "见第三部分"),
        ("按上期与本期的绝对额绘制柱状图，数据区保留明细金额。", "E", "见第三部分"),
    ])
    row = _section_row(ws, row, ncols, "三、审计程序执行结果")

    data = result.meta.get("chart_data", {})

    income_header = row
    row = _data_table(ws, row, ["项目", "上期金额", "本期金额"],
                      [{"项目": n, "上期金额": p, "本期金额": c} for n, p, c in data.get("income", [])],
                      spans=[1, 1, 1])
    row += 1
    balance_header = row
    row = _data_table(ws, row, ["项目", "上期金额", "本期金额"],
                      [{"项目": n, "上期金额": p, "本期金额": c} for n, p, c in data.get("balance", [])],
                      spans=[1, 1, 1])
    row += 1

    income_rows = len(data.get("income", []))
    if income_rows:
        chart = BarChart()
        chart.type = "col"
        chart.title = "收入、成本与净利润两期对比"
        chart.y_axis.title = "元"
        chart.x_axis.title = "项目"
        ref = Reference(ws, min_col=2, max_col=3, min_row=income_header, max_row=income_header + income_rows)
        cats = Reference(ws, min_col=1, min_row=income_header + 1, max_row=income_header + income_rows)
        chart.add_data(ref, titles_from_data=True)
        chart.set_categories(cats)
        chart.height, chart.width = 8, 18
        ws.add_chart(chart, f"A{row}")
        row += 18

    balance_rows = len(data.get("balance", []))
    if balance_rows:
        chart2 = BarChart()
        chart2.type = "col"
        chart2.title = "资产、负债与所有者权益等两期对比"
        chart2.y_axis.title = "元"
        chart2.x_axis.title = "项目"
        ref2 = Reference(ws, min_col=2, max_col=3, min_row=balance_header, max_row=balance_header + balance_rows)
        cats2 = Reference(ws, min_col=1, min_row=balance_header + 1, max_row=balance_header + balance_rows)
        chart2.add_data(ref2, titles_from_data=True)
        chart2.set_categories(cats2)
        chart2.height, chart2.width = 8, 18
        ws.add_chart(chart2, f"A{row}")
        row += 18

    row = _section_row(ws, row, ncols, "四、审计说明")
    _audit_notes(ws, row, ncols, [
        "图表数据来源于本工作簿的结构分析与两年对比结果，金额单位为元。",
        "图表仅用于呈现总体变动趋势，不能替代明细核对与支持性证据。",
    ], companion)

    _register_width(ws, 1, 30)
    _register_width(ws, 2, 18)
    _register_width(ws, 3, 18)
    _apply_widths(ws)


# ------------------------------------------------------------------ CSV 与日志


def write_exception_csv(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    headers = ["编号", "等级", "来源", "报表", "项目/指标", "本期", "上期", "差异",
               "判定依据", "可能成因", "建议程序", "人工结论"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in result.exceptions:
            writer.writerow(row)
    return path


def write_log(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    lines = [
        f"财务报表分析程序 运行日志  版本 {cfg.VERSION}",
        f"运行时间：{result.meta.get('run_time')}",
        f"输入文件：{result.meta.get('input')}",
        f"被审计单位：{result.meta.get('entity') or '(未提供)'}",
        f"期间：{result.meta.get('period') or '(未提供)'}",
        f"重要性水平：{result.meta.get('materiality')}（{result.meta.get('materiality_source')}）",
        "",
        "── 处理统计 ──",
        f"数据校验条目：{len(result.validation)}",
        f"结构分析条目：{len(result.structure)}",
        f"两年对比条目：{len(result.trend)}",
        f"比率指标：{len(result.ratios)}",
        f"期望值模型：{len(result.expectation)}",
        f"一致性检查：{len(result.consistency)}",
        f"异常合计：{len(result.exceptions)}",
        f"未映射项目：{len(result.unmapped)}",
        "",
        "── 提示与警告 ──",
    ]
    if result.warnings:
        lines.extend(f"- {w}" for w in result.warnings)
    else:
        lines.append("- 无")
    lines.extend(["", "── 未映射项目 ──"])
    if result.unmapped:
        lines.extend(f"- [{s}] {raw}" for s, raw in result.unmapped)
    else:
        lines.append("- 无")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_revision_log(result: AnalysisResult, path: str | Path, workbook_name: str) -> Path:
    """生成与工作簿同路径的修订记录 md（底稿制式要求）。"""
    path = Path(path)
    meta = result.meta
    lines = [
        f"# {workbook_name} 修订记录",
        "",
        f"- 索引号：{INDEX_PREFIX}（工作簿级）",
        f"- 被审计单位：{meta.get('entity') or '（待填）'}",
        f"- 期间：{meta.get('period') or '（待填）'}",
        "",
        "| 版本 | 日期 | 编制/修订人 | 修订内容 |",
        "| --- | --- | --- | --- |",
        f"| {cfg.VERSION} | {datetime.now().strftime('%Y-%m-%d')} | 分析程序自动生成 | "
        f"首次生成分析程序底稿（输入：{meta.get('input')}） |",
        "",
        "> 说明：本文件为工作簿的修订记录伴随文件，预览与修订登记使用；正式交付以同路径 .xlsx 为准。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------ Word


def _set_run_font(run, size=10.5, bold=False, color=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = FONT_NAME
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), FONT_NAME)
    rfonts.set(qn("w:ascii"), FONT_NAME)
    rfonts.set(qn("w:hAnsi"), FONT_NAME)


def _shade_paragraph(para, fill):
    ppr = para._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


def _shade_cell(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _add_para(doc, text, size=10.5, bold=False, align=None, space_after=6, color=None):
    para = doc.add_paragraph()
    if align is not None:
        para.alignment = align
    para.paragraph_format.space_after = Pt(space_after)
    run = para.add_run(text)
    _set_run_font(run, size=size, bold=bold, color=color)
    return para


def _add_heading(doc, text):
    """节标题：12pt 加粗 + E8E8E8 底纹，与 Excel 制式一致。"""
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(10)
    para.paragraph_format.space_after = Pt(4)
    run = para.add_run(text)
    _set_run_font(run, size=12, bold=True)
    _shade_paragraph(para, "E8E8E8")
    return para


def _set_cell(cell, text, *, size=9, bold=False, align=None, shade=None):
    cell.text = ""
    para = cell.paragraphs[0]
    if align is not None:
        para.alignment = align
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(1)
    run = para.add_run("" if text is None else str(text))
    _set_run_font(run, size=size, bold=bold)
    if shade:
        _shade_cell(cell, shade)


def _word_table(doc, headers, rows, *, widths=None, max_rows=None, font_size=9):
    data = rows[:max_rows] if max_rows else rows
    table = doc.add_table(rows=1 + len(data), cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for i, header in enumerate(headers):
        _set_cell(table.rows[0].cells[i], header, size=font_size, bold=True,
                  align=WD_ALIGN_PARAGRAPH.CENTER, shade="D9D9D9")
    for r, data_row in enumerate(data, start=1):
        for i, header in enumerate(headers):
            value = data_row.get(header)
            align = WD_ALIGN_PARAGRAPH.RIGHT if _is_number(value) else WD_ALIGN_PARAGRAPH.LEFT
            _set_cell(table.rows[r].cells[i], fmt_cell(value, header, data_row),
                      size=font_size, align=align)
    if widths:
        for table_row in table.rows:
            for i, width in enumerate(widths):
                if i < len(table_row.cells):
                    table_row.cells[i].width = Cm(width)
    _style_table_rows(table)
    return table


def _style_table_rows(table, repeat_header=True):
    """行不断页；首行为重复表头，跨页时自动重现。"""
    for i, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        tr_pr.append(OxmlElement("w:cantSplit"))
        if i == 0 and repeat_header:
            header = OxmlElement("w:tblHeader")
            header.set(qn("w:val"), "true")
            tr_pr.append(header)


def _word_info_table(doc, pairs, widths):
    """一、项目基本信息：两对一行的四列表。"""
    rows = [pairs[i:i + 2] for i in range(0, len(pairs), 2)]
    table = doc.add_table(rows=len(rows), cols=4)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for r, pair in enumerate(rows):
        for c, (label, value) in enumerate(pair):
            _set_cell(table.rows[r].cells[c * 2], label, size=9, bold=True,
                      align=WD_ALIGN_PARAGRAPH.LEFT, shade="F2F2F2")
            _set_cell(table.rows[r].cells[c * 2 + 1], value, size=9,
                      align=WD_ALIGN_PARAGRAPH.LEFT)
    for table_row in table.rows:
        for i, width in enumerate(widths):
            table_row.cells[i].width = Cm(width)
    _style_table_rows(table, repeat_header=False)
    return table


def _add_footer(section, text):
    para = section.footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run(f"{text}　　第 ")
    _set_run_font(run, size=8, color="808080")
    run2 = para.add_run()
    _set_run_font(run2, size=8, color="808080")
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run2._r.append(begin)
    run2._r.append(instr)
    run2._r.append(end)
    run3 = para.add_run(" 页")
    _set_run_font(run3, size=8, color="808080")


def write_word(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)

    meta = result.meta
    entity = meta.get("entity") or "＿＿＿＿＿＿＿＿"
    period = meta.get("period") or "＿＿＿＿＿＿"
    materiality_text = (f"{meta.get('materiality'):,.2f} 元" if meta.get("materiality")
                        else "未提供（待项目组确认）")
    companion = f"{path.stem.replace('-分析底稿', '')}-修订记录.md"

    # 页面：A4 纵向，页边距与表格宽度（≤17cm）匹配，便于打印归档
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.0)
    doc.core_properties.title = "财务报表分析程序底稿"
    doc.core_properties.subject = f"索引号 {INDEX_PREFIX}｜{entity}｜{period}"
    doc.core_properties.category = "审计底稿（分析程序）"

    # 标题区
    _add_para(doc, "财务报表分析程序底稿", size=18, bold=True,
              align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    _add_para(doc,
              f"索引号：{INDEX_PREFIX}　|　被审计单位：{entity}　|　期间：{period}　|　生成时间：{meta.get('run_time')}",
              size=9, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10, color="666666")

    # 一、项目基本信息
    _add_heading(doc, "一、项目基本信息")
    _word_info_table(doc, [
        ("被审计单位", entity),
        ("审计期间", period),
        ("索引号", f"{INDEX_PREFIX}（工作簿级）"),
        ("整体重要性水平", materiality_text),
        ("编制人", ""),
        ("编制日期", ""),
        ("审核人", ""),
        ("审核日期", ""),
    ], widths=[2.6, 5.4, 2.6, 5.3])

    # 二、分析目的与依据
    _add_heading(doc, "二、分析目的与依据")
    _add_para(doc, "根据《中国注册会计师审计准则第1313号——分析程序》的要求，本底稿记录对财务报表实施分析程序的过程与结果，"
                   "用于识别异常或偏离预期的关系，并据以确定进一步审计程序的性质、时间与范围。")
    _add_para(doc, "本底稿由分析程序辅助工具生成计算与比对结果；可能成因与建议程序为线索，不构成审计结论。"
                   "所有差异的定性、结论与后续程序由项目组作出。")

    # 三、数据来源与口径说明
    _add_heading(doc, "三、数据来源与口径说明")
    _add_para(doc, f"数据来源：{meta.get('input')}；生成时间：{meta.get('run_time')}。金额单位为元，"
                   "如原始报表以千元或万元填列，程序已统一换算并记录在实际识别单位中。")
    if meta.get("materiality"):
        _add_para(doc, f"整体重要性水平：{meta.get('materiality'):,.2f} 元（{meta.get('materiality_source')}）。"
                       f"可容忍差异按重要性水平的 {cfg.DEFAULT_CONFIG['tolerable_ratio_of_materiality']:.0%} 与"
                       f"期望值容差率（收入成本 5%、费用 8%、资产负债 10%）中的较高者确定。")
    else:
        _add_para(doc, "整体重要性水平：未提供，相关比较阈值参考建议值，待项目组确认。")
    _add_para(doc, "本版本仅使用本期与上期两期数据。因缺少更长期间，未执行时间序列统计离群分析，"
                   "改以变动率法、结构变动法与跨科目一致性检查替代。")

    # 四、执行的程序
    _add_heading(doc, "四、执行的程序")
    for text in [
        "1. 数据校验：报表内部与表间勾稽关系核对、金额单位与科目映射检查。",
        "2. 结构分析：各项目占总额（资产负债表按资产总计、利润表按营业收入）的比重及两期变动。",
        "3. 两年对比：各项目本期与上期的变动额与变动率分析。",
        "4. 比率分析：偿债能力、营运能力、盈利能力、现金流质量与成长性比率，并作杜邦分解。",
        "5. 期望值分析：按业务驱动关系测算期望值，与实际数比较并评价差异。",
        "6. 一致性检查：识别科目之间互相矛盾的现象。",
    ]:
        _add_para(doc, text, size=10.5, space_after=3)

    # 五、数据校验结果
    _add_heading(doc, "五、数据校验结果")
    problem_rows = [r for r in result.validation if r.get("结论") in ("注意", "不符", "无法执行")]
    if problem_rows:
        _word_table(doc, ["检查项", "项目", "金额一", "金额二", "差异", "结论", "说明"],
                    problem_rows, widths=[2.0, 3.6, 1.9, 1.9, 1.9, 1.3, 3.3])
    else:
        _add_para(doc, "各项勾稽检查通过，未发现勾稽差异。")
    if result.unmapped:
        _add_para(doc, f"另有 {len(result.unmapped)} 个报表项目未能自动映射到标准科目，"
                       "已列入 Excel 工作簿「未映射清单」，需人工确认对应关系。", size=10)

    # 六、主要财务比率
    _add_heading(doc, "六、主要财务比率")
    _word_table(doc, ["分组", "指标", "本期", "上期", "变动", "单位", "方向", "备注"],
                result.ratios, widths=[1.7, 3.3, 1.7, 1.7, 1.7, 0.9, 1.1, 3.7])

    # 七、异常事项汇总
    _add_heading(doc, "七、异常事项汇总")
    _add_para(doc, f"共识别异常 {len(result.exceptions)} 项，其中 L3 高风险 "
                   f"{sum(1 for r in result.exceptions if r['等级'].startswith('L3'))} 项，L2 需解释 "
                   f"{sum(1 for r in result.exceptions if r['等级'].startswith('L2'))} 项，L1 提示 "
                   f"{sum(1 for r in result.exceptions if r['等级'].startswith('L1'))} 项。")
    if result.exceptions:
        _word_table(doc, ["编号", "等级", "来源", "报表", "项目/指标", "本期", "上期", "差异",
                          "判定依据", "人工结论"],
                    result.exceptions,
                    widths=[1.0, 1.2, 1.4, 1.1, 1.9, 1.4, 1.4, 1.4, 2.7, 1.4])
    else:
        _add_para(doc, "未识别出达到关注标准的异常事项。")

    # 八、待向被审计单位询问的问题
    _add_heading(doc, "八、待向被审计单位询问的问题")
    questions = _build_questions(result)
    if questions:
        for i, q in enumerate(questions, start=1):
            _add_para(doc, f"{i}. {q}", size=10.5, space_after=3)
    else:
        _add_para(doc, "无。")

    # 九、分析结论
    _add_heading(doc, "九、分析结论")
    _add_para(doc, "（以下由项目组填写，程序不代写结论）", size=9, color="808080")
    for label in ["1. 分析程序结果显示的异常或不一致关系：", "2. 对差异的解释及已获取的支持性证据：",
                  "3. 对进一步审计程序的性质、时间与范围的影响：", "4. 对风险评估结论的影响："]:
        _add_para(doc, label, size=10.5, space_after=2)
        _add_para(doc, "　", size=10.5, space_after=2)
        _add_para(doc, "　", size=10.5, space_after=6)

    # 十、复核记录
    _add_heading(doc, "十、复核记录")
    table = doc.add_table(rows=3, cols=3)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    labels = [["编制人", "日期", "签字"], ["复核人", "日期", "签字"], ["项目合伙人", "日期", "签字"]]
    for r, label_row in enumerate(labels):
        for c, text in enumerate(label_row):
            _set_cell(table.rows[r].cells[c], text, size=9, bold=(c == 0),
                      align=WD_ALIGN_PARAGRAPH.CENTER, shade=("F2F2F2" if c == 0 else None))
    for table_row in table.rows:
        table_row.cells[0].width = Cm(3.0)
        table_row.cells[1].width = Cm(4.0)
        table_row.cells[2].width = Cm(8.9)
    _style_table_rows(table, repeat_header=False)

    _add_para(doc, f"注：本底稿由分析程序自动生成，同路径伴随《{companion}》，每次修订同步登记。",
              size=9, space_after=2, color="C00000")
    _add_footer(doc.sections[0], f"财务报表分析程序底稿 · 索引号 {INDEX_PREFIX}")

    doc.save(path)
    return path


def _build_questions(result: AnalysisResult) -> list[str]:
    questions = []
    for row in result.exceptions:
        if row["等级"].startswith("L1"):
            continue
        item = row.get("项目/指标")
        sources = row.get("来源", "")
        current = row.get("本期")
        diff = row.get("差异")
        if "期望值模型" in sources and _is_number(diff) and _is_number(current):
            questions.append(
                f"关于【{item}】，本期实际数为 {current:,.2f} 元，与按业务关系测算的期望值相差"
                f" {diff:,.2f} 元，请说明原因并提供支持性资料（如合同、明细表、业务量数据）。"
            )
        elif "一致性检查" in sources:
            questions.append(
                f"关于【{item}】，分析显示相关科目之间存在不一致的变动关系，"
                "请说明业务原因并提供支持性资料。"
            )
        elif _is_number(diff):
            questions.append(
                f"关于【{item}】，本期较上期变动 {diff:,.2f} 元，请说明原因并提供支持性资料。"
            )
        else:
            questions.append(f"关于【{item}】，请说明变动原因并提供支持性资料。")
    return questions
