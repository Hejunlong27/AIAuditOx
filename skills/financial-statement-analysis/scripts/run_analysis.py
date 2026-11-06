#!/usr/bin/env python
"""命令行入口：执行财务报表分析程序并生成底稿。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fs_analysis import analysis, pipeline  # noqa: E402
from fs_analysis.loader import load_workbook  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="财务报表分析程序：生成分析性程序底稿")
    parser.add_argument("--input", required=True, help="四张报表的 Excel 文件路径")
    parser.add_argument("--outdir", default="output", help="输出目录（默认 output）")
    parser.add_argument("--entity", default=None, help="被审计单位名称")
    parser.add_argument("--period", default=None, help="期间标签，如 2025年度")
    parser.add_argument("--materiality", type=float, default=None, help="整体重要性水平（元）")
    parser.add_argument("--suggest-materiality", action="store_true",
                        help="仅测算建议重要性水平，不生成底稿")
    parser.add_argument("--stem", default=None, help="输出文件名前缀（默认取输入文件名）")
    args = parser.parse_args(argv)

    if args.suggest_materiality:
        report = load_workbook(args.input)
        suggestion = analysis.suggest_materiality(report)
        print("重要性水平测算（金额单位：元）")
        print("-" * 52)
        for row in suggestion["bases"]:
            value = row["测算值"]
            text = f"{value:,.2f}" if isinstance(value, (int, float)) else "无法测算"
            base = f"{row['基准金额']:,.2f}" if isinstance(row["基准金额"], (int, float)) else "-"
            print(f"{row['基准']:<10}基准金额 {base:>18}  × {row['比例']:.2%}  = {text:>18}")
        print("-" * 52)
        if suggestion["suggestion"]:
            print(f"建议重要性水平（以{'、'.join(suggestion['basis_used'])}为基准）：{suggestion['suggestion']:,.2f}")
        print(suggestion["note"])
        return 0

    outcome = pipeline.run(
        input_path=args.input,
        outdir=args.outdir,
        entity=args.entity,
        period=args.period,
        materiality=args.materiality,
        stem=args.stem,
    )
    result = outcome["result"]
    print("分析完成")
    print(f"  重要性水平：{result.meta['materiality']:,.2f} 元（{result.meta['materiality_source']}）"
          if result.meta.get("materiality") else "  重要性水平：未确定")
    print(f"  异常事项：{len(result.exceptions)} 项"
          f"（L3 {sum(1 for r in result.exceptions if r['等级'].startswith('L3'))}，"
          f"L2 {sum(1 for r in result.exceptions if r['等级'].startswith('L2'))}，"
          f"L1 {sum(1 for r in result.exceptions if r['等级'].startswith('L1'))}）")
    print(f"  未映射项目：{len(result.unmapped)} 项")
    for name, path in outcome["paths"].items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
