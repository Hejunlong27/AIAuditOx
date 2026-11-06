"""合同结构抽取 —— 只做确定性结构切分，不做语义归纳。

输入契约同 extract_invoice：lines = [{text, score, page, bbox}]
"""
from __future__ import annotations

import re
from typing import Any

from .validate import cn_amount_to_number, normalize_date, parse_money

# 条号正则（行首）
CLAUSE_PATTERNS = [
    re.compile(r"^\s*(第\s*[一二三四五六七八九十百零〇\d]+\s*条)"),
    re.compile(r"^\s*([一二三四五六七八九十]+)\s*[、.．]\s*"),
    re.compile(r"^\s*(\d+)\s*[、.．]\s*(?=[\u4e00-\u9fa5])"),
    re.compile(r"^\s*(\d+(?:\.\d+)+)\s*[、.．\s]"),
]
SUB_PATTERN = re.compile(r"^\s*[（(]\s*[一二三四五六七八九十\d]+\s*[)）]")

AMOUNT_UNIT = {"元": 1, "万元": 10_000, "亿元": 100_000_000, "万": 10_000, "亿": 100_000_000}
ESTIMATE_WORDS = ("暂定", "预估", "估算", "据实结算", "以实际发生为准", "暂估", "约")


def _yc(l: dict[str, Any]) -> float:
    b = l.get("bbox") or [0, 0, 0, 0]
    return (b[1] + b[3]) / 2


def extract(lines: list[dict[str, Any]]) -> dict[str, Any]:
    lines = [l for l in lines if (l.get("text") or "").strip()]
    lines.sort(key=lambda l: (_yc(l), (l.get("bbox") or [0])[0]))

    meta = _extract_meta(lines)
    parties = _extract_parties(lines)
    clauses = _split_clauses(lines)
    key_terms = _extract_key_terms(lines, clauses)
    signatures = _extract_signatures(lines)

    flags: list[str] = []
    notes: list[str] = []          # 提示项，不影响等级
    total_chars = sum(len(l.get("text", "")) for l in lines)

    split_state = "ok"
    if len(clauses) < 3 and total_chars > 2000:
        split_state = "failed"
        flags.append("clause_split_failed")

    if len([p for p in parties if p.get("name")]) < 2:
        flags.append("parties_incomplete")
    if not meta.get("sign_date"):
        flags.append("sign_date_missing")

    # 多金额候选：主金额已过大写交叉验证时仅作提示
    amts = {a["value"] for a in (key_terms.get("amount_candidates") or [])}
    if len(amts) > 1:
        if key_terms.get("amount_cn_agrees") is True:
            notes.append("amount_candidates")
        else:
            flags.append("amount_candidates")
    if key_terms.get("amount_cn_agrees") is False:
        flags.append("amount_cn_mismatch")

    grade = "C" if flags else ("B" if (split_state != "ok" or notes) else "A")

    return {
        "type": "contract",
        "meta": meta,
        "parties": parties,
        "clauses": clauses,
        "key_terms": key_terms,
        "signatures": signatures,
        "clause_split": split_state,
        "flags": sorted(set(flags + notes)),
        "grade": grade,
        "needs_review": grade == "C",
    }


def _extract_meta(lines: list[dict[str, Any]]) -> dict[str, Any]:
    head = " ".join(l.get("text", "") for l in lines[:30])
    full = " ".join(l.get("text", "") for l in lines)

    title = None
    for l in lines[:12]:
        t = l.get("text", "").strip()
        if 4 <= len(t) <= 40 and re.search(r"(合同|协议)$", t):
            title = t
            break

    no = None
    m = re.search(r"(?:合同编号|协议编号|编号)\s*[:：]?\s*([A-Za-z0-9\-_（）()]{3,30})", head)
    if m:
        no = m.group(1)

    place = None
    m = re.search(r"(?:签订地点|签约地点|签订地)\s*[:：]?\s*([\u4e00-\u9fa5]{2,20})", head)
    if m:
        place = m.group(1)

    sign_date = None
    for pat in (r"(?:签订日期|签署日期|签约日期)\s*[:：]?\s*(\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2})",
                r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"):
        m = re.search(pat, head) or re.search(pat, full)
        if m:
            sign_date = normalize_date(m.group(0))
            if sign_date:
                break

    pages = max((l.get("page", 0) for l in lines), default=0)
    return {"title": title, "contract_no": no, "sign_place": place,
            "sign_date": sign_date, "pages": pages}


def _extract_parties(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parties: list[dict[str, Any]] = []
    role_map = ["甲方", "乙方", "丙方", "委托人", "受托人", "出租方", "承租方",
                "买方", "卖方", "需方", "供方"]
    seen: set[str] = set()

    for i, l in enumerate(lines[:60]):
        t = l.get("text", "")
        for role in role_map:
            if role in t and role not in seen:
                m = re.search(rf"{role}\s*[（(]?[^)）]*[)）]?\s*[:：]\s*(\S.{{1,40}})", t)
                name = m.group(1) if m else None
                if not name:
                    for nxt in lines[i + 1: i + 3]:
                        nt = nxt.get("text", "").strip()
                        if 2 < len(nt) < 50 and not re.search(r"[:：]", nt):
                            name = nt
                            break
                if name:
                    name = re.sub(r"[（(]?以下简称[^)）]*[)）]?", "", name).strip(" ，,。")
                    parties.append({"role": role, "name": name,
                                    "confidence": l.get("score", 0.0),
                                    "page": l.get("page")})
                    seen.add(role)
                break

    full = "\n".join(l.get("text", "") for l in lines[:80])
    for p in parties:
        pos = full.find(p["role"])
        seg = full[pos: pos + 300] if pos >= 0 else ""
        m = re.search(r"(?:住\s*所|地\s*址)\s*[:：]\s*(\S{4,60})", seg)
        p["address"] = m.group(1) if m else None
        m = re.search(r"(?:法定代表人|负责人|代表人)\s*[:：]\s*([\u4e00-\u9fa5]{2,4})", seg)
        p["legal_rep"] = m.group(1) if m else None
    return parties


def _split_clauses(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按条号切分。已在「第X条」内时，`1、` `2、` 视为子项而非新条款。"""
    clauses: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None

    for l in lines:
        t = l.get("text", "")
        if not t.strip():
            continue

        hit = None
        is_plain_num = False
        for idx, pat in enumerate(CLAUSE_PATTERNS):
            m = pat.match(t)
            if m and len(t) < 60:
                hit = m.group(1)
                is_plain_num = idx >= 1  # 非「第X条」的普通序号
                break

        # 普通序号出现在「第X条」内 → 子项，不新开条款
        if hit and is_plain_num and cur and cur["no"].startswith("第"):
            cur["text"] += "\n" + t.strip()
            cur.setdefault("sub_items", []).append(t.strip())
            continue

        if hit:
            if cur:
                clauses.append(cur)
            title = t[len(hit):].strip(" 、.．:：")
            cur = {
                "no": re.sub(r"\s+", "", hit),
                "title": title[:40] if title else "",
                "text": t.strip(),
                "page": l.get("page"),
                "bbox": l.get("bbox"),
                "confidence": l.get("score", 0.0),
            }
        elif cur is not None:
            cur["text"] += "\n" + t.strip()

    if cur:
        clauses.append(cur)

    # 补二级条目（（一）（1）式）
    for c in clauses:
        subs = [ln.strip() for ln in c["text"].split("\n")[1:] if SUB_PATTERN.match(ln)]
        if subs:
            merged = c.get("sub_items", []) + subs
            c["sub_items"] = list(dict.fromkeys(merged))
    return clauses


def _extract_key_terms(lines: list[dict[str, Any]],
                       clauses: list[dict[str, Any]]) -> dict[str, Any]:
    full = "\n".join(l.get("text", "") for l in lines)
    terms: dict[str, Any] = {}

    # ---- 主金额：合同总价类关键词后的第一个「非百分比」金额
    # 关键：(?![0-9]) 防止「30%」被贪婪回溯截成「3」；排除编号/日期类上下文
    primary_rx = re.compile(
        r"(?:合同总价|合同总金额|合同金额|总金额|价款总额|总价款|总价为|合计金额|合同价款)"
        r"[^0-9¥￥%‰]{0,30}[¥￥]?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
        r"(?![0-9])(?!\s*[%‰])\s*(万元|亿元|元|万|亿)?")
    primary: list[dict[str, Any]] = []
    for m in primary_rx.finditer(full):
        num = parse_money(m.group(1))
        if num is None:
            continue
        unit = m.group(2) or "元"
        val = round(num * AMOUNT_UNIT.get(unit, 1), 2)
        if val < 1:
            continue
        ctx = full[max(0, m.start() - 30): m.end() + 90]
        primary.append({"value": val, "raw": m.group(0).strip(),
                        "is_estimate": any(w in ctx for w in ESTIMATE_WORDS)})

    # ---- 其他金额候选：排除百分比、年份、编号
    cand_rx = re.compile(r"[¥￥]?\s*([0-9][0-9,]{2,}(?:\.[0-9]{1,2})?)"
                         r"(?![0-9])(?!\s*[%‰])")
    others: list[dict[str, Any]] = []
    for m in cand_rx.finditer(full):
        num = parse_money(m.group(1))
        if num is None or num < 1000:
            continue
        if 1900 <= num <= 2100 and "." not in m.group(1):
            continue
        ctx = full[max(0, m.start() - 25): m.end() + 25]
        if re.search(r"编号|合同号|HT-|No\.|凭证号|发票号|账号", ctx):
            continue
        others.append({"value": num, "raw": m.group(0).strip(),
                       "is_estimate": any(w in ctx for w in ESTIMATE_WORDS)})

    uniq: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for c in primary + others:
        k = (c["value"], c["is_estimate"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    terms["amount_candidates"] = uniq[:10]
    terms["contract_amount"] = primary[0]["value"] if primary else (
        uniq[0]["value"] if uniq else None)
    terms["amount_source"] = "primary_label" if primary else ("candidate" if uniq else None)
    terms["amount_is_estimate"] = primary[0]["is_estimate"] if primary else (
        uniq[0]["is_estimate"] if uniq else None)

    # ---- 大写金额交叉校验
    m = re.search(r"([零〇壹贰叁肆伍陆柒捌玖拾佰仟万亿]{1,}元[零〇壹贰叁肆伍陆柒捌玖角分整]*)", full)
    terms["amount_cn"] = m.group(1) if m else None
    terms["amount_cn_value"] = cn_amount_to_number(m.group(1)) if m else None
    ca, cnv = terms["contract_amount"], terms["amount_cn_value"]
    terms["amount_cn_agrees"] = None if (ca is None or cnv is None) else abs(ca - cnv) <= 0.01

    # ---- 期限
    period: dict[str, Any] = {}
    m = re.search(r"自\s*(.{4,25}?)\s*起\s*至\s*(.{4,25}?)\s*止", full)
    if m:
        period["start_raw"], period["end_raw"] = m.group(1), m.group(2)
        period["start"] = normalize_date(m.group(1))
        period["end"] = normalize_date(m.group(2))
    for kw in ("合同有效期", "服务期限", "工期", "履行期限", "合作期限"):
        mm = re.search(rf"{kw}[^。；\n]{{0,60}}", full)
        if mm:
            period.setdefault("raw", []).append(mm.group(0))
    terms["period"] = period or None

    # ---- 付款条件：只在付款类条款内取比例，剔除违约金条款
    pay_clauses = [c for c in clauses
                   if re.search(r"付款|结算|支付|价款", c["text"])
                   and not re.search(r"违约|赔偿|罚则", c["text"])]
    pay: dict[str, Any] = {}
    ratios: set[float] = set()
    for c in pay_clauses:
        for r in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", c["text"]):
            v = float(r)
            if 0 < v <= 100:
                ratios.add(v)
    if ratios:
        pay["ratios"] = sorted(ratios)
    nodes = [k for k in ("预付款", "进度款", "验收款", "质保金", "尾款", "首付款") if k in full]
    if nodes:
        pay["nodes"] = nodes
    m = re.search(r"(\d{1,3})\s*(?:个)?\s*(?:工作)?(?:日|天)\s*内\s*(?:支付|付款)", full)
    if m:
        pay["credit_days"] = int(m.group(1))
    terms["payment"] = pay or None

    # ---- 违约与争议
    breach: dict[str, Any] = {}
    m = re.search(r"违约金[^。；\n]{0,30}?(\d+(?:\.\d+)?)\s*%", full)
    if m:
        breach["penalty_rate"] = float(m.group(1)) / 100
    m = re.search(r"每(?:日|逾期一日)[^。；\n]{0,25}?(\d+(?:\.\d+)?)\s*([%‰])", full)
    if m:
        breach["daily_rate"] = m.group(1) + m.group(2)
        if m.group(2) == "%":
            breach["daily_rate_note"] = "单位疑为‰（OCR 常将‰误识为%），请核对原件"
    if "仲裁" in full:
        breach["dispute"] = "仲裁"
        m = re.search(r"([\u4e00-\u9fa5]{4,30}仲裁委员会)", full)
        if m:
            breach["arbitration_body"] = m.group(1)
    elif "诉讼" in full or "法院" in full:
        breach["dispute"] = "诉讼"
        m = re.search(r"([\u4e00-\u9fa5]{2,25}人民法院)", full)
        if m:
            breach["court"] = m.group(1)
    terms["breach"] = breach or None

    # ---- 质保
    m = re.search(r"质保期[^。；\n]{0,40}?(\d{1,2})\s*(个月|年)", full)
    if m:
        terms["warranty"] = {"value": int(m.group(1)), "unit": m.group(2)}

    return terms


def _extract_signatures(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """签章区：取文本尾部 28% 区域，只认「签订日期」标签或签章块内的日期。"""
    if not lines:
        return {"parties": [], "dates": [], "seal_detected": None}
    ys = [_yc(l) for l in lines]
    y_cut = min(ys) + (max(ys) - min(ys)) * 0.72
    tail = [l for l in lines if _yc(l) >= y_cut]
    text = "\n".join(l.get("text", "") for l in tail)

    sig: dict[str, Any] = {"parties": [], "dates": []}
    for m in re.finditer(r"(甲\s*方|乙\s*方|丙\s*方)\s*[（(]\s*(?:盖章|签章|公章)\s*[)）]", text):
        sig["parties"].append(m.group(1).replace(" ", ""))

    for m in re.finditer(
            r"(?:签订|签署|签约)日期\s*[:：]?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text):
        d = normalize_date(m.group(0))
        if d:
            sig["dates"].append(d)
    sig["dates"] = sorted(set(sig["dates"]))

    seal = [l for l in tail if l.get("block_label") in ("seal", "stamp")]
    has_label = any("block_label" in l for l in tail)
    sig["seal_detected"] = bool(seal) if has_label else None
    return sig
