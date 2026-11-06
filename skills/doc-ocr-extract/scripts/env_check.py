#!/usr/bin/env python
"""环境自检 —— 运行识别前先跑这个。

检查：Python 版本、PaddlePaddle、GPU 可用性、PaddleOCR、PyMuPDF、模型缓存、显存余量。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

OK, WARN, FAIL = "[OK]  ", "[警告]", "[失败]"


def _line(status: str, msg: str) -> None:
    print(f"{status} {msg}")


def check_python() -> bool:
    v = sys.version_info
    if (3, 10) <= (v.major, v.minor) <= (3, 12):
        _line(OK, f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    if (v.major, v.minor) > (3, 12):
        _line(WARN, f"Python {v.major}.{v.minor} —— PaddlePaddle 官方支持 3.10–3.12，"
                    f"更高版本可能装不上，建议改用 3.12")
    else:
        _line(FAIL, f"Python {v.major}.{v.minor} —— 需要 3.10 以上")
    return False


def check_paddle() -> bool:
    try:
        import paddle
    except ImportError:
        _line(FAIL, "未安装 PaddlePaddle —— pip install paddlepaddle-gpu==3.4.0 "
                    "--index-url https://www.paddlepaddle.org.cn/packages/stable/cu129/")
        return False
    _line(OK, f"PaddlePaddle {paddle.__version__}")

    if not paddle.is_compiled_with_cuda():
        _line(WARN, "当前为 CPU 版 PaddlePaddle —— 可运行，但扫描件约慢 4–8 倍")
        return True

    n = paddle.device.cuda.device_count()
    if n == 0:
        _line(WARN, "CUDA 版已装但未检测到 GPU —— 将回退 CPU")
        return True
    _line(OK, f"GPU 数量 {n}")

    # 显存余量
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        for row in out.stdout.strip().splitlines():
            parts = [p.strip() for p in row.split(",")]
            if len(parts) >= 4:
                name, total, used, free = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
                msg = f"{name}  总 {total}MB / 已用 {used}MB / 空闲 {free}MB"
                if free < 1500:
                    _line(WARN, msg + "  ← 空闲显存偏低，建议关闭其他 GPU 程序")
                else:
                    _line(OK, msg)
    except Exception:
        pass
    return True


def check_paddleocr() -> bool:
    try:
        import paddleocr
        _line(OK, f"PaddleOCR {paddleocr.__version__}")
        return True
    except ImportError:
        _line(FAIL, "未安装 PaddleOCR —— pip install paddleocr==3.7.0")
        return False


def check_pymupdf() -> bool:
    try:
        import pymupdf
        _line(OK, f"PyMuPDF {pymupdf.__version__}")
        return True
    except ImportError:
        try:
            import fitz  # noqa: F401
            _line(OK, "PyMuPDF（旧版 fitz 接口）")
            return True
        except ImportError:
            _line(FAIL, "未安装 PyMuPDF —— pip install pymupdf")
            return False


def check_models() -> None:
    home = Path(os.path.expanduser("~")) / ".paddlex" / "official_models"
    if not home.exists():
        _line(WARN, f"模型缓存目录不存在（{home}）—— 首次识别会自动下载约 140MB")
        return
    found = [d.name for d in home.iterdir() if d.is_dir()]
    ocr_models = [d for d in found if "OCR" in d]
    if ocr_models:
        _line(OK, f"已缓存模型：{', '.join(sorted(ocr_models))}")
    else:
        _line(WARN, "尚未下载 OCR 模型 —— 首次识别会自动下载")


def check_engine() -> None:
    """尝试真正初始化一次 OCR 引擎（最硬的验证）。"""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from ocr_core import engine
        dev = engine.resolve(None)
        _line(OK, f"引擎设备解析：{dev}")
    except Exception as e:
        _line(WARN, f"引擎自检跳过：{type(e).__name__}: {e}")


def main() -> int:
    print("=" * 62)
    print("审小牛 · 文档识别与结构化 —— 环境自检")
    print("=" * 62)

    results = [check_python(), check_paddle(), check_paddleocr(), check_pymupdf()]
    check_models()
    check_engine()

    print("-" * 62)
    if all(results):
        print("结论：环境就绪，可以运行 scripts/run_ocr.py")
        return 0
    print("结论：存在缺失项，请按上面的提示补齐后再运行")
    return 1


if __name__ == "__main__":
    sys.exit(main())
