"""增值税发票字段抽取 —— 输入标准化文本行，输出带溯源的字段。

输入契约（与 OCR 引擎解耦，便于单测）：
    lines = [{"text": str, "score": float, "page": int, "bbox": [x1,y1,x2,y2]}, ...]
    lines 须按阅读顺序（y 升序、同 y 按 x 升序）排列。

两套定位策略，按可靠性降序：
    ① 表头列对齐 —— 发票表格版式固定，先找表头行，再按 x 坐标把值归列。
       这是金额类字段的首选，能避免「税额」标签命中表头「税额」列取到「单价」值的错误。
    ② 标签邻近 —— 无表头时（如电子发票纯文本层）回落使用。
"""
from __future__ import annotations

import re
from typing import Any

from .validate import (
    check_arithmetic, cn_amount_to_number, make_field, normalize_date,
    parse_money, uscc_checksum_ok,
)

CRITICAL = ("invoice_no", "invoice_date", "amount_ex_tax", "tax_amount", "total_amount")
CONF_CRITICAL = 0.90

# 表头列名 → 标准列 key
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["货物或应税劳务、服务名称", "货物或应税劳务", "服务名称", "项目名称", "货物名称", "品名"],
    "spec": ["规格型号", "规格"],
    "unit": ["单位"],
    "qty": ["数量"],
    "price": ["单价"],
    "amount": ["金额", "不含税金额"],
    "rate": ["税率", "征收率", "税率/征收率"],
    "tax": ["税额"],
}


# ---------------------------------------------------------------- 工具

def _join(lines: list[dict[str, Any]]) -> str:
    return "\n".join(l.get("text", "") for l in lines)


def _f(value: Any, line: dict[str, Any] | None, source: str, **flags: Any) -> dict[str, Any]:
    return make_field(
        value,
        confidence=(line or {}).get("score", 0.0),
        page=(line or {}).get("page"),
        bbox=(line or {}).get("bbox"),
        raw_text=(line or {}).get("text", ""),
        source=source,
        **flags,
    )


def _yc(l: dict[str, Any]) -> float:
    b = l.get("bbox") or [0, 0, 0, 0]
    return (b[1] + b[3]) / 2


def _xc(l: dict[str, Any]) -> float:
    b = l.get("bbox") or [0, 0, 0, 0]
    return (b[0] + b[2]) / 2


def _group_rows(lines: list[dict[str, Any]], y_tol: int = 14) -> list[list[dict[str, Any]]]:
    """按 y 中心聚成行。"""
    rows: list[list[dict[str, Any]]] = []
    for l in sorted(lines, key=lambda x: (_yc(x), _xc(x))):
        for row in rows:
            if abs(_yc(l) - sum(_yc(c) for c in row) / len(row)) <= y_tol:
                row.append(l)
                break
        else:
            rows.append([l])
    for r in rows:
        r.sort(key=_xc)
    rows.sort(key=lambda r: sum(_yc(c) for c in r) / len(r))
    return rows


# ---------------------------------------------------------------- 表头列对齐

def _find_table_header(lines: list[dict[str, Any]]) -> dict[str, float] | None:
    """定位表头行，返回 {列 key: x 中心}。要求至少命中 4 列。"""
    for row in _group_rows(lines):
        cols: dict[str, float] = {}
        for cell in row:
            t = re.sub(r"\s", "", cell.get("text", ""))
            for key, aliases in COLUMN_ALIASES.items():
                if key in cols:
                    continue
                if t in aliases or any(t.startswith(a) and len(t) <= len(a) + 2 for a in aliases):
                    cols[key] = _xc(cell)
                    break
        if len(cols) >= 4 and "amount" in cols:
            return cols
    return None


def _col_of(x: float, cols: dict[str, float]) -> str:
    """按 x 中心归列（取最近列）。"""
    return min(cols.items(), key=lambda kv: abs(kv[1] - x))[0]


def _parse_items(lines: list[dict[str, Any]], cols: dict[str, float]) -> list[dict[str, Any]]:
    """从表头下方的数据行还原明细。"""
    rows = _group_rows(lines)
    # 表头行索引
    header_y = None
    for i, row in enumerate(rows):
        texts = {re.sub(r"\s", "", c.get("text", "")) for c in row}
        hit = sum(1 for aliases in COLUMN_ALIASES.values() for a in aliases if a in texts)
        if hit >= 4:
            header_y = i
            break
    if header_y is None:
        return []

    items: list[dict[str, Any]] = []
    for row in rows[header_y + 1:]:
        joined = "".join(c.get("text", "") for c in row)
        if re.search(r"合\s*计|价税合计|小写|大写", joined):
            break
        rec: dict[str, Any] = {}
        for cell in row:
            key = _col_of(_xc(cell), cols)
            rec.setdefault(key, []).append(cell)
        if not rec:
            continue
        item = {
            "name": " ".join(c["text"] for c in rec.get("name", [])),
            "spec": " ".join(c["text"] for c in rec.get("spec", [])),
            "unit": " ".join(c["text"] for c in rec.get("unit", [])),
            "qty": parse_money(rec["qty"][0]["text"]) if rec.get("qty") else None,
            "price": parse_money(rec["price"][0]["text"]) if rec.get("price") else None,
            "amount": parse_money(rec["amount"][0]["text"]) if rec.get("amount") else None,
            "rate": rec["rate"][0]["text"] if rec.get("rate") else None,
            "tax": parse_money(rec["tax"][0]["text"]) if rec.get("tax") else None,
            "_min_score": min(c.get("score", 1.0) for c in row),
            "_page": row[0].get("page"),
        }
        if item["name"] or item["amount"] is not None:
            items.append(item)
    return items


def _find_total_row(lines: list[dict[str, Any]], cols: dict[str, float]) -> dict[str, Any]:
    """定位「合计」行，按列取金额与税额。"""
    for row in _group_rows(lines):
        joined = "".join(c.get("text", "") for c in row)
        if not re.search(r"合\s*计|小\s*计", joined):
            continue
        if re.search(r"价税合计|大写", joined):
            continue
        out: dict[str, Any] = {}
        for cell in row:
            key = _col_of(_xc(cell), cols)
            val = parse_money(cell.get("text", ""))
            if val is None:
                continue
            if key in ("amount", "tax") and key not in out:
                out[key] = (val, cell)
        if out:
            return out
    return {}


# ---------------------------------------------------------------- 标签邻近（兜底）

def _value_after_label(lines: list[dict[str, Any]], label_rx: str,
                       value_rx: str) -> tuple[str | None, dict[str, Any] | None]:
    lrx, vrx = re.compile(label_rx), re.compile(value_rx)
    for l in lines:
        t = l.get("text", "")
        m = lrx.search(t)
        if m:
            mv = vrx.search(t[m.end():])
            if mv:
                return (mv.group(1) if mv.groups() else mv.group(0)), l
    for i, l in enumerate(lines):
        if lrx.search(l.get("text", "")):
            for nxt in lines[i + 1: i + 3]:
                mv = vrx.search(nxt.get("text", ""))
                if mv:
                    return (mv.group(1) if mv.groups() else mv.group(0)), nxt
    return None, None


# ---------------------------------------------------------------- 主流程

def extract(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """抽取发票字段。返回 {"fields": {...}, "items": [...], "flags": [...], "grade": ...}"""
    lines = [l for l in lines if (l.get("text") or "").strip()]
    lines.sort(key=lambda l: (_yc(l), _xc(l)))
    flat = _join(lines).replace("\n", " ")
    fields: dict[str, Any] = {}
    flags: list[str] = []

    cols = _find_table_header(lines)
    items = _parse_items(lines, cols) if cols else []
    total_row = _find_total_row(lines, cols) if cols else {}

    # ---- 发票号码
    raw, line = _value_after_label(
        lines, r"(?:发票号码|发\s*票\s*号\s*码)", r"(\d{8}|\d{20})")
    if not raw:
        m = re.search(r"发票号码\D{0,4}(\d{8}|\d{20})", flat)
        raw, line = (m.group(1), None) if m else (None, None)
    fields["invoice_no"] = _f(raw, line, "label_adjacent" if line else "regex")
    if raw and len(raw) not in (8, 20):
        flags.append("invoice_no_invalid")

    # ---- 发票代码
    raw, line = _value_after_label(lines, r"(?:发票代码)", r"(\d{10,12})")
    fields["invoice_code"] = _f(raw, line, "label_adjacent")

    # ---- 开票日期
    raw, line = _value_after_label(
        lines, r"(?:开票日期|开具日期)", r"(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2})")
    iso = normalize_date(raw) if raw else None
    if not iso:
        m = re.search(r"(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2})", flat)
        if m:
            iso = normalize_date(m.group(1))
            line = next((l for l in lines if m.group(1).replace(" ", "") in l.get("text", "").replace(" ", "")), None)
    fields["invoice_date"] = _f(iso, line, "label_adjacent")
    if raw and not iso:
        flags.append("date_out_of_range")

    # ---- 购销方名称 / 税号
    for key, label in (("buyer_name", r"(?:购买方|购\s*方)"),
                       ("seller_name", r"(?:销售方|销\s*方)")):
        val, l = _party_name(lines, label)
        fields[key] = _f(val, l, "region")
    for key, label in (("buyer_tax_id", r"(?:购买方|购\s*方)"),
                       ("seller_tax_id", r"(?:销售方|销\s*方)")):
        val, l = _tax_id_near(lines, label)
        fields[key] = _f(val, l, "region")
        if val and len(val) == 18 and not uscc_checksum_ok(val):
            flags.append("checksum_failed")
            fields[key].setdefault("flags", {})["checksum_failed"] = True

    # ---- 金额三件套：优先合计行（列对齐），回落标签邻近
    ae_val, ae_line = total_row.get("amount", (None, None))
    ta_val, ta_line = total_row.get("tax", (None, None))
    ae_src = "table_cell" if ae_line else None
    ta_src = "table_cell" if ta_line else None

    if ae_val is None:
        raw, ae_line = _value_after_label(
            lines, r"(?:合\s*计|金额合计|不含税金额)", r"[¥￥]?\s*([0-9][0-9,]*\.\d{2})")
        ae_val, ae_src = parse_money(raw) if raw else None, "label_adjacent"
    if ta_val is None:
        raw, ta_line = _value_after_label(
            lines, r"(?:税额合计|税\s*额)", r"[¥￥]?\s*([0-9][0-9,]*\.\d{2})")
        ta_val, ta_src = parse_money(raw) if raw else None, "label_adjacent"

    # 合计行缺失时用明细求和
    if ae_val is None and items:
        s = [i["amount"] for i in items if i["amount"] is not None]
        ae_val, ae_src = (round(sum(s), 2) if s else None), "items_sum"
    if ta_val is None and items:
        s = [i["tax"] for i in items if i["tax"] is not None]
        ta_val, ta_src = (round(sum(s), 2) if s else None), "items_sum"

    fields["amount_ex_tax"] = _f(ae_val, ae_line, ae_src or "regex")
    fields["tax_amount"] = _f(ta_val, ta_line, ta_src or "regex")

    # ---- 价税合计（小写）
    raw, tot_line = _value_after_label(
        lines, r"(?:小\s*写|价税合计)", r"[¥￥]?\s*([0-9][0-9,]*\.\d{2})")
    fields["total_amount"] = _f(parse_money(raw) if raw else None, tot_line, "label_adjacent")

    # ---- 大写金额（限定行内，不跨行）
    cn_val, cn_line = None, None
    cn_rx = re.compile(r"([零〇壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整圆]{2,})")
    for l in lines:
        if re.search(r"大写|价税合计", l.get("text", "")):
            for cell in [l] + [x for x in lines if abs(_yc(x) - _yc(l)) <= 16]:
                m = cn_rx.search(cell.get("text", ""))
                if m and ("元" in m.group(1) or "角" in m.group(1)):
                    cn_val, cn_line = m.group(1), cell
                    break
        if cn_val:
            break
    if not cn_val:
        m = re.search(r"([零〇壹贰叁肆伍陆柒捌玖拾佰仟万亿]{1,}元[零〇壹贰叁肆伍陆柒捌玖角分整]*)", flat)
        cn_val = m.group(1) if m else None
    fields["total_amount_cn"] = _f(cn_val, cn_line, "label_adjacent" if cn_line else "regex")

    # ---- 税率
    rates: list[float] = []
    for it in items:
        if it.get("rate"):
            m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", it["rate"])
            if m:
                rates.append(round(float(m.group(1)) / 100, 4))
    if not rates:
        rates = [round(int(r) / 100, 4) for r in re.findall(r"(\d{1,2})\s*%", flat)]
    fields["tax_rate"] = _f(sorted(set(rates)) or None, None, "table_cell" if items else "regex")

    # ---- 人员三栏
    for key, label in (("payee", r"收款人"), ("reviewer", r"复核人?"), ("drawer", r"开票人")):
        val, l = _person_near(lines, label)
        fields[key] = _f(val, l, "label_adjacent")

    # ---- 备注（严格行内，不跨行）
    remark, rl = None, None
    for l in lines:
        m = re.search(r"备\s*注\s*[:：]\s*(.{1,60})$", l.get("text", ""))
        if m:
            remark, rl = m.group(1).strip(), l
            break
    fields["remark"] = _f(remark, rl, "label_adjacent")

    # ============ 校验 ============
    arith = check_arithmetic(ae_val, ta_val, fields["total_amount"]["value"])
    if arith["ok"] is False:
        flags.append("arithmetic_mismatch")

    cn_num = cn_amount_to_number(cn_val) if cn_val else None
    tt = fields["total_amount"]["value"]
    if cn_num is not None and tt is not None and abs(cn_num - tt) > 0.01:
        flags.append("case_mismatch")

    # 明细合计校验
    if items and ae_val is not None:
        s = [i["amount"] for i in items if i["amount"] is not None]
        if s and abs(round(sum(s), 2) - ae_val) > 0.01:
            flags.append("items_sum_mismatch")

    bn, sn = fields["buyer_name"]["value"], fields["seller_name"]["value"]
    if bn and sn and bn.strip() == sn.strip():
        flags.append("same_party")

    for k in CRITICAL:
        f = fields.get(k)
        if f and f.get("value") not in (None, "") and (f.get("confidence") or 0) < CONF_CRITICAL:
            flags.append(f"low_confidence:{k}")
            f.setdefault("flags", {})["low_confidence"] = True
        if not f or f.get("value") in (None, ""):
            flags.append(f"missing:{k}")

    for it in items:
        it.pop("_min_score", None)

    grade = _grade(fields, flags)
    return {
        "type": "vat_invoice",
        "fields": fields,
        "items": items,
        "columns_detected": bool(cols),
        "checks": {"arithmetic": arith, "cn_amount": cn_num},
        "flags": sorted(set(flags)),
        "grade": grade,
        "needs_review": grade in ("C", "D"),
    }


# ---------------------------------------------------------------- 子抽取器

def _clean_name(s: str) -> str:
    s = re.sub(r"^[名称:：\s]+", "", s or "")
    s = re.sub(r"[|｜·•]+$", "", s)
    return s.strip()


def _find_label_line(lines: list[dict[str, Any]], label_rx: str) -> dict[str, Any] | None:
    """找标签行。优先短标签行（避免「购买方名称：」这类长行抢先）。"""
    lrx = re.compile(label_rx)
    cands = [l for l in lines if lrx.search(l.get("text", ""))]
    if not cands:
        return None
    # 短行更像区域标签（如「购买方」三字）
    return min(cands, key=lambda l: (len(l.get("text", "")), _yc(l)))


def _nearest_below(lines: list[dict[str, Any]], anchor: dict[str, Any],
                   pattern: re.Pattern, y_window: int = 200) -> tuple[str | None, dict[str, Any] | None]:
    """在锚点行附近（优先下方、y 距离最近）找匹配 pattern 的行。

    不依赖列表顺序 —— OCR 返回顺序与阅读顺序不一致，按坐标判定才稳。
    """
    ay = _yc(anchor)
    best: tuple[float, int, str, dict[str, Any]] | None = None
    for l in lines:
        if l is anchor:
            continue
        m = pattern.search(l.get("text", ""))
        if not m:
            continue
        dy = _yc(l) - ay
        if abs(dy) > y_window:
            continue
        # 下方优先（0），上方次之（1）
        bucket = 0 if dy >= -8 else 1
        key = (bucket, abs(dy))
        if best is None or key < (best[1], best[0]):
            best = (abs(dy), bucket, m.group(1) if m.groups() else m.group(0), l)
    if best is None:
        return None, None
    return best[2], best[3]


def _party_name(lines: list[dict[str, Any]], label_rx: str) -> tuple[str | None, dict[str, Any] | None]:
    anchor = _find_label_line(lines, label_rx)
    if anchor is None:
        return None, None
    # ① 「名称：XXX」
    v, l = _nearest_below(lines, anchor, re.compile(r"名\s*称\s*[:：]\s*(\S.{1,40})"))
    if v:
        return _clean_name(v), l
    # ② 兜底：锚点下方最近的中文名称行
    ay = _yc(anchor)
    cands = []
    for c in lines:
        t = c.get("text", "")
        dy = _yc(c) - ay
        if 0 <= dy <= 120 and re.search(r"[\u4e00-\u9fa5]{4,}", t) \
                and not re.search(r"税|号|地址|电话|开户|识别|名称", t):
            cands.append((dy, c))
    if cands:
        cands.sort(key=lambda x: x[0])
        return _clean_name(cands[0][1]["text"]), cands[0][1]
    return None, None


def _tax_id_near(lines: list[dict[str, Any]], label_rx: str) -> tuple[str | None, dict[str, Any] | None]:
    anchor = _find_label_line(lines, label_rx)
    tid_rx = re.compile(r"(?:纳税人识别号|统一社会信用代码)\s*[:：]?\s*([0-9A-Z]{15,20})")
    if anchor is not None:
        v, l = _nearest_below(lines, anchor, tid_rx)
        if v:
            return v, l
    for l in lines:
        m = tid_rx.search(l.get("text", ""))
        if m:
            return m.group(1), l
    return None, None


def _person_near(lines: list[dict[str, Any]], label_rx: str) -> tuple[str | None, dict[str, Any] | None]:
    lrx = re.compile(label_rx + r"\s*[:：]?\s*([\u4e00-\u9fa5]{2,4})")
    for l in lines:
        m = lrx.search(l.get("text", ""))
        if m:
            return m.group(1), l
    return None, None


def _grade(fields: dict[str, Any], flags: list[str]) -> str:
    missing = [f for f in flags if f.startswith("missing:")]
    lowconf = [f for f in flags if f.startswith("low_confidence:")]
    hard = [f for f in flags if f in ("arithmetic_mismatch", "case_mismatch",
                                      "invoice_no_invalid", "items_sum_mismatch")]
    if "missing:invoice_no" in flags and "missing:invoice_date" in flags:
        return "D"
    if hard or missing:
        return "C"
    if lowconf:
        return "B"
    return "A"
