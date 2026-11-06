#!/usr/bin/env python
"""审小牛 · 文档识别与结构化 —— 主入口。

用法：
    python run_ocr.py <文件或目录> [-o 输出目录] [--type auto|invoice|contract|receipt|generic]
                       [--device auto|gpu|cpu] [--dpi 200] [--no-cache] [--quiet]

输出（默认 <输入同级>/ocr-output/）：
    <文件名>.md          版面还原的 Markdown（带页码标记、低置信度行前缀 [?]）
    <文件名>.json        结构化字段（每个字段带 page/bbox/raw_text 溯源）
    <文件名>.lines.json  原始文本行（调试与二次抽取用）
    _index.json          批次索引（供其他审小牛技能消费）
    _review.md           人工复核清单（P0/P1/P2）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

# 允许直接以脚本方式运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ocr_core import classify, engine, extract_contract, extract_invoice, loader, writer
from ocr_core.validate import cn_amount_to_number

VERSION = "1.0.0"
CACHE_DIR_NAME = ".ocr-cache"


# ---------------------------------------------------------------- 缓存

def _cache_key(doc: loader.Document, mode: str) -> str:
    return hashlib.sha256(f"{doc.file_hash}:{mode}:{VERSION}".encode()).hexdigest()[:32]


def _cache_get(cache_dir: Path, key: str) -> list[dict] | None:
    p = cache_dir / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_put(cache_dir: Path, key: str, lines: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(
        json.dumps(lines, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- 单文件处理

def process_file(path: Path, out_dir: Path, force_type: str = "auto",
                 device: str = "auto", dpi: int = 200,
                 use_cache: bool = True, quiet: bool = False) -> dict[str, Any]:
    t0 = time.time()
    doc = loader.load(path, dpi=dpi)

    mode = "text_layer" if doc.has_text_layer else "ocr"
    key = _cache_key(doc, mode)
    cache_dir = out_dir / CACHE_DIR_NAME

    lines: list[dict] = []
    if use_cache:
        cached = _cache_get(cache_dir, key)
        if cached:
            lines = cached
            if not quiet:
                print(f"    [cache] {len(lines)} 行")

    if not lines:
        if doc.has_text_layer:
            lines = _lines_from_text_layer(doc)
        else:
            for page in doc.pages:
                lines.extend(engine.ocr_image(page.image, page=page.index, device=device))
        if use_cache and lines:
            _cache_put(cache_dir, key, lines)

    # 重复页检测（扫描重复进纸 / PDF 合并重复页）
    dup_pages: set[int] = set()
    if len(doc.pages) > 1:
        dup_pages = _detect_duplicate_pages(lines)
        if dup_pages:
            lines = [l for l in lines if l.get("page", 1) not in dup_pages]

    # 页眉页脚剔除（多页时；首页首部保留，避免把文档标题误删）
    if len(doc.pages) > 1:
        per_page = _split_by_page(lines)
        repeated = classify.detect_repeated_lines(list(per_page.values()))
        kept: list[dict] = []
        for l in lines:
            pg = l.get("page", 1)
            if pg == 1 and _is_leading(l, per_page.get(1, [])):
                kept.append(l)      # 首页标题区不做页眉剔除
                continue
            if classify.is_page_furniture(l.get("text", ""), pg, len(doc.pages), repeated):
                continue
            kept.append(l)
        lines = kept
    lines.sort(key=lambda l: (l.get("page", 1), (l.get("bbox") or [0, 0, 0, 0])[1],
                              (l.get("bbox") or [0, 0, 0, 0])[0]))

    # 分类
    cls = classify.classify_texts(lines)
    doc_type = force_type if force_type != "auto" else cls["type"]

    # 抽取
    if doc_type == "vat_invoice":
        ext = extract_invoice.extract(lines)
    elif doc_type == "contract":
        ext = extract_contract.extract(lines)
    else:
        ext = {"type": doc_type, "flags": [], "grade": "B", "needs_review": False}

    # Markdown
    md = writer.lines_to_markdown(lines)
    stem = path.stem
    md_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    lines_path = out_dir / f"{stem}.lines.json"

    elapsed = round(time.time() - t0, 2)
    flags = list(ext.get("flags", []))
    if dup_pages:
        flags.append("duplicate_pages_removed")
    result: dict[str, Any] = {
        "file": str(path),
        "file_name": path.name,
        "type": doc_type,
        "type_confidence": cls["confidence"],
        "type_ambiguous": cls["ambiguous"],
        "type_scores": cls["scores"],
        "forced_type": force_type != "auto",
        "engine": "pdf_text_layer" if doc.has_text_layer else f"paddleocr_{engine.get_device()}",
        "pages": len(doc.pages),
        "duplicate_pages": sorted(dup_pages),
        "lines": len(lines),
        "elapsed_sec": elapsed,
        "ocr_version": VERSION,
        "summary": _summarize(doc_type, ext),
        "flags": sorted(set(flags)),
        "grade": ext.get("grade"),
        "needs_review": ext.get("needs_review"),
        "detail": ext,
        "md_path": str(md_path),
        "json_path": str(json_path),
    }

    writer.write_text(md_path, md)
    writer.write_json(json_path, result)
    writer.write_json(lines_path, lines)
    return result


def _lines_from_text_layer(doc: loader.Document) -> list[dict[str, Any]]:
    """PDF 文本层 → 标准行（带真实坐标）。"""
    out: list[dict[str, Any]] = []
    for page in doc.pages:
        if page.text_lines:
            out.extend(page.text_lines)
        elif page.text_layer:
            y = 0
            for raw in page.text_layer.split("\n"):
                t = raw.strip()
                if not t:
                    y += 10
                    continue
                out.append({"text": t, "score": 1.0, "page": page.index,
                            "bbox": [0, y, 0, y + 8]})
                y += 10
    return out


def _split_by_page(lines: list[dict]) -> dict[int, list[dict]]:
    d: dict[int, list[dict]] = {}
    for l in lines:
        d.setdefault(l.get("page", 1), []).append(l)
    return d


def _is_leading(line: dict, page_lines: list[dict], top_n: int = 3) -> bool:
    """判断该行是否属于页面首部（文档标题区）。"""
    if not page_lines:
        return False
    ordered = sorted(page_lines, key=lambda l: ((l.get("bbox") or [0, 0, 0, 0])[1],
                                                (l.get("bbox") or [0, 0, 0, 0])[0]))
    return any(l is line for l in ordered[:top_n])


def _detect_duplicate_pages(lines: list[dict], threshold: float = 0.85,
                            min_lines: int = 5) -> set[int]:
    """检测内容高度重复的页（扫描重复进纸 / PDF 合并重复）。

    只保留首次出现，后续重复页整页丢弃。
    阈值取 0.85 而非 0.95：重复页的页码行必然不同，纯 Jaccard 会被页码拉低。
    同时要求每页至少 min_lines 行，避免空白页/封面页被误判为重复。
    """
    per_page = _split_by_page(lines)
    if len(per_page) < 2:
        return set()

    sigs: dict[int, set[str]] = {}
    for pg, ls in per_page.items():
        sigs[pg] = {l.get("text", "").strip() for l in ls if len(l.get("text", "").strip()) >= 4}

    dups: set[int] = set()
    pages = sorted(sigs)
    for i, p in enumerate(pages):
        if p in dups or len(sigs[p]) < min_lines:
            continue
        for q in pages[i + 1:]:
            if q in dups or len(sigs[q]) < min_lines:
                continue
            inter = len(sigs[p] & sigs[q])
            union = len(sigs[p] | sigs[q])
            if union and inter >= min_lines and inter / union >= threshold:
                dups.add(q)
    return dups


def _summarize(doc_type: str, ext: dict[str, Any]) -> dict[str, Any]:
    if doc_type == "vat_invoice":
        f = ext.get("fields", {})

        def v(k):
            x = f.get(k, {}).get("value")
            return x

        return {
            "invoice_no": v("invoice_no"),
            "invoice_date": v("invoice_date"),
            "seller": v("seller_name"),
            "buyer": v("buyer_name"),
            "total": v("total_amount"),
            "arithmetic_ok": (ext.get("checks") or {}).get("arithmetic", {}).get("ok"),
            "items": len(ext.get("items") or []),
        }
    if doc_type == "contract":
        m, kt = ext.get("meta", {}), ext.get("key_terms", {})
        return {
            "title": m.get("title"),
            "contract_no": m.get("contract_no"),
            "sign_date": m.get("sign_date"),
            "amount": kt.get("contract_amount"),
            "amount_is_estimate": kt.get("amount_is_estimate"),
            "parties": [p.get("name") for p in ext.get("parties", [])],
            "clauses": len(ext.get("clauses") or []),
        }
    return {"chars": None}


# ---------------------------------------------------------------- 批次

def run(input_path: str, out: str | None, **kw) -> int:
    src = Path(input_path)
    if not src.exists():
        print(f"[错误] 路径不存在: {src}", file=sys.stderr)
        return 2

    files = loader.iter_files(src)
    if not files:
        print(f"[错误] 未找到可处理文件（PDF/图片）: {src}", file=sys.stderr)
        return 2

    out_dir = Path(out) if out else (src.parent if src.is_file() else src) / "ocr-output"
    out_dir.mkdir(parents=True, exist_ok=True)

    quiet = kw.get("quiet", False)
    print(f"输入 {len(files)} 个文件 → {out_dir}")
    if not quiet:
        print(f"设备: {engine.get_device()}  缓存: {'开' if kw.get('use_cache', True) else '关'}")

    # 预热（GPU 首次加载模型较慢，单独计时）
    t_warm = time.time()
    if not quiet:
        print("预热引擎…", end="", flush=True)
    dev = engine.warmup(kw.get("device", "auto"))
    if not quiet:
        print(f" {time.time() - t_warm:.1f}s（{dev}）")

    entries: list[dict] = []
    details: dict[str, dict] = {}
    t0 = time.time()

    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {f.name}", flush=True)
        try:
            r = process_file(f, out_dir, force_type=kw.get("force_type", "auto"),
                             device=kw.get("device", "auto"), dpi=kw.get("dpi", 200),
                             use_cache=kw.get("use_cache", True), quiet=quiet)
        except Exception as e:
            print(f"    [失败] {type(e).__name__}: {e}", file=sys.stderr)
            entries.append({"file": str(f), "type": "error", "flags": ["process_failed"],
                            "grade": "D", "needs_review": True, "summary": {"error": str(e)}})
            continue

        entries.append(writer.build_index_entry(r))
        details[str(f)] = r
        s = r.get("summary") or {}
        brief = s.get("invoice_no") or s.get("contract_no") or s.get("title") or "-"
        print(f"    {r['type']} · {r['grade']}级 · {r['elapsed_sec']}s · {brief}"
              + ("  ⚠需复核" if r.get("needs_review") else ""), flush=True)

    total = round(time.time() - t0, 2)

    # 跨文档校验
    anomalies = _cross_doc_check(entries, details)

    index = {
        "version": VERSION,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input": str(src),
        "out_dir": str(out_dir),
        "device": dev,
        "total_files": len(files),
        "total_sec": total,
        "avg_sec": round(total / max(len(files), 1), 2),
        "documents": entries,
        "anomalies": anomalies,
    }
    writer.write_json(out_dir / "_index.json", index)
    review_path = writer.write_review(out_dir, entries, details)

    need = sum(1 for e in entries if e.get("needs_review"))
    print(f"\n完成：{len(files)} 文件 / {total}s（均 {index['avg_sec']}s）")
    print(f"  需人工复核：{need}")
    if anomalies:
        print(f"  跨文档异常：{len(anomalies)} 项")
    print(f"  索引：{out_dir / '_index.json'}")
    print(f"  复核清单：{review_path}")
    return 0


def _cross_doc_check(entries: list[dict], details: dict[str, dict]) -> list[dict]:
    """跨文档校验：发票号重复、税号名称漂移。"""
    anomalies: list[dict] = []

    inv: dict[str, list[str]] = {}
    tax_names: dict[str, set[str]] = {}
    for e in entries:
        if e.get("type") != "vat_invoice":
            continue
        d = details.get(e["file"], {})
        f = (d.get("detail") or {}).get("fields") or {}
        no = (f.get("invoice_no") or {}).get("value")
        if no:
            inv.setdefault(str(no), []).append(e["file"])
        for key in ("seller_name", "buyer_name"):
            name = (f.get(key) or {}).get("value")
            tid = (f.get(key.replace("_name", "_tax_id")) or {}).get("value")
            if name and tid:
                tax_names.setdefault(str(tid), set()).add(str(name))

    for no, fs in inv.items():
        if len(fs) > 1:
            anomalies.append({"type": "duplicate_invoice", "invoice_no": no, "files": fs})
    for tid, names in tax_names.items():
        if len(names) > 1:
            anomalies.append({"type": "name_drift", "tax_id": tid, "names": sorted(names)})
    return anomalies


def main() -> int:
    ap = argparse.ArgumentParser(
        description="审小牛 · 文档识别与结构化（合同/发票/票据 → Markdown + JSON）")
    ap.add_argument("input", help="文件或目录")
    ap.add_argument("-o", "--out", help="输出目录（默认 <输入>/ocr-output）")
    ap.add_argument("--type", default="auto",
                    choices=["auto", "invoice", "contract", "receipt", "generic"],
                    help="强制文档类型（默认 auto 自动判别）")
    ap.add_argument("--device", default="auto", choices=["auto", "gpu", "cpu"])
    ap.add_argument("--dpi", type=int, default=200, help="PDF 渲染 DPI（默认 200）")
    ap.add_argument("--no-cache", action="store_true", help="禁用结果缓存")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    a = ap.parse_args()

    return run(a.input, a.out, force_type=a.type, device=a.device, dpi=a.dpi,
               use_cache=not a.no_cache, quiet=a.quiet)


if __name__ == "__main__":
    sys.exit(main())
