#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 skills/ 生成 registry/skills.json —— agent 发现技能的索引入口。

用法：
    python tools/build_index.py            # 生成索引
    python tools/build_index.py --check    # 只校验不写文件（CI 用）
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
OUT = ROOT / "registry" / "skills.json"

SKIP = {"_index", "_templates", "__pycache__", ".pytest_cache", "output", ".git", ".github"}


def parse_frontmatter(text: str) -> dict:
    """极简 YAML frontmatter 解析：只取顶层 key: value，够用且零依赖。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data, key = {}, None
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1] not in (" ", "\t") and ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if val[:1] in ("'", '"') and val[-1:] == val[:1]:
                val = val[1:-1]
            data[key] = val
        elif key and line[:1] in (" ", "\t"):
            data[key] = (data.get(key, "") + " " + line.strip()).strip()
    return data


def detect_variant(pkg: Path) -> str:
    """按结构判别形态，不靠包名约定。"""
    if (pkg / "roles").is_dir():
        return "orchestrator"
    if (pkg / "scripts").is_dir():
        return "tool"
    if (pkg / "procedures").is_dir():
        return "skill-group"
    return "standard"  # 只有 SKILL.md + dsl.json + templates，如底稿制式规范


def count_files(d: Path, pattern: str = "*") -> int:
    return sum(1 for p in d.rglob(pattern) if p.is_file()) if d.is_dir() else 0


def build_one(pkg: Path, *, path_prefix: str = "skills") -> dict:
    skill_md = pkg / "SKILL.md"
    meta = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace")) if skill_md.exists() else {}
    variant = detect_variant(pkg)
    item = {
        "id": pkg.name,
        "name": meta.get("name") or pkg.name,
        "version": meta.get("version") or "",
        "description": meta.get("description") or "",
        "variant": variant,
        "path": f"{path_prefix.rstrip('/')}/{pkg.name}",
        "hasSkillMd": skill_md.exists(),
        "hasChangelog": (pkg / "CHANGELOG.md").exists(),
        "counts": {
            "procedures": count_files(pkg / "procedures", "*.md"),
            "templates": count_files(pkg / "templates"),
            "tests": count_files(pkg / "tests"),
            "scripts": count_files(pkg / "scripts"),
            "rules": count_files(pkg / "rules"),
            "references": count_files(pkg / "references"),
            "roles": len([d for d in (pkg / "roles").iterdir() if d.is_dir()]) if (pkg / "roles").is_dir() else 0,
        },
    }
    dsl = pkg / "dsl.json"
    if dsl.exists():
        try:
            item["tools"] = sorted({
                t for proc in json.loads(dsl.read_text(encoding="utf-8")).get("procedures", [])
                for t in (proc.get("tools") or [])
            })
        except Exception:
            item["tools"] = []
    return item


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    ap.add_argument("--skills-dir", type=Path, default=SKILLS, help="技能包根目录")
    ap.add_argument("--out", type=Path, default=OUT, help="输出索引文件")
    ap.add_argument("--path-prefix", default="skills", help="索引 path 字段前缀")
    args = ap.parse_args(argv)

    skills_dir = args.skills_dir.resolve()
    output = args.out.resolve()
    if not skills_dir.is_dir():
        print(f"[FAIL] 找不到技能目录：{skills_dir}")
        return 1

    packages = sorted(p for p in skills_dir.iterdir() if p.is_dir() and p.name not in SKIP)
    skills = [build_one(p, path_prefix=args.path_prefix) for p in packages]

    missing = [s["id"] for s in skills if not s["hasSkillMd"]]
    index = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(skills),
        "byVariant": {v: sum(1 for s in skills if s["variant"] == v) for v in ("skill-group", "orchestrator", "tool", "standard")},
        "totalProcedures": sum(s["counts"]["procedures"] for s in skills),
        "skills": skills,
    }

    print(f"扫描到 {len(skills)} 个技能包 · 程序卡文档 {index['totalProcedures']} 份")
    print("  形态分布：" + " / ".join(f"{k}={v}" for k, v in index["byVariant"].items()))
    if missing:
        print(f"  [WARN] 缺 SKILL.md：{', '.join(missing)}")

    if args.check:
        print("[OK] 校验模式，未写文件")
        return 1 if missing else 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        rendered = output.relative_to(ROOT)
    except ValueError:
        rendered = output
    print(f"已写入 {rendered}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
