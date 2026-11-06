"""四张报表的读取、表头识别、单位换算与科目映射。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import profile

STATEMENT_ORDER = ["资产负债表", "利润表", "现金流量表", "所有者权益变动表"]


# ------------------------------------------------------------------ 数据类


@dataclass
class LineItem:
    statement: str
    row_no: int
    raw_name: str
    standard: str | None
    method: str
    current: float | None
    prior: float | None


@dataclass
class StatementData:
    name: str
    sheet: str
    unit: str = "元"
    unit_factor: float = 1.0
    items: list[LineItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    mapping: dict[str, LineItem] = field(default_factory=dict)

    def get(self, standard: str) -> tuple[float | None, float | None]:
        item = self.mapping.get(standard)
        if item is None:
            return (None, None)
        return (item.current, item.prior)

    @property
    def item_count(self) -> int:
        return len(self.items)


@dataclass
class ReportSet:
    statements: dict[str, StatementData] = field(default_factory=dict)
    source_path: str = ""
    warnings: list[str] = field(default_factory=list)

    def statement(self, name: str) -> StatementData | None:
        return self.statements.get(name)

    def get(self, statement: str, standard: str) -> tuple[float | None, float | None]:
        st = self.statements.get(statement)
        if st is None:
            return (None, None)
        return st.get(standard)

    def find(self, standard: str) -> tuple[float | None, float | None]:
        """在四张表中查找某标准项目，资产负债表优先。"""
        for name in STATEMENT_ORDER:
            st = self.statements.get(name)
            if st and standard in st.mapping:
                return st.get(standard)
        return (None, None)

    @property
    def all_unmapped(self) -> list[tuple[str, str]]:
        out = []
        for name, st in self.statements.items():
            for raw in st.unmapped:
                out.append((name, raw))
        return out


# ------------------------------------------------------------------ 工具函数


def parse_number(value) -> float | None:
    """解析金额，支持千分位、括号负数、破折号与文字混排。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            fv = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv

    text = str(value).strip()
    if text == "" or text.lower() in ("nan", "none", "null"):
        return None
    if text in ("-", "--", "—", "－", "/", "不适用", "N/A", "n/a", "无"):
        return None

    negative = False
    if (text.startswith("(") and text.endswith(")")) or (text.startswith("（") and text.endswith("）")):
        negative = True
        text = text[1:-1]
    if "(" in text or "（" in text:
        negative = True

    cleaned = re.sub(r"[,\s，、元]", "", text)
    cleaned = cleaned.replace("（", "(").replace("）", ")")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        val = float(match.group(0))
    except ValueError:
        return None
    return -val if negative else val


UNIT_PATTERN = re.compile(r"单位[:：]?\s*(万元|千元|元)")
UNIT_FACTOR = {"万元": 10000.0, "千元": 1000.0, "元": 1.0}

PERIOD_NOW = ("本期", "期末", "年末", "本年", "本年累计", "本期金额", "期末余额", "年末余额")
PERIOD_PREV = ("上期", "期初", "年初", "上年", "上年同期", "上期金额", "年初余额", "期初余额")
YEAR_PATTERN = re.compile(r"(20\d{2})")


def detect_unit(grid: list[list]) -> tuple[str, float]:
    for row in grid[:8]:
        for cell in row:
            if cell is None:
                continue
            text = str(cell)
            m = UNIT_PATTERN.search(text)
            if m:
                unit = m.group(1)
                return unit, UNIT_FACTOR[unit]
    return "元", 1.0


def _cell_text(grid: list[list], r: int, c: int) -> str:
    try:
        return profile.normalize_name(grid[r][c])
    except IndexError:
        return ""


def _is_item_header(text: str) -> bool:
    if not text:
        return False
    if "项目" in text or "科目" in text:
        return True
    return text in ("资产", "负债", "负债和所有者权益", "负债和股东权益", "所有者权益")


def _is_period_header(text: str) -> bool:
    if not text:
        return False
    if any(k in text for k in PERIOD_NOW + PERIOD_PREV):
        return True
    return bool(YEAR_PATTERN.search(text))


def _combined_headers(grid: list[list], header_row: int, ncols: int) -> list[str]:
    out = []
    for c in range(ncols):
        parts = []
        for r in range(max(0, header_row - 2), min(len(grid), header_row + 2)):
            parts.append(_cell_text(grid, r, c))
        out.append("".join(p for p in parts if p))
    return out


def _effective_periods(headers: list[str]) -> dict[int, object]:
    """处理跨列合并的期间表头。

    报表中的"本期金额"常只在第一列出现、向右合并若干列，导致后续列的表头为空。
    这里让每一列继承其左侧最近的期间标记；遇到新的期间标记则更新。
    """
    effective: dict[int, object] = {}
    last: object = None
    for c, text in enumerate(headers):
        if text:
            years = YEAR_PATTERN.findall(text)
            if any(k in text for k in PERIOD_NOW):
                last = "now"
            elif any(k in text for k in PERIOD_PREV):
                last = "prev"
            elif years:
                last = max(int(y) for y in years)
        if last is not None:
            effective[c] = last
    return effective


def _detect_header_row(grid: list[list]) -> int | None:
    nrows = len(grid)
    ncols = max((len(r) for r in grid), default=0)
    for r in range(min(nrows, 30)):
        row_has_item = any(_is_item_header(_cell_text(grid, r, c)) for c in range(ncols))
        if not row_has_item:
            continue
        window = range(max(0, r - 2), min(nrows, r + 2))
        row_has_period = any(
            _is_period_header(_cell_text(grid, rr, c))
            for rr in window
            for c in range(ncols)
        )
        if row_has_period:
            return r
    return None


def _pick_period_columns(headers: list[str], date_cols: list[int],
                         effective: dict[int, object]) -> tuple[int | None, int | None]:
    """从候选列中挑出本期列与上期列。"""
    if len(date_cols) == 1:
        return date_cols[0], None

    year_map = {c: effective[c] for c in date_cols if isinstance(effective.get(c), int)}

    if len(year_map) >= 2:
        ordered = sorted(year_map.items(), key=lambda kv: kv[1])
        prior_col = ordered[0][0]
        current_col = ordered[-1][0]
        return current_col, prior_col

    explicit_now = [c for c in date_cols if effective.get(c) == "now"]
    explicit_prev = [c for c in date_cols if effective.get(c) == "prev"]
    if explicit_now and explicit_prev:
        return explicit_now[0], explicit_prev[0]

    return date_cols[0], date_cols[1] if len(date_cols) > 1 else None


def _pick_equity_columns(headers: list[str], date_cols: list[int],
                         effective: dict[int, object]) -> tuple[int | None, int | None]:
    """所有者权益变动表：优先选择"所有者权益合计"列。"""
    total_cols = [c for c in date_cols if "所有者权益合计" in headers[c] or "股东权益合计" in headers[c]]
    if total_cols:
        current = [c for c in total_cols if effective.get(c) == "now"]
        prior = [c for c in total_cols if effective.get(c) == "prev"]
        if current and prior:
            return current[0], prior[0]
        year_map = {c: effective[c] for c in total_cols if isinstance(effective.get(c), int)}
        if len(year_map) >= 2:
            ordered = sorted(year_map.items(), key=lambda kv: kv[1])
            return ordered[-1][0], ordered[0][0]
        if len(total_cols) >= 2:
            return total_cols[0], total_cols[1]
        return total_cols[0], None

    now_cols = [c for c in date_cols if effective.get(c) == "now"]
    prev_cols = [c for c in date_cols if effective.get(c) == "prev"]
    if now_cols and prev_cols:
        return now_cols[-1], prev_cols[-1]
    return _pick_period_columns(headers, date_cols, effective)


# ------------------------------------------------------------------ 解析单张表


def parse_sheet(grid: list[list], statement_name: str, sheet_name: str) -> StatementData:
    unit, factor = detect_unit(grid)
    data = StatementData(name=statement_name, sheet=sheet_name, unit=unit, unit_factor=factor)

    header_row = _detect_header_row(grid)
    if header_row is None:
        data.warnings.append(
            f"未能在工作表「{sheet_name}」中识别表头，请确认存在项目列与本期/上期金额列"
        )
        return data

    ncols = max((len(r) for r in grid), default=0)
    headers = _combined_headers(grid, header_row, ncols)
    effective = _effective_periods(headers)
    row_headers = [_cell_text(grid, header_row, c) for c in range(ncols)]
    prev_headers = [_cell_text(grid, header_row - 1, c) if header_row > 0 else "" for c in range(ncols)]
    item_texts = [row_headers[c] or prev_headers[c] for c in range(ncols)]
    item_cols = [c for c in range(ncols) if _is_item_header(item_texts[c])]
    if not item_cols:
        item_cols = [0]

    blocks = []
    for idx, item_col in enumerate(item_cols):
        next_item = item_cols[idx + 1] if idx + 1 < len(item_cols) else ncols
        date_cols = [c for c in range(item_col + 1, next_item) if effective.get(c) is not None]
        if not date_cols:
            continue
        if statement_name == "所有者权益变动表":
            current_col, prior_col = _pick_equity_columns(headers, date_cols, effective)
        else:
            current_col, prior_col = _pick_period_columns(headers, date_cols, effective)
        if current_col is None:
            continue
        blocks.append((item_col, current_col, prior_col))

    if not blocks:
        data.warnings.append(f"工作表「{sheet_name}」未找到金额列，请检查表头格式")
        return data

    seen: dict[str, LineItem] = {}
    for r in range(header_row + 1, len(grid)):
        for item_col, current_col, prior_col in blocks:
            raw_name = _cell_text(grid, r, item_col)
            if profile.is_skip_row(raw_name):
                continue
            cur = parse_number(_cell_text(grid, r, current_col))
            prior = parse_number(_cell_text(grid, r, prior_col)) if prior_col is not None else None
            cur = cur * factor if cur is not None else None
            prior = prior * factor if prior is not None else None
            if cur is None and prior is None:
                continue

            standard, method = profile.resolve_item(raw_name)
            item = LineItem(
                statement=statement_name,
                row_no=r + 1,
                raw_name=str(grid[r][item_col]).strip() if item_col < len(grid[r]) else raw_name,
                standard=standard,
                method=method,
                current=cur,
                prior=prior,
            )
            data.items.append(item)

            if standard is None:
                if raw_name not in data.unmapped:
                    data.unmapped.append(raw_name)
                continue
            if standard in seen:
                prev = seen[standard]
                if prev.raw_name != item.raw_name:
                    data.conflicts.append(
                        f"「{prev.raw_name}」(第{prev.row_no}行) 与 「{item.raw_name}」(第{item.row_no}行) 均映射为「{standard}」，保留前者，需人工确认"
                    )
                continue
            seen[standard] = item

    data.mapping = seen
    return data


# ------------------------------------------------------------------ 主入口


def _match_sheet(sheet_names: list[str], statement: str) -> str | None:
    aliases = [profile.normalize_name(a) for a in profile.SHEET_ALIASES[statement]]
    normalized = {name: profile.normalize_name(name) for name in sheet_names}
    for name, key in normalized.items():
        for alias in aliases:
            if alias and alias in key:
                return name
    return None


def load_workbook(path: str | Path) -> ReportSet:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在：{path}")

    frames = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    report = ReportSet(source_path=str(path))
    sheet_names = list(frames.keys())

    for statement in STATEMENT_ORDER:
        sheet = _match_sheet(sheet_names, statement)
        if sheet is None:
            report.warnings.append(f"未找到「{statement}」工作表，相关分析将跳过")
            continue
        frame = frames[sheet]
        grid = []
        for _, row in frame.iterrows():
            grid.append([None if pd.isna(v) else v for v in row.tolist()])
        data = parse_sheet(grid, statement, sheet)
        report.statements[statement] = data
        report.warnings.extend(f"[{statement}] {w}" for w in data.warnings)
        if data.conflicts:
            report.warnings.extend(f"[{statement}] 映射冲突：{c}" for c in data.conflicts)

    if not report.statements:
        raise ValueError("未能从文件中识别任何一张报表，请确认工作表名称与格式")
    return report
