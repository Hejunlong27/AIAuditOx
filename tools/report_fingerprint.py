#!/usr/bin/env python3
"""Print or compare structural fingerprints for xlsx/docx deliverables."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _project_root_default() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_api(project_root: Path):
    src = project_root / "skill-tools" / "auditox-python-core" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from auditox_common.office_fingerprint import (
        diff_fingerprints,
        fingerprint_docx,
        fingerprint_xlsx,
    )

    return fingerprint_xlsx, fingerprint_docx, diff_fingerprints


def fingerprint(path: Path):
    suffix = path.suffix.lower()
    project_root = _project_root_default()
    fingerprint_xlsx, fingerprint_docx, _diff = _load_api(project_root)
    if suffix == ".xlsx":
        return fingerprint_xlsx(path)
    if suffix == ".docx":
        return fingerprint_docx(path)
    raise ValueError(f"不支持的文件类型：{path.suffix}（仅 .xlsx/.docx）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成或比较 xlsx/docx 结构指纹")
    parser.add_argument("path", type=Path, help="基线文件")
    parser.add_argument("--diff", type=Path, help="与基线比较的新文件")
    args = parser.parse_args(argv)

    baseline = fingerprint(args.path)
    if args.diff is None:
        print(json.dumps(baseline, ensure_ascii=False, indent=2, default=str))
        return 0
    current = fingerprint(args.diff)
    _xlsx, _docx, diff_fingerprints = _load_api(_project_root_default())
    differences = diff_fingerprints(baseline, current)
    print(json.dumps(differences, ensure_ascii=False, indent=2, default=str))
    return 0 if not differences else 1


if __name__ == "__main__":
    raise SystemExit(main())
