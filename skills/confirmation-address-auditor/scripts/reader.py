# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 多格式数据读取 (Stage 1)
==================================================
支持：Excel(.xlsx) / CSV / PDF / Word(.docx)
能力：
  1) 自动识别表头行（在前若干行中定位候选表头）
  2) 表头模糊映射到标准字段（别名库）
  3) PDF / Word 无表格时，回退为"键值对"逐行解析
  4) 输出统一记录结构 + 读取元数据（用于底稿"数据来源"章节）

依赖：openpyxl / pdfplumber / python-docx（缺失时报明确错误，不静默降级）
"""
import csv
import io
import os
import re

# ---------------------------------------------------------------------------
# 标准字段与别名库
# ---------------------------------------------------------------------------
FIELD_ALIASES = {
    "entity_name": ["被函证单位名称", "被函证单位", "被询证单位", "单位名称", "企业名称",
                    "公司名称", "客户名称", "供应商名称", "往来单位", "名称", "被函证方"],
    "uscc": ["统一社会信用代码", "社会信用代码", "统一信用代码", "信用代码", "纳税人识别号",
             "税号", "uscc", "工商注册号"],
    "confirm_address": ["函证地址", "函证收件地址", "询证地址", "收件地址", "邮寄地址",
                        "寄送地址", "通讯地址", "联系地址", "发函地址", "函件地址"],
    "registered_address": ["注册地址", "工商注册地址", "营业执照地址", "登记地址", "注册地",
                           "工商地址", "注册住所", "住所"],
    "phone": ["联系电话", "电话", "联系方式", "电话号码", "手机号", "手机", "固定电话",
              "收件电话", "联系人电话"],
    "contact": ["联系人", "收件人", "对接人", "联系人姓名", "经办人"],
    "confirm_type": ["函证类型", "询证类型", "函证类别", "类型", "往来类型", "函证性质"],
    "registered_name": ["工商登记名称", "工商名称", "登记名称", "注册名称", "营业执照名称"],
    "reg_change_count": ["注册地址变更次数", "地址变更次数", "工商变更次数", "变更次数"],
    "reg_source": ["工商信息来源", "信息来源", "查询来源", "来源平台", "数据来源平台",
                   "核对来源", "查询渠道"],
    "reg_source_url": ["工商信息网址", "来源网址", "查询网址", "公示系统网址", "核对网址",
                       "工商查询网址", "信息链接", "来源链接"],
    "query_date": ["查询日期", "核对日期", "截图日期", "信息查询日期", "核查日期"],
    "screenshot": ["查询界面截图附件", "查询界面截图", "工商信息查询截图", "查询截图附件",
                   "查询截图", "界面截图", "截图文件名", "工商查询截图",
                   "截图", "附件文件名", "证据附件", "附件"],
}

FIELD_LABELS = {
    "entity_name": "被函证单位名称",
    "uscc": "统一社会信用代码",
    "confirm_address": "函证地址",
    "registered_address": "注册地址",
    "phone": "联系电话",
    "contact": "联系人",
    "confirm_type": "函证类型",
    "registered_name": "工商登记名称",
    "reg_change_count": "注册地址变更次数",
    "reg_source": "工商信息来源",
    "reg_source_url": "信息来源网址",
    "query_date": "查询日期",
    "screenshot": "查询界面截图附件",
}

REQUIRED_FIELDS = ["entity_name", "confirm_address"]


def _norm_header(h) -> str:
    if h is None:
        return ""
    s = str(h)
    s = re.sub(r"[\s\u3000()（）\[\]【】:：/、,，.-]", "", s)
    return s.strip().lower()


def map_headers(headers):
    """表头 → 标准字段映射。返回 {field: col_index}"""
    mapped = {}
    normed = [_norm_header(h) for h in headers]
    alias_norm = {f: [_norm_header(a) for a in al] for f, al in FIELD_ALIASES.items()}

    # 第一轮：精确匹配
    for field, aliases in alias_norm.items():
        for i, nh in enumerate(normed):
            if nh and nh in aliases:
                mapped[field] = i
                break

    # 第二轮：包含关系（长度接近，容差 3）
    for field, aliases in alias_norm.items():
        if field in mapped:
            continue
        for i, nh in enumerate(normed):
            if not nh:
                continue
            if any(na and (na in nh or nh in na) and abs(len(na) - len(nh)) <= 3
                   for na in aliases):
                mapped[field] = i
                break

    # 第三轮：宽松包含（别名 ≥3 字，避免过短别名误命中）
    for field, aliases in alias_norm.items():
        if field in mapped:
            continue
        for i, nh in enumerate(normed):
            if not nh:
                continue
            if any(len(na) >= 3 and (na in nh or nh in na) for na in aliases):
                mapped[field] = i
                break
    return mapped


def _score_header_row(row) -> int:
    """给一行打分，用于定位真实表头行。"""
    s = 0
    for cell in row:
        nh = _norm_header(cell)
        if not nh:
            continue
        for aliases in FIELD_ALIASES.values():
            if any(nh == _norm_header(a) for a in aliases):
                s += 3
            elif any(_norm_header(a) in nh and _norm_header(a) for a in aliases):
                s += 1
    return s


# ---------------------------------------------------------------------------
# 各格式读取器
# ---------------------------------------------------------------------------

def _rows_to_records(rows, meta):
    """rows: List[List[cell]]；自动定位表头并映射。"""
    if not rows:
        raise ValueError("文件中未读取到任何数据行")
    best_i, best_score = 0, -1
    for i, row in enumerate(rows[:12]):
        sc = _score_header_row(row)
        if sc > best_score:
            best_i, best_score = i, sc
    headers = rows[best_i]
    mapping = map_headers(headers)

    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise ValueError(
            "未能识别必需字段：%s。请确认表头包含【被函证单位名称/函证地址】等列，"
            "或在 SKILL.md 中扩展别名库。已识别表头：%s"
            % ("、".join(FIELD_LABELS[f] for f in missing), [str(h) for h in headers]))

    records = []
    for row in rows[best_i + 1:]:
        if row is None:
            continue
        if all((c is None or str(c).strip() == "") for c in row):
            continue
        rec = {}
        for field, idx in mapping.items():
            v = row[idx] if idx < len(row) else ""
            rec[field] = "" if v is None else str(v).strip()
        for f in FIELD_LABELS:
            rec.setdefault(f, "")
        records.append(rec)

    meta.update({
        "header_row": best_i + 1,
        "columns_mapped": {FIELD_LABELS[f]: str(headers[i]) for f, i in mapping.items()},
        "records": len(records),
    })
    return records


def _read_xlsx(path, meta):
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise RuntimeError("缺少 openpyxl，无法读取 Excel：%s" % e)
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(list(row))
    meta["sheet"] = ws.title
    meta["sheet_count"] = len(wb.sheetnames)
    wb.close()
    return _rows_to_records(rows, meta)


def _read_csv(path, meta):
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "gb18030", "utf-8", "big5"):
        try:
            text = raw.decode(enc)
            meta["encoding"] = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("CSV 编码无法识别（已尝试 utf-8-sig / gb18030 / utf-8 / big5）")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except Exception:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect)]
    return _rows_to_records(rows, meta)


def _read_pdf(path, meta):
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError("缺少 pdfplumber，无法读取 PDF：%s" % e)
    all_rows = []
    kv_lines = []
    with pdfplumber.open(path) as pdf:
        meta["pages"] = len(pdf.pages)
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for t in tables:
                for r in t:
                    all_rows.append(r)
            if not tables:
                txt = page.extract_text() or ""
                kv_lines.extend([ln for ln in txt.splitlines() if ln.strip()])
    if all_rows and _score_header_row(all_rows[0]) > 0:
        meta["parse_mode"] = "PDF 表格"
        return _rows_to_records(all_rows, meta)
    if all_rows:
        meta["parse_mode"] = "PDF 表格（未识别表头，尝试键值解析）"
        recs = _kv_records(all_rows, meta)
        if recs:
            return recs
    meta["parse_mode"] = "PDF 文本（键值行解析）"
    recs = _kv_records([ln.split() for ln in kv_lines], meta)
    if not recs:
        raise ValueError(
            "PDF 中未解析出可用的函证信息。建议：将 PDF 转为 Excel/CSV 后重试，"
            "或使用带文本层（非扫描件）的 PDF。")
    return recs


def _read_docx(path, meta):
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError("缺少 python-docx，无法读取 Word：%s" % e)
    doc = Document(path)
    rows = []
    for tbl in doc.tables:
        for r in tbl.rows:
            rows.append([c.text for c in r.cells])
    if rows and _score_header_row(rows[0]) > 0:
        meta["parse_mode"] = "Word 表格"
        return _rows_to_records(rows, meta)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    meta["parse_mode"] = "Word 文本（键值行解析）"
    recs = _kv_records([_split_kv(ln) for ln in lines], meta)
    if not recs:
        raise ValueError("Word 中未解析出可用的函证信息，请确认文档包含函证清单表格。")
    return recs


def _split_kv(line):
    for sep in ("：", ":", "=", "\t", "|", "，", ","):
        if sep in line:
            parts = [p.strip() for p in line.split(sep, 1)]
            return parts
    return [line.strip()]


def _kv_records(rows, meta):
    """把 键/值 行聚合为记录：遇到 entity_name 键即视为新记录开始。"""
    records = []
    cur = {}
    label2field = {}
    for field, aliases in FIELD_ALIASES.items():
        for a in aliases:
            label2field[_norm_header(a)] = field

    for row in rows:
        if not row:
            continue
        if len(row) == 1:
            pair = _split_kv(str(row[0]))
        elif len(row) >= 2:
            pair = [str(row[0]), str(row[1])]
        else:
            continue
        if len(pair) < 2:
            continue
        k = _norm_header(pair[0])
        f = label2field.get(k)
        if not f:
            for lbl, fl in label2field.items():
                if lbl and (lbl in k) and abs(len(lbl) - len(k)) <= 3:
                    f = fl
                    break
        if not f:
            continue
        if f == "entity_name" and cur.get("entity_name") and cur.get("confirm_address"):
            records.append(cur)
            cur = {}
        cur[f] = str(pair[1]).strip()

    if cur:
        records.append(cur)
    for r in records:
        for f in FIELD_LABELS:
            r.setdefault(f, "")
    meta["parse_mode"] = meta.get("parse_mode", "键值行解析")
    meta["records"] = len(records)
    return records


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

def read_records(path):
    """返回 (records: List[dict], meta: dict)"""
    if not os.path.exists(path):
        raise FileNotFoundError("输入文件不存在：%s" % path)
    ext = os.path.splitext(path)[1].lower()
    meta = {"source_file": os.path.basename(path), "source_ext": ext,
            "parse_mode": "表格", "encoding": "-"}
    if ext in (".xlsx", ".xlsm"):
        recs = _read_xlsx(path, meta)
    elif ext == ".csv":
        recs = _read_csv(path, meta)
    elif ext == ".pdf":
        recs = _read_pdf(path, meta)
    elif ext in (".docx",):
        recs = _read_docx(path, meta)
    elif ext == ".xls":
        raise ValueError("不支持旧版 .xls 格式，请另存为 .xlsx 后重试")
    elif ext in (".doc",):
        raise ValueError("不支持旧版 .doc 格式，请另存为 .docx 后重试")
    else:
        raise ValueError("不支持的文件格式：%s（支持 xlsx/csv/pdf/docx）" % ext)

    return recs, meta
