#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 downloads.json 的 SkillHub 标注切到个人账户（slug 加 aiauditox- 前缀）。

用法：
    python switch_downloads.py --dry-run
    python switch_downloads.py
"""

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path("D:/w.ai/2026-09-23-00-03-11")
DL = ROOT / "data" / "downloads.json"
PREFIX = "aiauditox-"

# 新增条目：这两个此前没有下载条目
NEW_ENTRIES = {
    "confirmation-address-auditor": {
        "provider": "quark",
        "url": "",
        "code": "",
        "size": "",
        "format": ".zip（SKILL.md + scripts/ + references/ + assets/）",
        "note": "六阶段闭环：多格式读取 → 名称地址标准化 → 三级匹配 → 逐项差异比对 → 风险识别与审计判断 → 输出核对记录表与底稿。",
    },
    "doc-ocr-extract": {
        "provider": "quark",
        "url": "",
        "code": "",
        "size": "618 KB",
        "format": ".zip（SKILL.md + scripts/ 7 个模块 + rules/ 4 份规则 + samples/ 脱敏样例 + tests/）",
        "note": "PDF 文本层直读与扫描件 OCR 双引擎；发票 16 字段带坐标溯源；合同条款切分；全程本地推理。",
    },
}


def fetch_published(handle="indiv-27"):
    """拉个人账户已上架的 slug 集合（归一化去掉前缀）。"""
    import urllib.request
    url = f"https://api.skillhub.cn/api/v1/users/{handle}/skills?page=1&pageSize=100"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AuditOx-site/1.0)",
        "Referer": "https://skillhub.cn/",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    items = data.get("skills") or data.get("items") or []
    out = set()
    for it in items:
        s = str(it.get("slug") or "")
        if s.startswith(PREFIX):
            out.add(s[len(PREFIX):])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-api", action="store_true", help="不查平台，直接按本地条目改")
    args = ap.parse_args()

    published = None
    if not args.no_api:
        try:
            published = fetch_published()
            print(f"平台已上架 {len(published)} 个（{PREFIX}*）")
        except Exception as e:
            print(f"! 拉取平台列表失败：{e}；改为按本地条目处理")
            published = None

    data = json.loads(DL.read_text(encoding="utf-8"))
    changed = []
    skipped = []

    for key, val in data.items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        sh = val.get("skillhub")
        if not isinstance(sh, dict):
            continue
        slug = str(sh.get("slug") or "")
        if slug and not slug.startswith(PREFIX):
            sh["slug"] = PREFIX + slug
            changed.append(f"{key}: slug -> {sh['slug']}")
        # 企业 team-skills 详情页会失效，改为按全局模板生成
        if "url" in sh:
            sh.pop("url")
            changed.append(f"{key}: 移除 skillhub.url 覆盖")

    for key, entry in NEW_ENTRIES.items():
        if key not in data:
            data[key] = dict(entry)
            data[key]["skillhub"] = {"slug": PREFIX + key}
            changed.append(f"{key}: 新增条目")

    # 补 skillhub 字段：只补平台确实已上架的，避免把未发布的标成已上架
    for key, val in data.items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        if val.get("skillhub"):
            continue
        if published is None or key in published:
            val["skillhub"] = {"slug": PREFIX + key}
            changed.append(f"{key}: 补 skillhub 字段")
        else:
            skipped.append(key)

    print(f"计划改动 {len(changed)} 处")
    for c in changed:
        print("  " + c)
    if skipped:
        print(f"跳过（平台未上架，保持未上架态）：{', '.join(skipped)}")

    if args.dry_run:
        print("\n[dry-run] 未写入")
        return

    DL.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写入 {DL}")


if __name__ == "__main__":
    main()
