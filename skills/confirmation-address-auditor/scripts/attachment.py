# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 附件管理（索引号编制 / 截图归集 / 复制归档）
====================================================================
职责：
  1) 扫描用户提供的截图目录（支持多目录，以 ; 分隔）
  2) 为每条记录匹配其"工商信息查询界面截图"
       - 优先按记录中「查询界面截图附件」字段指定的文件名匹配
       - 其次按序号约定匹配（1.png / 01.png / <索引号>-01.png）
       - 再次按被函证单位字号匹配文件名
  3) 统一复制到输出目录的 `附件/` 子目录，并按索引号重命名
  4) 生成附件清单（manifest），供 Excel「附件索引表」与 Word 附录使用

索引号规则：`<底稿索引号>-<记录序号两位>`，同一记录多张截图追加 `-1`、`-2`……
例如 B-3-1-05、B-3-1-05-1。
"""
import os
import re
import shutil

from normalizer import is_blank, normalize_entity_name

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
DOC_EXT = {".pdf"}


def is_image(path) -> bool:
    return os.path.splitext(path)[1].lower() in IMG_EXT


def _stem(path) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def attachment_index(index_no, seq, k=1):
    """编制附件索引号。"""
    base = "%s-%02d" % (index_no, seq)
    return base if k <= 1 else "%s-%d" % (base, k)


class AttachmentManager:
    def __init__(self, outdir, attach_dirs=None, index_no="B-3-1"):
        self.outdir = outdir
        self.attach_dirs = [d.strip() for d in str(attach_dirs or "").split(";") if d.strip()]
        self.index_no = index_no or "B-3-1"
        self.out_attach = os.path.join(outdir, "附件")
        self.manifest = []
        self.by_seq = {}
        self._pool = self._scan_pool()

    # ---------------- 内部 ----------------
    def _scan_pool(self):
        pool = []
        for d in self.attach_dirs:
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                fp = os.path.join(d, f)
                if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in (IMG_EXT | DOC_EXT):
                    pool.append(fp)
        return pool

    def _match(self, rec, seq):
        spec = str(rec.get("screenshot") or "").strip()
        if not is_blank(spec):
            names = [n for n in re.split(r"[|,，;；、\s]+", spec) if n.strip()]
            hits = []
            for n in names:
                n = n.strip()
                if os.path.isabs(n) and os.path.exists(n):
                    hits.append(n)
                    continue
                target = os.path.basename(n)
                target_stem = os.path.splitext(target)[0]
                for fp in self._pool:
                    if os.path.basename(fp) == target or _stem(fp) == target_stem:
                        hits.append(fp)
                        break
                else:
                    for fp in self._pool:
                        if target_stem and target_stem in os.path.basename(fp):
                            hits.append(fp)
                            break
            if hits:
                return list(dict.fromkeys(hits))

        cands = {"%d" % seq, "%02d" % seq, "%s-%02d" % (self.index_no, seq)}
        for fp in self._pool:
            if _stem(fp) in cands:
                return [fp]

        core = (normalize_entity_name(rec.get("entity_name")).get("core_na") or "").strip()
        if core and len(core) >= 2:
            for fp in self._pool:
                if core in os.path.basename(fp):
                    return [fp]
        return []

    # ---------------- 对外 ----------------
    def collect(self, records):
        """归集全部附件，返回 (manifest, by_seq)。by_seq: {记录序号: [dict,...]}"""
        os.makedirs(self.out_attach, exist_ok=True)
        self.manifest, self.by_seq = [], {}

        for seq, rec in enumerate(records, start=1):
            files = self._match(rec, seq)
            items = []
            for k, fp in enumerate(files, start=1):
                code = attachment_index(self.index_no, seq, k)
                ext = os.path.splitext(fp)[1].lower()
                dst_name = code + ext
                dst = os.path.join(self.out_attach, dst_name)
                try:
                    shutil.copy2(fp, dst)
                except Exception:  # noqa: BLE001
                    continue
                item = {
                    "索引号": code,
                    "对应记录序号": seq,
                    "被函证单位": rec.get("entity_name", ""),
                    "附件类型": "工商信息查询界面截图" if is_image(fp) else "其他附件",
                    "原文件名": os.path.basename(fp),
                    "附件文件名": dst_name,
                    "相对路径": "附件/" + dst_name,
                    "绝对路径": dst,
                    "工商信息来源": rec.get("reg_source", ""),
                    "来源网址": rec.get("reg_source_url", ""),
                    "查询日期": rec.get("query_date", ""),
                    "说明": "",
                }
                items.append(item)
                self.manifest.append(item)
            self.by_seq[seq] = items
        return self.manifest, self.by_seq

    def missing(self, seq):
        """该记录是否缺少截图附件。"""
        return not self.by_seq.get(seq)


def build_evidence_checklist(records, by_seq, index_no="B-3-1"):
    """生成"证据留痕核对清单"（供风险规则与底稿使用）。"""
    rows = []
    for seq, rec in enumerate(records, start=1):
        items = by_seq.get(seq, [])
        src = str(rec.get("reg_source") or "").strip()
        url = str(rec.get("reg_source_url") or "").strip()
        rows.append({
            "序号": seq,
            "被函证单位": rec.get("entity_name", ""),
            "附件数": len(items),
            "附件索引号": "、".join(i["索引号"] for i in items),
            "工商信息来源": src,
            "来源网址": url,
            "查询日期": str(rec.get("query_date") or "").strip(),
            "缺来源网址": is_blank(url),
            "缺来源平台": is_blank(src),
            "缺查询截图": len(items) == 0,
            "缺查询日期": is_blank(rec.get("query_date")),
        })
    return rows
