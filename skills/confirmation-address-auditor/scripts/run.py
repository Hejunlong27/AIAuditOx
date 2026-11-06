# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 端到端主流程 (Stage 1 → Stage 6)
==========================================================
用法：
  python run.py --input <函证清单.xlsx|csv|pdf|docx> --outdir <输出目录>
                [--attach-dir "<查询截图目录>[;<目录2>]"]
                [--index-no B-3-1] [--project "被审计单位/项目名"]
                [--prepared-by 姓名] [--reviewed-by 姓名] [--no-require-evidence]

流程：
  Stage1 读取 → Stage2 标准化 → Stage3 三级匹配 → Stage4 风险识别
  → Stage5 审计判断 → Stage6 生成 Excel / Word / Markdown / JSON + 附件归档

输出结构：
  <outdir>/
  ├── 函证地址核对记录表_<日期>.xlsx      （询证信息 / 工商登记信息 两栏对照 + 超链接）
  ├── 函证地址核对执行记录_<日期>.docx    （审计底稿，含附录一来源记录、附录二查询截图）
  ├── 函证地址核对结果摘要_<日期>.md
  ├── 函证地址核对结果_机器可读_<日期>.json
  └── 附件/
      ├── B-3-1-01.png  …                （按索引号归档的查询界面截图）
      └── B-3-1-02.png
"""
import argparse
import json
import os
import sys
from datetime import date

# 允许以脚本方式直接运行（同目录模块导入）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matcher          # noqa: E402
import report_builder   # noqa: E402
import risk_engine      # noqa: E402
from attachment import AttachmentManager, build_evidence_checklist  # noqa: E402
from reader import read_records  # noqa: E402


def run(input_path, outdir, project="", prepared_by="", reviewed_by="",
        attach_dir="", index_no="B-3-1", require_evidence=True):
    os.makedirs(outdir, exist_ok=True)
    tag = date.today().strftime("%Y%m%d")

    print("[1/6] Stage1 数据读取 ...")
    records, meta = read_records(input_path)
    print("[OK] 读取 %d 条记录，解析方式：%s" % (len(records), meta.get("parse_mode")))

    print("[2/6] Stage2 数据标准化 ... (名称归一 + 地址分层解析，内置规则)")
    print("[3/6] Stage3 三级匹配 ...")
    matched = matcher.run_matching(records)
    print("[OK] 匹配完成：%s" % ", ".join(
        "%s=%d" % (s, sum(1 for m in matched if m["addr_status"] == s))
        for s in ("一致", "基本一致", "部分一致", "不一致", "无法比对")))

    print("[4/6] Stage4 风险识别 + [5/6] Stage5 审计判断 ...")
    # 附件归集与索引号编制
    am = AttachmentManager(outdir, attach_dir, index_no)
    manifest, by_seq = am.collect(records)
    ev_rows = build_evidence_checklist(records, by_seq, index_no)
    ev_map = {r["序号"]: r for r in ev_rows}
    if manifest:
        print("[OK] 附件归集 %d 个，索引号 %s ~ %s"
              % (len(manifest), manifest[0]["索引号"], manifest[-1]["索引号"]))
    else:
        print("[WARN] 未归集到任何附件（未提供 --attach-dir 或文件名未匹配）")

    reg_map = {}
    for r in records:
        if str(r.get("reg_change_count", "")).strip().isdigit():
            key = str(r.get("uscc") or "").strip() or str(r.get("entity_name") or "").strip()
            reg_map[key] = int(str(r["reg_change_count"]).strip())
    assessed = risk_engine.assess_all(matched, reg_map, ev_map, require_evidence)
    print("[OK] 风险分布：高风险 %d / 中风险 %d / 低风险 %d" % (
        sum(1 for a in assessed if a["risk_level"] == "高风险"),
        sum(1 for a in assessed if a["risk_level"] == "中风险"),
        sum(1 for a in assessed if a["risk_level"] == "低风险")))

    print("[6/6] Stage6 生成交付物 ...")
    xlsx = os.path.join(outdir, "函证地址核对记录表_%s.xlsx" % tag)
    docx = os.path.join(outdir, "函证地址核对执行记录_%s.docx" % tag)
    md = os.path.join(outdir, "函证地址核对结果摘要_%s.md" % tag)
    js = os.path.join(outdir, "函证地址核对结果_机器可读_%s.json" % tag)

    report_builder.build_excel(assessed, meta, xlsx, manifest, by_seq, index_no)
    report_builder.build_workpaper(assessed, meta, docx, project, prepared_by, reviewed_by,
                                   manifest, by_seq, index_no)
    report_builder.build_markdown(assessed, meta, md, manifest, by_seq, index_no)

    payload = {
        "generated_at": date.today().isoformat(),
        "project": project,
        "index_no": index_no,
        "source": meta,
        "summary": {
            "total": len(assessed),
            "high": sum(1 for a in assessed if a["risk_level"] == "高风险"),
            "medium": sum(1 for a in assessed if a["risk_level"] == "中风险"),
            "low": sum(1 for a in assessed if a["risk_level"] == "低风险"),
            "attachments": len(manifest),
        },
        "attachments": manifest,
        "records": [
            {
                "seq": a.get("index"),
                "entity_name": a.get("entity_name"),
                "uscc": a.get("uscc"),
                "confirm_address": a.get("confirm_address"),
                "registered_name": a.get("registered_name"),
                "registered_address": a.get("registered_address"),
                "reg_source": a.get("reg_source"),
                "reg_source_url": a.get("reg_source_url"),
                "query_date": a.get("query_date"),
                "attachment_index": [i["索引号"] for i in by_seq.get(a.get("index"), [])],
                "match_status": a.get("addr_status"),
                "match_degree": a.get("addr_score"),
                "risk_level": a.get("risk_level"),
                "risk_codes": a.get("risk_codes"),
                "diff_rows": a.get("diff_rows"),
                "explanation": a.get("explanation"),
                "advice": a.get("advice"),
                "flags": a.get("flags"),
                "evidence": a.get("evidence"),
            } for a in assessed
        ],
    }
    with open(js, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    for p in (xlsx, docx, md, js):
        print("[OK] 已生成：%s" % p)
    if manifest:
        print("[OK] 附件目录：%s（%d 个）" % (am.out_attach, len(manifest)))
    return {"xlsx": xlsx, "docx": docx, "md": md, "json": js,
            "attach_dir": am.out_attach, "summary": payload["summary"]}


def main():
    ap = argparse.ArgumentParser(description="函证地址智能核对助手")
    ap.add_argument("--input", required=True, help="函证清单文件（xlsx/csv/pdf/docx）")
    ap.add_argument("--outdir", required=True, help="输出目录")
    ap.add_argument("--attach-dir", default="",
                    help="工商信息查询界面截图所在目录；多个目录以英文分号分隔")
    ap.add_argument("--index-no", default="B-3-1",
                    help="底稿索引号前缀，附件索引号规则为 <索引号>-<序号两位>，默认 B-3-1")
    ap.add_argument("--project", default="", help="被审计单位/项目名称")
    ap.add_argument("--prepared-by", default="", help="编制人")
    ap.add_argument("--reviewed-by", default="", help="复核人")
    ap.add_argument("--no-require-evidence", action="store_true",
                    help="关闭“必须留存来源网址与查询截图”的强制校验（默认开启）")
    args = ap.parse_args()
    try:
        run(args.input, args.outdir, args.project, args.prepared_by, args.reviewed_by,
            args.attach_dir, args.index_no, not args.no_require_evidence)
    except Exception as e:  # noqa: BLE001
        print("[FAIL] %s: %s" % (type(e).__name__, e))
        sys.exit(1)


if __name__ == "__main__":
    main()
