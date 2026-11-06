"""文档类型判别 —— 纯文本规则，不依赖 OCR 引擎。

输入：OCR 得到的全页文本行列表（含置信度、页码、坐标）
输出：类型 + 置信度 + 命中信号明细（可审计）
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# 强特征词（权重 2.0）
STRONG = {
    "vat_invoice": [
        "增值税专用发票", "增值税普通发票", "电子发票", "发票号码", "价税合计",
        "销售方", "购买方", "开票日期", "发票代码", "税率",
    ],
    "receipt": [
        "收据", "银行回单", "进账单", "付款凭证", "完税证明", "税收缴款书",
        "支票", "汇票", "收款人", "交易流水", "电子回单",
    ],
    "contract": [
        "合同", "协议", "甲方", "乙方", "签订地点", "签订日期", "第一条",
        "违约责任", "争议解决", "本合同", "委托人", "受托人",
    ],
    "statement": [
        "对账单", "明细表", "本期发生额", "期初余额", "期末余额",
    ],
}

# 弱特征词（权重 1.0）
WEAK = {
    "vat_invoice": ["统一社会信用代码", "开户行", "校验码", "货物或应税劳务", "规格型号"],
    "receipt": ["金额大写", "用途", "出票日期", "付款人", "账号"],
    "contract": ["盖章", "法定代表人", "委托代理人", "附件", "生效"],
    "statement": ["序号", "合计", "累计", "借贷"],
}

# 互斥信号：出现则大幅削弱该类型
EXCLUDE = {
    "vat_invoice": ["对账单", "银行回单", "进账单"],
    "receipt": ["增值税专用发票", "价税合计", "发票号码"],
}

# 发票三件套：必须同时具备才算发票强判据
INVOICE_TRIPLET = ["发票号码", "价税合计", "税额"]


def _norm(text: str) -> str:
    """去掉空白和常见 OCR 噪声，便于匹配。"""
    return re.sub(r"[\s\u3000|｜·•]", "", text or "")


def classify_texts(lines: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """按文本行列表判别文档类型。

    lines: [{"text": str, "score": float, "page": int, "bbox": [x1,y1,x2,y2]}]
    """
    lines = list(lines)
    full = _norm("".join(l.get("text", "") for l in lines))

    scores: dict[str, float] = {}
    hits: dict[str, dict[str, list[str]]] = {}

    for t in STRONG:
        s, h = 0.0, {"strong": [], "weak": [], "excluded": []}
        for kw in STRONG[t]:
            if _norm(kw) in full:
                s += 2.0
                h["strong"].append(kw)
        for kw in WEAK[t]:
            if _norm(kw) in full:
                s += 1.0
                h["weak"].append(kw)
        for kw in EXCLUDE.get(t, []):
            if _norm(kw) in full:
                s -= 3.0
                h["excluded"].append(kw)
        scores[t] = max(s, 0.0)
        hits[t] = h

    # 发票硬门槛：三件套齐全才可能判为发票
    if not all(_norm(k) in full for k in INVOICE_TRIPLET):
        scores["vat_invoice"] = min(scores.get("vat_invoice", 0.0), 1.0)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_type, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    ambiguous = False
    if top_score < 3.0:
        doc_type = "generic"
        confidence = 0.3 if top_score < 1.0 else 0.5
    elif second_score > 0 and top_score / max(second_score, 0.001) < 1.5:
        doc_type = top_type
        confidence = 0.55
        ambiguous = True
    else:
        doc_type = top_type
        confidence = min(0.95, 0.6 + 0.05 * top_score)

    return {
        "type": doc_type,
        "confidence": round(confidence, 2),
        "ambiguous": ambiguous,
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "signals": hits.get(doc_type, {}),
    }


# ---------------------------------------------------------------- 页眉页脚剔除

_PAGENO_PATTERNS = [
    re.compile(r"^\s*第?\s*\d+\s*页(\s*/?\s*共\s*\d+\s*页)?\s*$"),
    re.compile(r"^\s*共\s*\d+\s*页\s*第?\s*\d+\s*页?\s*$"),
    re.compile(r"^\s*[-—]\s*\d+\s*[-—]\s*$"),
    re.compile(r"^\s*Page\s*\d+(\s*(of|/)\s*\d+)?\s*$", re.I),
]


def is_page_furniture(text: str, page: int, total_pages: int,
                      repeated_texts: set[str] | None = None) -> bool:
    """判断某行是否为页眉页脚（页码行 / 多页重复行）。"""
    t = (text or "").strip()
    if not t:
        return True
    if any(p.match(t) for p in _PAGENO_PATTERNS):
        return True
    if repeated_texts and _norm(t) in repeated_texts and len(_norm(t)) < 40:
        return True
    return False


def detect_repeated_lines(pages: list[list[dict[str, Any]]],
                          edge_only: int = 3) -> set[str]:
    """找出在多页重复出现的短行（页眉/页脚/密级）。

    只在每页的**首尾若干行**中统计 —— 正文中部偶然重复的句子不应被当成页眉页脚，
    否则多页模板化文档（如每页结构相同的合同）会被整页清空。
    """
    if len(pages) < 2:
        return set()
    counter: dict[str, int] = {}
    for lines in pages:
        ordered = sorted(lines, key=lambda l: ((l.get("bbox") or [0, 0, 0, 0])[1],
                                               (l.get("bbox") or [0, 0, 0, 0])[0]))
        edge = ordered[:edge_only] + ordered[-edge_only:]
        seen = set()
        for l in edge:
            k = _norm(l.get("text", ""))
            if 2 <= len(k) < 40 and k not in seen:
                seen.add(k)
                counter[k] = counter.get(k, 0) + 1
    threshold = max(2, int(len(pages) * 0.6))
    return {k for k, v in counter.items() if v >= threshold}
