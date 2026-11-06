"""PaddleOCR 引擎封装 —— 延迟加载、单例复用、GPU/CPU 自适应。

对外统一输出标准化文本行：
    {"text": str, "score": float, "page": int, "bbox": [x1,y1,x2,y2]}
"""
from __future__ import annotations

import os
import threading
from typing import Any

_LOCK = threading.Lock()
_OCR_ENGINE = None
_LAYOUT_ENGINE = None
_DEVICE = None


def pick_device(prefer: str = "auto") -> str:
    """auto → 有 GPU 用 GPU，否则 CPU。"""
    if prefer in ("gpu", "cpu"):
        return prefer
    try:
        import paddle
        if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu"
    except Exception:
        pass
    return "cpu"


def get_device() -> str:
    global _DEVICE
    if _DEVICE is None:
        _DEVICE = pick_device(os.environ.get("OCR_DEVICE", "auto"))
    return _DEVICE


def resolve(device: str | None = None) -> str:
    """把 auto/None/gpu/cpu 统一解析成 paddle 可接受的设备串。"""
    d = device or os.environ.get("OCR_DEVICE", "auto")
    if d in (None, "", "auto"):
        return get_device()
    if d == "gpu":
        return "gpu:0"
    return d


def get_ocr(device: str | None = None, lang: str = "ch"):
    """单例 OCR 引擎（检测 + 文字识别）。"""
    global _OCR_ENGINE
    with _LOCK:
        if _OCR_ENGINE is None:
            from paddleocr import PaddleOCR
            dev = resolve(device)
            _OCR_ENGINE = PaddleOCR(
                lang=lang,
                device=dev,
                # 发票/票据版式固定，关掉方向分类与矫正可省 30%+ 耗时；
                # 手机拍照件需要时可置 True
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
    return _OCR_ENGINE


def get_layout(device: str | None = None):
    """单例版面分析引擎（PP-StructureV3，仅合同/对账单需要）。"""
    global _LAYOUT_ENGINE
    with _LOCK:
        if _LAYOUT_ENGINE is None:
            from paddleocr import PPStructureV3
            dev = resolve(device)
            _LAYOUT_ENGINE = PPStructureV3(
                device=dev,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
            )
    return _LAYOUT_ENGINE


# ---------------------------------------------------------------- 结果归一化

def _bbox_from_poly(poly: Any) -> list[int]:
    """四点多边形 → [x1,y1,x2,y2]。"""
    try:
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
    except Exception:
        return [0, 0, 0, 0]


def _to_bbox(bb: Any) -> list[int]:
    """统一把 rec_boxes[i] / dt_polys[i] 转成 [x1,y1,x2,y2]。

    注意：rec_boxes 是 numpy.ndarray(N,4)，其元素也是 ndarray，
    不能用 isinstance(x, list/tuple) 判断。
    """
    try:
        vals = list(bb)
    except TypeError:
        return [0, 0, 0, 0]
    # 扁平 4 标量 → 已是 [x1,y1,x2,y2]
    if len(vals) == 4 and all(not hasattr(v, "__len__") for v in vals):
        try:
            return [int(float(v)) for v in vals]
        except (TypeError, ValueError):
            return [0, 0, 0, 0]
    # 否则按多边形处理
    return _bbox_from_poly(vals)


def _to_dict(res: Any) -> dict:
    """OCRResult → 普通 dict，兼容不同版本。"""
    if isinstance(res, dict):
        return res
    for attr in ("json", "res"):
        v = getattr(res, attr, None)
        if isinstance(v, dict):
            return v.get("res", v) if "res" in v else v
    try:
        return dict(res)
    except Exception:
        return {}


def _first_seq(d: dict, keys: tuple[str, ...]):
    """取第一个非空的序列字段。numpy 数组不能用 `or` 判真值。"""
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        try:
            if len(v) == 0:
                continue
        except TypeError:
            continue
        return v
    return []


def normalize_ocr_result(res: Any, page: int) -> list[dict[str, Any]]:
    """把 PaddleOCR 的 OCRResult 转成标准文本行列表。"""
    d = _to_dict(res)
    texts = _first_seq(d, ("rec_texts",))
    scores = _first_seq(d, ("rec_scores",))
    boxes = _first_seq(d, ("rec_boxes", "dt_polys"))
    out: list[dict[str, Any]] = []
    for i, t in enumerate(texts):
        if not t or not str(t).strip():
            continue
        sc = float(scores[i]) if i < len(scores) else 0.0
        bb = boxes[i] if i < len(boxes) else [0, 0, 0, 0]
        out.append({"text": str(t).strip(), "score": round(sc, 4),
                    "page": page, "bbox": _to_bbox(bb)})
    return out


def ocr_image(img, page: int = 1, device: str | None = None) -> list[dict[str, Any]]:
    """对单页 PIL 图像做检测+识别。"""
    engine = get_ocr(device)
    import numpy as np
    arr = np.array(img.convert("RGB"))
    results = engine.predict(arr)
    lines: list[dict[str, Any]] = []
    for r in results:
        lines.extend(normalize_ocr_result(r, page))
    return lines


def layout_image(img, page: int = 1, device: str | None = None) -> dict[str, Any]:
    """版面分析，返回 markdown + 块列表（含 seal 检测）。"""
    engine = get_layout(device)
    import numpy as np
    arr = np.array(img.convert("RGB"))
    results = engine.predict(arr)
    md_parts: list[str] = []
    blocks: list[dict[str, Any]] = []
    for r in results:
        d = _to_dict(r)
        md = d.get("markdown") or {}
        if isinstance(md, dict):
            txt = md.get("markdown_texts") or md.get("text") or ""
        else:
            txt = str(md)
        if txt:
            md_parts.append(txt)
        for blk in (d.get("parsing_res_list") or []):
            bd = blk if isinstance(blk, dict) else _to_dict(blk)
            blocks.append({
                "label": bd.get("block_label") or bd.get("label"),
                "content": bd.get("block_content") or bd.get("content"),
                "bbox": bd.get("block_bbox") or bd.get("bbox"),
            })
    return {"markdown": "\n\n".join(md_parts), "blocks": blocks}


def warmup(device: str | None = None) -> str:
    """预热：加载模型 + 跑一次空推理，避免首次调用超时。"""
    dev = resolve(device)
    get_ocr(dev)
    return dev
