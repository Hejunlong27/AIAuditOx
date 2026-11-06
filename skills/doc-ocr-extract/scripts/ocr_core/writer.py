"""输出层：Markdown / JSON / 批次索引 / 人工复核清单。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def lines_to_markdown(lines: list[dict[str, Any]], low_conf: float = 0.60) -> str:
    """文本行 → Markdown。按 bbox 的 y 坐标聚行，按 x 排序。"""
    if not lines:
        return ""
    # 按页分组
    pages: dict[int, list[dict]] = {}
    for l in lines:
        pages.setdefault(l.get("page", 1), []).append(l)

    out: list[str] = []
    for pg in sorted(pages):
        rows = _group_rows(pages[pg])
        if len(pages) > 1:
            out.append(f"\n<!-- page {pg} -->\n")
        for row in rows:
            text = " ".join(c["text"] for c in row)
            min_score = min(c.get("score", 1.0) for c in row)
            if min_score < low_conf:
                text = f"[?] {text}"
            out.append(text)
            out.append("")
    return "\n".join(out).strip()


def _group_rows(lines: list[dict], y_tol: int = 12) -> list[list[dict]]:
    """按 y 坐标聚类成行。"""
    items = sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0]))
    rows: list[list[dict]] = []
    for it in items:
        y_center = (it["bbox"][1] + it["bbox"][3]) / 2
        placed = False
        for row in rows:
            ry = sum((c["bbox"][1] + c["bbox"][3]) / 2 for c in row) / len(row)
            if abs(y_center - ry) <= y_tol:
                row.append(it)
                placed = True
                break
        if not placed:
            rows.append([it])
    for row in rows:
        row.sort(key=lambda c: c["bbox"][0])
    rows.sort(key=lambda r: min(c["bbox"][1] for c in r))
    return rows


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_index_entry(doc_result: dict[str, Any]) -> dict[str, Any]:
    """从单文档结果提炼索引条目（供其他 skill 检索）。"""
    return {
        "file": doc_result.get("file"),
        "type": doc_result.get("type"),
        "type_confidence": doc_result.get("type_confidence"),
        "grade": doc_result.get("grade"),
        "needs_review": doc_result.get("needs_review"),
        "pages": doc_result.get("pages"),
        "elapsed_sec": doc_result.get("elapsed_sec"),
        "engine": doc_result.get("engine"),
        "summary": doc_result.get("summary"),
        "flags": doc_result.get("flags", []),
        "md_path": doc_result.get("md_path"),
        "json_path": doc_result.get("json_path"),
    }


def write_review(out_dir: Path, entries: list[dict[str, Any]],
                 details: dict[str, dict[str, Any]]) -> Path:
    """生成人工复核清单，按 P0/P1/P2 分级。"""
    p0, p1, p2 = [], [], []

    for e in entries:
        d = details.get(e["file"], {})
        flags = e.get("flags", [])
        name = Path(e["file"]).name

        for f in flags:
            if f.startswith("missing:") or f in ("arithmetic_mismatch", "case_mismatch",
                                                 "invoice_no_invalid", "clause_split_failed",
                                                 "parties_incomplete"):
                p0.append(f"- `{name}` — {_flag_cn(f)}")
            elif f.startswith("low_confidence:") or f in ("checksum_failed", "date_out_of_range",
                                                          "items_sum_mismatch", "seal_missing",
                                                          "sign_date_missing"):
                p1.append(f"- `{name}` — {_flag_cn(f)}")
            elif f in ("same_party", "amount_candidates", "duplicate_invoice", "name_drift"):
                p2.append(f"- `{name}` — {_flag_cn(f)}")

    lines = [
        "# 人工复核清单",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}　"
        f"文档数：{len(entries)}　需复核：{sum(1 for e in entries if e.get('needs_review'))}",
        "",
        "## P0 · 必须核对（不核对则结论不可用）",
        "",
        *(sorted(set(p0)) or ["（无）"]),
        "",
        "## P1 · 建议核对（低置信度 / 格式异常）",
        "",
        *(sorted(set(p1)) or ["（无）"]),
        "",
        "## P2 · 提示（关注项，非错误）",
        "",
        *(sorted(set(p2)) or ["（无）"]),
        "",
        "---",
        "",
        "**复核原则**：本清单由确定性规则生成，只做标记不做修正。"
        "P0 项必须回原页核对后再用于审计底稿。",
    ]
    p = out_dir / "_review.md"
    write_text(p, "\n".join(lines))
    return p


_FLAG_CN = {
    "arithmetic_mismatch": "金额勾稽失败（不含税+税额≠价税合计）",
    "case_mismatch": "金额大小写不一致",
    "invoice_no_invalid": "发票号码位数异常",
    "checksum_failed": "纳税人识别号校验位不通过",
    "date_out_of_range": "日期超出合理区间",
    "items_sum_mismatch": "明细合计与总额不符",
    "same_party": "购销方同名（关联交易或识别错误）",
    "clause_split_failed": "合同条款切分失败，已降级为段落结构",
    "parties_incomplete": "合同当事人不足两方",
    "seal_missing": "未检出签章",
    "sign_date_missing": "未识别到签订日期",
    "amount_candidates": "合同存在多个金额候选，未择一",
    "duplicate_invoice": "同批次发票号重复",
    "name_drift": "同一税号对应多个名称",
}


def _flag_cn(flag: str) -> str:
    if flag.startswith("missing:"):
        return f"必填字段缺失：{flag.split(':', 1)[1]}"
    if flag.startswith("low_confidence:"):
        return f"低置信度字段：{flag.split(':', 1)[1]}"
    return _FLAG_CN.get(flag, flag)
