#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量发布审小牛技能包到个人账户（SkillHub）。

带限频退避与重试：每个包之间默认间隔 25 秒，429 时退避 90 秒重试。
用法：
    python publish_all.py                # 发布全部未发布的
    python publish_all.py --only a,b     # 只发指定包
    python publish_all.py --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skill-library"
CLI_PY = Path.home() / ".skillhub" / "skills_store_cli.py"
PYEXE = sys.executable
LOG = Path(__file__).resolve().parent / "publish-log.jsonl"
CHANGELOG = "迁移至个人账户 @indiv-27，slug 前缀 aiauditox-"

# 已确认发布成功的（避免重复发）
DONE = {
    "f-6-payroll-payable",
    "z-1-1-cash-on-hand",
    "z-1-2-bank-deposits",
    "z-1-3-other-monetary-funds",
}

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def publish(pkg: str, dry: bool = False) -> tuple[bool, str]:
    cmd = [PYEXE, str(CLI_PY), "publish", pkg]
    if dry:
        cmd.append("--dry-run")
    else:
        cmd += ["--changelog", CHANGELOG]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    p = subprocess.run(cmd, cwd=str(SKILLS), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, env=env)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--gap", type=int, default=25, help="包间隔秒数")
    args = ap.parse_args()

    pkgs = sorted(d.name for d in SKILLS.iterdir() if d.is_dir() and not d.name.startswith("_"))
    if args.only:
        want = {x.strip() for x in args.only.split(",")}
        pkgs = [p for p in pkgs if p in want]
    else:
        pkgs = [p for p in pkgs if p not in DONE]

    print(f"待发布 {len(pkgs)} 个，间隔 {args.gap}s")
    ok, fail = [], []
    for i, pkg in enumerate(pkgs, 1):
        for attempt in range(1, 4):
            good, out = publish(pkg, args.dry_run)
            if good:
                print(f"[{i}/{len(pkgs)}] OK   {pkg}  {out.splitlines()[0][:70]}")
                ok.append(pkg)
                with LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"pkg": pkg, "ok": True, "out": out[:200]}, ensure_ascii=False) + "\n")
                break
            if "频率" in out or "频繁" in out or "429" in out:
                print(f"[{i}/{len(pkgs)}] 限频 {pkg}，退避 90s（第 {attempt} 次）")
                time.sleep(90)
                continue
            print(f"[{i}/{len(pkgs)}] FAIL {pkg}  {out[:120]}")
            fail.append((pkg, out[:200]))
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"pkg": pkg, "ok": False, "out": out[:300]}, ensure_ascii=False) + "\n")
            break
        else:
            fail.append((pkg, "重试 3 次仍限频"))
            print(f"[{i}/{len(pkgs)}] GIVE UP {pkg}")
        if i < len(pkgs):
            time.sleep(args.gap)

    print(f"\n完成：成功 {len(ok)} / 失败 {len(fail)}")
    for pkg, msg in fail:
        print(f"  x {pkg}: {msg}")


if __name__ == "__main__":
    main()
