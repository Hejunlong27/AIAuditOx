#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 skills/ 下的技能包结构 —— 提交前与 CI 共用。

检查项：
  1. 每个包必须有 SKILL.md，frontmatter 含 name / description / version
  2. frontmatter 的 name 与目录名一致
  3. 技能组：dsl.json 可解析；procedures/ 存在；程序分派表可解析
  4. 程序卡：dsl.json 声明的程序卡是否都有对应文档（缺文档记警告，不阻断）
  5. 总控型必须有 roles/ 且至少 1 个子技能
  6. 工具型必须有 scripts/
  7. 更新记录：有 CHANGELOG.md 则检查是否为倒序表格（缺失只警告）

退出码：0 通过（可含警告）／1 有错误
"""

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SKIP = {"_index", "_templates", "__pycache__", ".pytest_cache", "output"}

errors, warnings = [], []


def err(pkg, msg):
    errors.append(f"{pkg}: {msg}")


def warn(pkg, msg):
    warnings.append(f"{pkg}: {msg}")


def parse_frontmatter(text):
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


def check_dispatch_table(text):
    """找「程序分派表」后的第一张 Markdown 表格，确认表头含关键列。"""
    idx = text.find("程序分派表")
    if idx == -1:
        return None
    block = text[idx: idx + 6000]
    lines = [l.strip() for l in block.splitlines()]
    for i, line in enumerate(lines):
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1]):
            headers = [c.strip() for c in line.strip("|").split("|")]
            required = ["程序卡", "程序名称", "认定", "产出底稿"]
            return {r: any(r in h for h in headers) for r in required}
    return {}


def check_pkg(pkg: Path):
    name = pkg.name
    skill_md = pkg / "SKILL.md"
    if not skill_md.exists():
        err(name, "缺 SKILL.md")
        return

    meta = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    for key in ("name", "description"):
        if not meta.get(key):
            err(name, f"frontmatter 缺 {key}")
    if not meta.get("version"):
        warn(name, "frontmatter 缺 version（建议补齐，索引会留空）")
    if meta.get("name") and meta["name"] != name:
        warn(name, f"frontmatter name（{meta['name']}）与目录名不一致")

    is_orch = (pkg / "roles").is_dir()
    is_tool = (pkg / "scripts").is_dir()
    is_group = (pkg / "procedures").is_dir()

    if is_orch:
        subs = [d for d in (pkg / "roles").iterdir() if d.is_dir()]
        if not subs:
            err(name, "roles/ 为空")
        for s in subs:
            if not (s / "SKILL.md").exists():
                warn(name, f"子技能 {s.name} 缺 SKILL.md")
    elif is_tool:
        if not any((pkg / "scripts").rglob("*.py")) and not any((pkg / "scripts").rglob("*.js")):
            warn(name, "scripts/ 下没有脚本文件")
    elif is_group:
        # 技能组：SKILL.md + dsl.json + procedures/P*.md
        dsl = pkg / "dsl.json"
        proc_dir = pkg / "procedures"
        if not dsl.exists():
            err(name, "技能组缺 dsl.json")
        if dsl.exists():
            try:
                data = json.loads(dsl.read_text(encoding="utf-8"))
            except Exception as e:
                err(name, f"dsl.json 解析失败：{e}")
                data = {}
            procs = data.get("procedures") or []
            if not procs:
                warn(name, "dsl.json 没有 procedures")
            docs = {p.stem.split("-")[0] for p in proc_dir.glob("P*.md")}
            missing = [p.get("id") for p in procs if p.get("id") and p["id"] not in docs]
            if missing:
                warn(name, f"{len(missing)} 张程序卡无独立文档：{', '.join(missing[:8])}")
        table = check_dispatch_table(skill_md.read_text(encoding="utf-8", errors="replace"))
        if table is None:
            warn(name, "未找到「程序分派表」")
        elif table and not all(table.values()):
            lacking = [k for k, v in table.items() if not v]
            warn(name, f"程序分派表缺列：{', '.join(lacking)}")
    else:
        # 规范型：只有 SKILL.md + dsl.json + templates，无程序卡
        if not (pkg / "dsl.json").exists():
            warn(name, "既无 roles/、scripts/、procedures/，也无 dsl.json，无法判别形态")
        else:
            try:
                json.loads((pkg / "dsl.json").read_text(encoding="utf-8"))
            except Exception as e:
                err(name, f"dsl.json 解析失败：{e}")

    cl = pkg / "CHANGELOG.md"
    if cl.exists():
        body = cl.read_text(encoding="utf-8", errors="replace")
        dates = re.findall(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|", body)
        if dates != sorted(dates, reverse=True):
            warn(name, "CHANGELOG 日期不是倒序")
    else:
        warn(name, "缺 CHANGELOG.md")


def main():
    if not SKILLS.is_dir():
        print(f"[FAIL] 找不到技能目录：{SKILLS}")
        return 1

    packages = sorted(p for p in SKILLS.iterdir() if p.is_dir() and p.name not in SKIP)
    for pkg in packages:
        check_pkg(pkg)

    print(f"检查 {len(packages)} 个技能包")
    if warnings:
        print(f"\n警告（{len(warnings)}）")
        for w in warnings:
            print("  ! " + w)
    if errors:
        print(f"\n错误（{len(errors)}）")
        for e in errors:
            print("  x " + e)
        print("\n结果：不通过")
        return 1
    print(f"\n结果：通过（{len(warnings)} 个警告）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
