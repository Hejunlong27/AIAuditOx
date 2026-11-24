"""Small deterministic helpers for reading audit tabular inputs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


class TableReadError(ValueError):
    """An input table cannot be interpreted safely."""


@dataclass(frozen=True)
class TableRow:
    values: dict[str, Any]

    def get(self, *aliases: str, default: Any = None) -> Any:
        normalized = {_norm_key(key): value for key, value in self.values.items()}
        for alias in aliases:
            key = _norm_key(alias)
            if key in normalized:
                value = normalized[key]
                if value is not None and str(value).strip() != "":
                    return value
        return default

    def text(self, *aliases: str, default: str = "") -> str:
        value = self.get(*aliases, default=default)
        return str(value).strip() if value is not None else default

    def number(self, *aliases: str, default: Decimal | None = None) -> Decimal | None:
        value = self.get(*aliases)
        if value is None or str(value).strip() == "":
            return default
        try:
            text = str(value).strip().replace(",", "").replace("，", "")
            return Decimal(text)
        except (InvalidOperation, ValueError) as exc:
            raise TableReadError(f"字段 {aliases[0]} 不是有效数字：{value!r}") from exc

    def date(self, *aliases: str) -> date | None:
        value = self.get(*aliases)
        if value is None or str(value).strip() == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise TableReadError(f"字段 {aliases[0]} 不是有效日期：{value!r}")


def read_table(path: Path) -> list[TableRow]:
    source = Path(path)
    if not source.is_file():
        raise TableReadError(f"输入文件不存在：{source}")
    suffix = source.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        return _read_delimited(source, "\t" if suffix == ".tsv" else ",")
    if suffix in {".xlsx", ".xlsm"}:
        return _read_xlsx(source)
    raise TableReadError(f"暂不支持输入格式：{source.suffix}")


def row_values(rows: Iterable[TableRow], *aliases: str) -> list[Any]:
    return [row.get(*aliases) for row in rows if row.get(*aliases) not in (None, "")]


def _read_delimited(path: Path, delimiter: str) -> list[TableRow]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise TableReadError(f"CSV 没有表头：{path}")
            return [TableRow(values=dict(row)) for row in reader]
    except UnicodeDecodeError:
        try:
            with path.open("r", encoding="gb18030", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                return [TableRow(values=dict(row)) for row in reader]
        except Exception as exc:
            raise TableReadError(f"CSV 解码失败：{path}") from exc


def _read_xlsx(path: Path) -> list[TableRow]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = workbook.active
        all_rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not all_rows:
        raise TableReadError(f"工作簿为空：{path}")
    header_index = _find_header_row(all_rows)
    headers = [
        str(value).strip() if value is not None else f"column_{i}"
        for i, value in enumerate(all_rows[header_index])
    ]
    rows: list[TableRow] = []
    for raw in all_rows[header_index + 1 :]:
        if all(value is None or str(value).strip() == "" for value in raw):
            continue
        values = {headers[i]: raw[i] if i < len(raw) else None for i in range(len(headers))}
        rows.append(TableRow(values=values))
    return rows


def _find_header_row(rows: list[tuple[Any, ...]]) -> int:
    best_index = 0
    best_score = -1
    for index, row in enumerate(rows[:20]):
        score = sum(1 for value in row if value is not None and str(value).strip())
        if score > best_score:
            best_index, best_score = index, score
    if best_score < 2:
        raise TableReadError("无法识别表头：前 20 行有效列不足 2 个")
    return best_index


def _norm_key(value: Any) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("（", "(")
        .replace("）", ")")
    )


__all__ = ["TableReadError", "TableRow", "read_table", "row_values"]
