"""确定性校验模块 —— 不依赖 OCR 引擎，可独立单测。

设计原则：只校验、只标记，绝不修正任何抽取到的值。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# ---------------------------------------------------------------- 统一社会信用代码

_USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
_USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]


def uscc_checksum_ok(code: str) -> bool:
    """18 位统一社会信用代码校验位校验（GB 32100-2015）。

    非 18 位或含非法字符返回 False。15 位旧税号无校验位，返回 True。
    """
    code = (code or "").strip().upper()
    if len(code) == 15:
        return code.isalnum()
    if len(code) != 18:
        return False
    if any(c not in _USCC_CHARSET for c in code):
        return False
    total = sum(_USCC_CHARSET.index(c) * w for c, w in zip(code[:17], _USCC_WEIGHTS))
    check = 31 - (total % 31)
    if check == 31:
        check = 0
    return _USCC_CHARSET[check] == code[17]


# ---------------------------------------------------------------- 金额大写转数字

_CN_DIGIT = {
    "零": 0, "〇": 0, "壹": 1, "一": 1, "贰": 2, "二": 2, "两": 2,
    "叁": 3, "三": 3, "肆": 4, "四": 4, "伍": 5, "五": 5,
    "陆": 6, "六": 6, "柒": 7, "七": 7, "捌": 8, "八": 8, "玖": 9, "九": 9,
}
_CN_UNIT = {"拾": 10, "十": 10, "佰": 100, "百": 100, "仟": 1000, "千": 1000}
_CN_BIG = {"万": 10_000, "亿": 100_000_000}


def cn_amount_to_number(text: str) -> float | None:
    """中文大写金额转数值。失败返回 None（不猜）。

    支持：壹万贰仟叁佰肆拾伍元陆角柒分 / 伍佰元整 / 壹亿零贰佰万元整
    """
    if not text:
        return None
    s = re.sub(r"[\s，,。]", "", text)
    s = s.replace("人民币", "").replace("圆", "元")
    if not s:
        return None
    # 拆出 元/角/分 三段
    m = re.search(r"(.*?)元(?:([零〇壹贰叁肆伍陆柒捌玖一二三四五六七八九])角)?"
                  r"(?:([零〇壹贰叁肆伍陆柒捌玖一二三四五六七八九])分)?(?:整|正)?$", s)
    if m:
        int_part, jiao, fen = m.group(1), m.group(2), m.group(3)
    else:
        # 无「元」，可能是「柒分」「陆角」
        m2 = re.fullmatch(r"(?:([零〇壹贰叁肆伍陆柒捌玖一二三四五六七八九])角)?"
                          r"(?:([零〇壹贰叁肆伍陆柒捌玖一二三四五六七八九])分)?(?:整|正)?", s)
        if not m2 or not (m2.group(1) or m2.group(2)):
            return None
        int_part, jiao, fen = "", m2.group(1), m2.group(2)

    int_val = _cn_integer(int_part) if int_part else 0
    if int_val is None:
        return None
    val = float(int_val)
    if jiao:
        val += _CN_DIGIT[jiao] / 10
    if fen:
        val += _CN_DIGIT[fen] / 100
    return round(val, 2)


def _cn_integer(s: str) -> int | None:
    """解析「壹万贰仟叁佰肆拾伍」这类整数段。"""
    if not s:
        return 0
    # 亿级分段递归
    if "亿" in s:
        left, _, right = s.partition("亿")
        lv = _cn_integer(left)
        rv = _cn_integer(right)
        if lv is None or rv is None:
            return None
        return lv * 100_000_000 + rv
    if "万" in s:
        left, _, right = s.partition("万")
        lv = _cn_integer(left) if left else 1
        rv = _cn_integer(right)
        if lv is None or rv is None:
            return None
        return lv * 10_000 + rv

    total, section, num = 0, 0, None
    for ch in s:
        if ch in _CN_DIGIT:
            num = _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            unit = _CN_UNIT[ch]
            if num is None:
                num = 1  # 「拾」单独出现按 10 处理
            section += num * unit
            num = None
        elif ch in _CN_BIG:
            section = (section + (num or 0)) * _CN_BIG[ch]
            total += section
            section, num = 0, None
        else:
            return None
    return total + section + (num or 0)


# ---------------------------------------------------------------- 日期

_DATE_RE = re.compile(r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")


def normalize_date(text: str, min_year: int = 2015) -> str | None:
    """把各种日期写法归一为 YYYY-MM-DD。非法返回 None。"""
    if not text:
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < min_year or y > date.today().year + 1:
        return None
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def date_in_range(iso: str, min_year: int = 2015) -> bool:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return min_year <= d.year <= date.today().year + 1


# ---------------------------------------------------------------- 金额

_MONEY_RE = re.compile(r"[¥￥]?\s*(-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)")


def parse_money(text: str) -> float | None:
    if text is None:
        return None
    m = _MONEY_RE.search(str(text))
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", "")), 2)
    except ValueError:
        return None


def check_arithmetic(amount_ex_tax: float | None, tax_amount: float | None,
                     total_amount: float | None, tol: float = 0.01) -> dict[str, Any]:
    """价税勾稽：不含税 + 税额 = 价税合计。"""
    if None in (amount_ex_tax, tax_amount, total_amount):
        return {"ok": None, "reason": "missing_field", "diff": None}
    diff = round(amount_ex_tax + tax_amount - total_amount, 2)
    return {"ok": abs(diff) <= tol, "reason": "" if abs(diff) <= tol else "arithmetic_mismatch",
            "diff": diff}


VALID_TAX_RATES = {0.0, 0.01, 0.03, 0.05, 0.06, 0.09, 0.13, 0.015, 0.02, 0.04, 0.1, 0.16, 0.17}


def tax_rate_ok(rate: float | None) -> bool:
    if rate is None:
        return True
    return round(rate, 4) in VALID_TAX_RATES or 0 <= rate <= 0.17


# ---------------------------------------------------------------- 证据结构

def make_field(value: Any, confidence: float, page: int | None = None,
               bbox: list[int] | None = None, raw_text: str = "",
               source: str = "regex", **flags: Any) -> dict[str, Any]:
    """构造带溯源信息的字段。无 evidence 的字段运行时视为不可信。"""
    f = {
        "value": value,
        "confidence": round(float(confidence), 4) if confidence is not None else None,
        "evidence": {
            "page": page,
            "bbox": bbox,
            "raw_text": raw_text,
            "source": source,
        },
    }
    if flags:
        f["flags"] = {k: v for k, v in flags.items() if v}
    return f


def field_ok(field: dict[str, Any] | None, threshold: float) -> bool:
    if not field or field.get("value") in (None, ""):
        return False
    conf = field.get("confidence")
    return conf is not None and conf >= threshold
