"""文件归一化：PDF/图片 → 页图 + 可选文本层。

核心优化：**PDF 有文本层时优先直读，不走 OCR**。
电子发票、电子合同的 PDF 绝大多数带文本层，直读准确率 100%、速度快两个数量级。
只有扫描件（无文本层）才回落 OCR。
"""
from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PDF_EXT = {".pdf"}

# 低于该宽度视为低分辨率，需要放大
MIN_WIDTH = 1200


@dataclass
class Page:
    index: int                      # 从 1 开始
    image: Any = None               # PIL.Image（文本层路径为 None，省去渲染开销）
    text_layer: str | None = None   # PDF 文本层全文
    text_lines: list = field(default_factory=list)  # 文本层带真实坐标的行
    width: int = 0
    height: int = 0
    dpi: int = 0
    source: str = ""                # "text_layer" | "ocr"
    scale_applied: float = 1.0
    extra: dict = field(default_factory=dict)


@dataclass
class Document:
    path: Path
    pages: list[Page]
    has_text_layer: bool
    file_hash: str
    kind: str                       # pdf | image


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load(path: str | Path, dpi: int = 200, force_ocr: bool = False,
         max_pages: int | None = None) -> Document:
    """加载文件为页列表。PDF 自动判断有无文本层。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    ext = p.suffix.lower()

    if ext in PDF_EXT:
        return _load_pdf(p, dpi=dpi, force_ocr=force_ocr, max_pages=max_pages)
    if ext in IMAGE_EXT:
        return _load_image(p, force_ocr=force_ocr)
    raise ValueError(f"不支持的文件类型: {ext}")


def _load_pdf(p: Path, dpi: int, force_ocr: bool, max_pages: int | None) -> Document:
    try:
        import pymupdf as fitz          # PyMuPDF >= 1.24 推荐写法
    except ImportError:
        try:
            import fitz                  # 旧版回退
        except ImportError as e:
            raise RuntimeError("缺少 PyMuPDF，请执行 pip install pymupdf") from e

    doc = fitz.open(str(p))
    pages: list[Page] = []
    n = len(doc) if max_pages is None else min(len(doc), max_pages)

    # 先探测文本层质量
    text_chars = 0
    for i in range(min(n, 5)):
        text_chars += len((doc[i].get_text("text") or "").strip())
    has_text_layer = (not force_ocr) and text_chars >= 20 * min(n, 5)

    for i in range(n):
        pg = doc[i]
        if has_text_layer:
            txt = (pg.get_text("text") or "").strip()
            if len(txt) >= 10:
                # 有文本层：**不渲染图片**。电子发票/电子合同的版面已由文本顺序表达，
                # 渲染一页 200dpi 约 0.2~0.5s，跳过它能让整份 PDF 快一个数量级。
                pages.append(Page(index=i + 1, image=None, text_layer=txt,
                                  text_lines=_extract_text_lines(pg, i + 1),
                                  width=int(pg.rect.width), height=int(pg.rect.height),
                                  dpi=dpi, source="text_layer"))
                continue
        pix = pg.get_pixmap(dpi=dpi)
        img = _pix_to_pil(pix)
        img, scale = _maybe_upscale(img)
        pages.append(Page(index=i + 1, image=img, text_layer=None,
                          width=img.width, height=img.height, dpi=dpi,
                          source="ocr", scale_applied=scale))
    doc.close()

    return Document(path=p, pages=pages, has_text_layer=has_text_layer,
                    file_hash=sha256_file(p), kind="pdf")


def _load_image(p: Path, force_ocr: bool) -> Document:
    from PIL import Image
    img = Image.open(p)
    img = img.convert("RGB")
    img, scale = _maybe_upscale(img)
    page = Page(index=1, image=img, text_layer=None, width=img.width,
                height=img.height, dpi=0, source="ocr", scale_applied=scale)
    return Document(path=p, pages=[page], has_text_layer=False,
                    file_hash=sha256_file(p), kind="image")


def _pix_to_pil(pix):
    from PIL import Image
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def _maybe_upscale(img):
    """低分辨率页放大，显著提升 OCR 精度。"""
    from PIL import Image
    w, h = img.size
    if w >= MIN_WIDTH:
        return img, 1.0
    scale = min(3.0, MIN_WIDTH / max(w, 1))
    nw, nh = int(w * scale), int(h * scale)
    return img.resize((nw, nh), Image.LANCZOS), round(scale, 2)


def _extract_text_lines(pg, page_no: int) -> list[dict[str, Any]]:
    """PDF 文本层 → 带真实坐标的行。

    用 words 级坐标按 (block, line) 聚合成行，行内按 x 排序后拼接，
    这样后续条款切分、字段溯源都能定位到原页。
    """
    out: list[dict[str, Any]] = []
    try:
        words = pg.get_text("words")  # (x0,y0,x1,y1,word,block,line,word_no)
    except Exception:
        return out
    buckets: dict[tuple, list] = {}
    for w in words:
        x0, y0, x1, y1, txt, bno, lno = w[0], w[1], w[2], w[3], w[4], w[5], w[6]
        if not str(txt).strip():
            continue
        buckets.setdefault((bno, lno), []).append((x0, y0, x1, y1, str(txt)))
    for (bno, lno), ws in buckets.items():
        ws.sort(key=lambda t: t[0])
        text = "".join(t[4] for t in ws)
        out.append({
            "text": text,
            "score": 1.0,                       # 文本层非识别结果，无不确定性
            "page": page_no,
            "bbox": [int(min(t[0] for t in ws)), int(min(t[1] for t in ws)),
                     int(max(t[2] for t in ws)), int(max(t[3] for t in ws))],
        })
    out.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    return out


def iter_files(root: str | Path, recursive: bool = True) -> list[Path]:
    """收集目录下可处理文件。"""
    root = Path(root)
    if root.is_file():
        return [root]
    out: list[Path] = []
    it = root.rglob("*") if recursive else root.glob("*")
    for f in it:
        if f.suffix.lower() in IMAGE_EXT | PDF_EXT and f.is_file():
            out.append(f)
    return sorted(out)
