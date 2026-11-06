# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 结果与底稿生成 (Stage 6)
==================================================
交付物：
  1) Excel 核对记录表
     · 函证地址核对结果        —— 询证信息 / 工商登记信息 两栏对照 + 结论 + 附件索引号
     · 逐项差异明细            —— 按比对项目逐一列示差异
     · 附件索引表              —— 索引号 + 超链接（点击直接打开附件图片）
     · 风险汇总 / 数据来源与口径
  2) Word 审计底稿《函证地址核对执行记录》
     · 信息对照表 + 逐项差异说明 + 信息来源与网址（可点击）
     · 附录一 工商登记信息来源记录 / 附录二 查询界面截图（嵌入图片，标注索引号）
  3) Markdown 摘要
  4) 机器可读 JSON

超链接说明：
  · 附件链接使用"相对路径"（附件/索引号.png），与工作簿同目录，整包移动仍可打开
  · 来源网址使用完整 URL，指向国家企业信用信息公示系统或第三方查询页
"""
import os
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

RISK_FILL = {
    "高风险": PatternFill("solid", fgColor="F8CBAD"),
    "中风险": PatternFill("solid", fgColor="FFE699"),
    "低风险": PatternFill("solid", fgColor="C6E0B4"),
    "不确定": PatternFill("solid", fgColor="D9D9D9"),
}
HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
HEAD_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
SUB_FILL_A = PatternFill("solid", fgColor="2E75B6")   # 询证信息组
SUB_FILL_B = PatternFill("solid", fgColor="548235")   # 工商登记信息组
SUB_FILL_C = PatternFill("solid", fgColor="BF8F00")   # 核对结论组
SUB_FILL_D = PatternFill("solid", fgColor="7030A0")   # 审计判断组
SUB_FILL_E = PatternFill("solid", fgColor="7B3F00")   # 附件组
BODY_FONT = Font(name="微软雅黑", size=10)
LINK_FONT = Font(name="微软雅黑", size=10, color="0563C1", underline="single")
THIN = Side(style="thin", color="B7B7B7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _deg(v):
    return "" if v is None else ("%.1f" % v if isinstance(v, float) else v)


def _border_row(ws, r, ncols, wrap_cols=()):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=r, column=c)
        cell.font = BODY_FONT
        cell.border = BORDER
        cell.alignment = Alignment(vertical="top", wrap_text=(c in wrap_cols))


def _group(ws, row, c1, c2, text, fill):
    if c2 > c1:
        ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    cell = ws.cell(row=row, column=c1)
    cell.value = text
    cell.fill = fill
    cell.font = HEAD_FONT
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for c in range(c1, c2 + 1):
        ws.cell(row=row, column=c).border = BORDER


def _sub(ws, row, cols, fill=None):
    for c in cols:
        cell = ws.cell(row=row, column=c)
        cell.fill = fill or HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


def _autosize(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def build_excel(records, meta, out_path, manifest=None, by_seq=None, index_no="B-3-1",
                title="函证地址核对记录表"):
    manifest = manifest or []
    by_seq = by_seq or {}
    wb = Workbook()

    # =================== Sheet1 函证地址核对结果 ===================
    ws = wb.active
    ws.title = "函证地址核对结果"

    # 第一行：信息分组表头（审计底稿习惯的"两栏对照"结构）
    _group(ws, 1, 1, 1, "序号", HEAD_FILL)
    _group(ws, 1, 2, 5, "被审计单位提供的询证信息", SUB_FILL_A)
    _group(ws, 1, 6, 10, "工商登记信息（核对来源）", SUB_FILL_B)
    _group(ws, 1, 11, 16, "核对结论", SUB_FILL_C)
    _group(ws, 1, 17, 20, "审计判断", SUB_FILL_D)
    _group(ws, 1, 21, 22, "核对留痕附件", SUB_FILL_E)

    # 第二行：明细列名
    headers = [
        "序号",
        "公司名称", "统一社会信用代码", "函证地址", "函证类型",
        "公司名称", "注册地址", "信息来源", "来源网址", "查询日期",
        "匹配结果", "匹配度", "风险等级", "逐项差异说明", "异常说明", "审计建议",
        "是否建议发送函证", "是否需电话确认", "是否需获取工商变更资料", "是否需扩大审计程序",
        "附件索引号", "查看截图",
    ]
    for i, h in enumerate(headers, start=1):
        ws.cell(row=2, column=i, value=h)
    _style_header(ws, len(headers), row=2)

    wrap_cols = (4, 7, 14, 15, 16, 18, 19, 20)
    for n, r in enumerate(records, start=1):
        seq = r.get("index", n)
        items = by_seq.get(seq, [])
        codes = "、".join(i["索引号"] for i in items)
        f = r.get("flags", {})
        row = [
            seq,
            r.get("entity_name", ""), r.get("uscc", ""),
            r.get("confirm_address", ""), r.get("confirm_type", ""),
            r.get("registered_name", "") or "（未提供）",
            r.get("registered_address", "") or "（未提供）",
            r.get("reg_source", ""), None, r.get("query_date", ""),
            r.get("addr_status", ""), _deg(r.get("addr_score")), r.get("risk_level", ""),
            r.get("diff_text", ""), r.get("explanation", ""), r.get("advice", ""),
            f.get("send_confirm", ""), "是" if f.get("need_phone") else "否",
            "是" if f.get("need_reg_change_doc") else "否",
            "是" if f.get("need_extend_procedure") else "否",
            codes, None,
        ]
        ws.append(row)
        ridx = ws.max_row

        # 来源网址超链接
        url = (r.get("reg_source_url") or "").strip()
        c_url = ws.cell(row=ridx, column=9)
        if url.startswith("http"):
            c_url.value = url
            c_url.hyperlink = url
            c_url.font = LINK_FONT
        else:
            c_url.value = url or "（未提供）"

        # 附件超链接（相对路径，整包移动后仍可打开）
        c_att = ws.cell(row=ridx, column=22)
        if items:
            c_att.value = "查看截图"
            c_att.hyperlink = items[0]["相对路径"].replace("/", "\\")
            c_att.font = LINK_FONT
        else:
            c_att.value = "无附件"

        _border_row(ws, ridx, len(headers), wrap_cols)
        rc = ws.cell(row=ridx, column=13)
        if r.get("risk_level") in RISK_FILL:
            rc.fill = RISK_FILL[r["risk_level"]]
        for c in (1, 11, 12, 13, 17, 18, 19, 20, 21, 22):
            ws.cell(row=ridx, column=c).alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True)
        # 来源网址、附件超链接保持蓝色字体
        if url.startswith("http"):
            c_url.font = LINK_FONT
        if items:
            c_att.font = LINK_FONT

    _autosize(ws, [6, 26, 20, 34, 10, 26, 34, 16, 30, 11,
                   10, 8, 10, 46, 46, 44, 20, 12, 20, 18, 18, 11])
    ws.freeze_panes = "B3"
    ws.auto_filter.ref = "A2:%s%d" % (get_column_letter(len(headers)), ws.max_row)

    # =================== Sheet2 逐项差异明细 ===================
    ws2 = wb.create_sheet("逐项差异明细")
    h2 = ["序号", "被函证单位", "比对项目", "被审计单位提供（询证信息）",
          "工商登记信息", "是否一致", "差异说明", "附件索引号"]
    ws2.append(h2)
    _style_header(ws2, len(h2))
    for n, r in enumerate(records, start=1):
        seq = r.get("index", n)
        codes = "、".join(i["索引号"] for i in by_seq.get(seq, []))
        for d in r.get("diff_rows", []):
            same = d.get("same")
            ws2.append([
                seq, r.get("entity_name", ""), d.get("item", ""),
                d.get("supplied", "") or "（空）", d.get("registered", "") or "（空）",
                {True: "一致", False: "存在差异", None: "无法比对"}[same],
                d.get("note", ""), codes,
            ])
            ridx = ws2.max_row
            _border_row(ws2, ridx, len(h2), (2, 4, 5, 7))
            fc = ws2.cell(row=ridx, column=6)
            fc.alignment = Alignment(horizontal="center", vertical="center")
            if same is False:
                fc.fill = RISK_FILL["高风险"]
            elif same is None:
                fc.fill = RISK_FILL["中风险"]
            else:
                fc.fill = RISK_FILL["低风险"]
    _autosize(ws2, [6, 26, 16, 32, 32, 10, 40, 18])

    # =================== Sheet3 附件索引表 ===================
    ws3 = wb.create_sheet("附件索引表")
    h3 = ["附件索引号", "对应记录序号", "被函证单位", "附件类型", "附件文件名",
          "打开附件", "工商信息来源", "来源网址", "查询日期", "说明"]
    ws3.append(h3)
    _style_header(ws3, len(h3))
    if manifest:
        for it in manifest:
            ws3.append([
                it["索引号"], it["对应记录序号"], it["被函证单位"], it["附件类型"],
                it["附件文件名"], "点击打开附件", it["工商信息来源"], None,
                it["查询日期"], it["说明"],
            ])
            ridx = ws3.max_row
            _border_row(ws3, ridx, len(h3), (3, 10))
            c = ws3.cell(row=ridx, column=6)
            c.hyperlink = it["相对路径"].replace("/", "\\")
            c.font = LINK_FONT
            c.alignment = Alignment(horizontal="center", vertical="center")
            u = ws3.cell(row=ridx, column=8)
            if (it.get("来源网址") or "").startswith("http"):
                u.value = it["来源网址"]
                u.hyperlink = it["来源网址"]
                u.font = LINK_FONT
            else:
                u.value = it.get("来源网址") or "（未提供）"
    else:
        ws3.append(["—", "—", "—", "—", "—", "本次未归集附件（未提供截图目录或文件名）",
                    "—", "—", "—", "—"])
        _border_row(ws3, ws3.max_row, len(h3))
    _autosize(ws3, [16, 12, 26, 24, 24, 16, 18, 34, 11, 24])

    # =================== Sheet4 风险汇总 ===================
    ws4 = wb.create_sheet("风险汇总")
    ws4.append(["风险等级", "数量", "占比"])
    _style_header(ws4, 3)
    total = len(records) or 1
    for lv in ("高风险", "中风险", "低风险"):
        cnt = sum(1 for r in records if r.get("risk_level") == lv)
        ws4.append([lv, cnt, round(cnt / total, 4)])
        c = ws4.cell(row=ws4.max_row, column=1)
        c.fill = RISK_FILL.get(lv, PatternFill())
        _border_row(ws4, ws4.max_row, 3)
    ws4.append([])
    ws4.append(["规则命中统计（同一条记录可命中多条）", "", ""])
    ws4.cell(row=ws4.max_row, column=1).font = Font(name="微软雅黑", size=10, bold=True)
    code_names = {
        "H1": "函证地址与注册地址实质不一致",
        "H2": "函证地址为空/无法解析（地址不可用）",
        "H3": "一址多照（地址对应多个主体）",
        "H4": "注册地址频繁变更",
        "M1": "地址表述/格式差异",
        "M2": "楼层或房号信息缺失",
        "M3": "名称简称/名称不一致，主体唯一性未确认",
        "M4": "统一社会信用代码校验异常",
        "M5": "电话区号与地址城市不一致",
        "M6": "函证类型与主体性质不匹配",
        "M7": "函证地址缺少门牌号（投递点不明确）",
        "M8": "注册地址缺失，无法执行一致性核验",
        "M9": "未记录工商信息来源/网址",
        "M10": "未附工商信息查询界面截图",
    }
    hit = {}
    for r in records:
        for c in r.get("risk_codes", []):
            hit[c] = hit.get(c, 0) + 1
    start = ws4.max_row + 1
    for code in sorted(code_names):
        ws4.append(["%s %s" % (code, code_names[code]), hit.get(code, 0), ""])
    for row in ws4.iter_rows(min_row=start, max_row=ws4.max_row):
        for cell in row:
            cell.font = BODY_FONT
            cell.border = BORDER
    _autosize(ws4, [50, 10, 10])

    # =================== Sheet5 数据来源与口径 ===================
    ws5 = wb.create_sheet("数据来源与口径")
    ws5.append(["项目", "内容"])
    _style_header(ws5, 2)
    sources = sorted({(r.get("reg_source") or "").strip()
                      for r in records if (r.get("reg_source") or "").strip()})
    rows = [
        ("询证信息来源", "被审计单位提供的函证清单（%s，格式 %s，解析方式 %s，表头行 %s，有效记录 %s 条）"
         % (meta.get("source_file", ""), meta.get("source_ext", ""),
            meta.get("parse_mode", ""), meta.get("header_row", "-"),
            meta.get("records", len(records)))),
        ("工商信息来源", "；".join(sources) if sources else "未记录（不确定）"),
        ("工商信息获取渠道要求", "官方渠道优先：国家企业信用信息公示系统（www.gsxt.gov.cn，含地方局公示入口）；"
                                 "备选第三方：企查查（www.qcc.com）、天眼查（www.tianyancha.com）等，"
                                 "第三方信息应与官方公示结果交叉验证后使用"),
        ("来源网址记录", "逐条记录于本表「来源网址」列及「附件索引表」，并在底稿附录一汇总"),
        ("证据留痕", "工商信息查询界面截图按索引号 %s-序号归档于「附件」目录，"
                     "本表「查看截图」列提供超链接（共 %d 个附件）" % (index_no, len(manifest))),
        ("字段映射", "; ".join("%s←%s" % (k, v) for k, v in (meta.get("columns_mapped") or {}).items())),
        ("匹配算法", "一级字符串精确匹配；二级语义相似度（序列比0.45 / 二元组Jaccard 0.30 / "
                     "行政区划层级0.25，行政区划冲突设上限：省级35、市级55、区县级75）；"
                     "三级企业信息合理性（名称、信用代码GB32100-2015、电话区号、函证类型、一址多照聚簇）"),
        ("判定阈值", "匹配度≥95且无行政区划冲突=一致；80~95=基本一致；60~80=部分一致；<60=不一致；"
                     "缺可比对基准=无法比对"),
        ("未确认信息处理", "凡缺乏可比对基准（未提供注册地址/工商登记名称/来源网址/查询截图）"
                           "一律标注“不确定”，不作一致性假设，并在底稿中说明程序受限范围"),
        ("编制日期", date.today().isoformat()),
    ]
    for k, v in rows:
        ws5.append([k, v])
        _border_row(ws5, ws5.max_row, 2, (2,))
    _autosize(ws5, [20, 110])

    wb.save(out_path)
    return out_path


def _style_header(ws, ncols, row=1, fill=None):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        if fill is not None:
            cell.fill = fill
        elif row == 1 or cell.fill.fgColor.rgb in (None, "00000000"):
            cell.fill = HEAD_FILL
        cell.font = HEAD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


# ---------------------------------------------------------------------------
# Word 底稿
# ---------------------------------------------------------------------------
def _set_cn_font(run, name="宋体", size=None, bold=None):
    from docx.oxml.ns import qn
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size:
        run.font.size = size
    if bold is not None:
        run.font.bold = bold


def _add_hyperlink(paragraph, url, text, size=8):
    """在段落中插入可点击超链接（python-docx 原生不支持，需操作 XML）。"""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.shared import Pt
    try:
        r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    except Exception:  # noqa: BLE001
        run = paragraph.add_run(text)
        _set_cn_font(run, "宋体", Pt(size))
        return
    hl = OxmlElement("w:hyperlink")
    hl.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:eastAsia"), "宋体")
    fonts.set(qn("w:ascii"), "宋体")
    rPr.append(fonts)
    rPr.append(color)
    rPr.append(u)
    rPr.append(sz)
    run.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    hl.append(run)
    paragraph._p.append(hl)


def _sec(doc, title, pt_size=12):
    from docx.shared import Pt
    ph = doc.add_paragraph()
    _set_cn_font(ph.add_run(title), "黑体", Pt(pt_size), True)
    return ph


def _para(doc, text, indent=True, size=10.5):
    from docx.shared import Pt
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.first_line_indent = Pt(21)
    _set_cn_font(p.add_run(text), "宋体", Pt(size))
    return p


def build_workpaper(records, meta, out_path, project="", prepared_by="", reviewed_by="",
                    manifest=None, by_seq=None, index_no="B-3-1"):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt

    manifest = manifest or []
    by_seq = by_seq or {}

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    h = doc.add_heading("", level=0)
    r = h.add_run("函证地址核对执行记录")
    _set_cn_font(r, "黑体", Pt(18), True)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info = doc.add_paragraph()
    _set_cn_font(info.add_run(
        "被审计单位/项目：%s        索引号：%s        编制人：%s        复核人：%s        编制日期：%s"
        % (project or "＿＿＿＿", index_no, prepared_by or "＿＿＿", reviewed_by or "＿＿＿",
           date.today().isoformat())), "宋体", Pt(9))
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER

    high = [r for r in records if r.get("risk_level") == "高风险"]
    mid = [r for r in records if r.get("risk_level") == "中风险"]
    low = [r for r in records if r.get("risk_level") == "低风险"]
    diff_records = [r for r in records
                    if any(d.get("same") is False for d in r.get("diff_rows", []))]
    unk_records = [r for r in records
                   if any(d.get("same") is None for d in r.get("diff_rows", []))]

    # ---------- 一、审计目的 ----------
    _sec(doc, "一、审计目的")
    _para(doc, "本程序旨在对财务报表审计过程中拟寄发的银行询证函、客户询证函、供应商询证函，"
               "就被审计单位提供的询证信息（公司名称、函证地址）与工商登记信息（公司名称、注册地址）"
               "执行一致性核对，识别函证地址异常风险，以支持函证程序的适当性与函证结果的可依赖性，"
               "降低因函证地址错误导致的审计风险。")

    # ---------- 二、执行程序 ----------
    _sec(doc, "二、执行程序")
    for t in [
        "1. 取得被审计单位提供的函证清单，提取被函证单位名称、统一社会信用代码、函证地址、"
        "注册地址、联系电话、联系人及函证类型等信息；",
        "2. 通过公开工商信息渠道查询被函证单位的登记名称与注册地址，并记录查询平台、查询网址与查询日期；",
        "3. 对查询界面进行截图留存，按索引号编制附件并与核对记录建立索引关系；",
        "4. 对企业名称与地址执行标准化处理，执行三级匹配并逐项比对差异；",
        "5. 按既定规则识别高、中、低三级风险并保留每一判断的依据；",
        "6. 形成审计判断与后续应对建议，编制本执行记录。"]:
        _para(doc, t)

    # ---------- 三、数据来源 ----------
    _sec(doc, "三、数据来源")
    sources = sorted({(r.get("reg_source") or "").strip()
                      for r in records if (r.get("reg_source") or "").strip()})
    _para(doc, "1. 询证信息来源：被审计单位提供的函证清单（%s，格式 %s，解析方式 %s，"
               "表头行 %s，有效记录 %s 条）。字段映射：%s。"
          % (meta.get("source_file", ""), meta.get("source_ext", ""), meta.get("parse_mode", ""),
             meta.get("header_row", "-"), meta.get("records", len(records)),
             "; ".join("%s←%s" % (k, v) for k, v in (meta.get("columns_mapped") or {}).items()) or "按标准字段读取"))
    _para(doc, "2. 工商信息来源：%s。"
               "获取渠道以官方公示信息为优先，即国家企业信用信息公示系统"
               "（https://www.gsxt.gov.cn ，含各地方市场监督管理局公示入口）；"
               "第三方平台（企查查 https://www.qcc.com 、天眼查 https://www.tianyancha.com 等）"
               "作为备选来源，其登记信息应与官方公示结果交叉验证后使用。"
          % ("；".join(sources) if sources else "未记录（不确定）"))
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(21)
    _set_cn_font(p.add_run("3. 主要信息查询入口："), "宋体", Pt(10.5))
    _add_hyperlink(p, "https://www.gsxt.gov.cn",
                   "国家企业信用信息公示系统（官方，优先）", size=10.5)
    _set_cn_font(p.add_run("；"), "宋体", Pt(10.5))
    _add_hyperlink(p, "https://www.qcc.com", "企查查（备选）", size=10.5)
    _set_cn_font(p.add_run("；"), "宋体", Pt(10.5))
    _add_hyperlink(p, "https://www.tianyancha.com", "天眼查（备选）", size=10.5)
    _set_cn_font(p.add_run("。逐条查询网址及查询日期详见附录一，查询界面截图详见附录二。"),
                 "宋体", Pt(10.5))
    _para(doc, "4. 说明：被审计单位提供的询证信息与其真实性、完整性由被审计单位负责，"
               "我们已按审计准则要求实施相应程序；工商登记信息来源于上述公开渠道，"
               "查询时点见附录一。")

    # ---------- 四、核验方法 ----------
    _sec(doc, "四、核验方法")
    for t in [
        "1. 标准化：企业名称统一组织形式表述并提取字号（含简称还原）；地址按省/市/区县/详址分层解析，"
        "统一道路、门牌号、楼栋房号表述，并对同义词、中文数字进行归一。",
        "2. 一级匹配（精确）：标准化后字符串完全一致即判定一致。",
        "3. 二级匹配（语义）：以序列相似度0.45、字符二元组Jaccard 0.30、行政区划层级得分0.25加权计算"
        "匹配度；存在行政区划冲突时设定匹配度上限（省级35、市级55、区县级75），防止详址巧合导致的误判。",
        "4. 三级匹配（合理性）：校验企业名称一致性、统一社会信用代码校验位（GB 32100-2015）、"
        "联系电话区号与地址城市一致性、函证类型与主体性质匹配性，并识别“一址多照”地址聚簇。",
        "5. 逐项差异比对：将“被审计单位提供的询证信息”与“工商登记信息”按公司名称、省份、地市、区县、"
        "道路、门牌号、楼栋、房间/楼层八个项目逐一比对并列示差异。",
        "6. 判定标准：匹配度≥95且无行政区划冲突为“一致”；80~95为“基本一致”；60~80为“部分一致”；"
        "<60为“不一致”；缺乏可比对基准的为“无法比对（不确定）”。"]:
        _para(doc, t)

    # ---------- 五、信息对照 ----------
    _sec(doc, "五、被审计单位提供的询证信息与工商登记信息对照")
    _para(doc, "本次共核对 %d 条函证记录，逐条对照情况如下表；标注“（未提供）”的项目表示"
               "被审计单位或公开渠道未提供该项信息，相关结论标注为不确定。" % len(records))

    t5 = doc.add_table(rows=1, cols=6)
    t5.style = "Table Grid"
    for i, txt in enumerate(["序号", "被审计单位提供的询证信息", "工商登记信息",
                             "信息来源及查询网址", "附件索引号", "差异结论"]):
        cell = t5.rows[0].cells[i]
        cell.text = ""
        _set_cn_font(cell.paragraphs[0].add_run(txt), "黑体", Pt(8), True)
    for n, rec in enumerate(records, start=1):
        seq = rec.get("index", n)
        items = by_seq.get(seq, [])
        codes = "、".join(i["索引号"] for i in items) or "（未附）"
        cells = t5.add_row().cells
        supplied = "公司名称：%s\n函证地址：%s" % (
            rec.get("entity_name", ""), rec.get("confirm_address", "") or "（空白）")
        registered = "公司名称：%s\n注册地址：%s" % (
            rec.get("registered_name", "") or "（未提供）",
            rec.get("registered_address", "") or "（未提供）")
        bad = [d for d in rec.get("diff_rows", []) if d.get("same") is False]
        unk = [d for d in rec.get("diff_rows", []) if d.get("same") is None]
        concl = "无差异" if not bad else "存在差异（%d 项）" % len(bad)
        if unk:
            concl += "；待确认（%d 项）" % len(unk)
        vals = [str(seq), supplied, registered, None, codes, concl]
        for j, v in enumerate(vals):
            cells[j].text = ""
            if v is not None:
                _set_cn_font(cells[j].paragraphs[0].add_run(v), "宋体", Pt(8))
        # 来源与网址（可点击）
        pc = cells[3].paragraphs[0]
        pc.text = ""
        _set_cn_font(pc.add_run("%s\n" % (rec.get("reg_source") or "（未提供来源）")), "宋体", Pt(8))
        url = (rec.get("reg_source_url") or "").strip()
        if url.startswith("http"):
            _add_hyperlink(pc, url, url, size=8)
        else:
            _set_cn_font(pc.add_run("（未记录查询网址）"), "宋体", Pt(8))
        _set_cn_font(pc.add_run("\n查询日期：%s" % (rec.get("query_date") or "（未记录）")),
                     "宋体", Pt(8))

    # ---------- 六、逐项差异说明 ----------
    _sec(doc, "六、逐项差异说明")
    if not diff_records and not unk_records:
        _para(doc, "经逐项比对，被审计单位提供的询证信息与工商登记信息在各比对项目上均一致，"
                   "未发现差异事项。")
    else:
        _para(doc, "下列记录存在差异或无法比对事项，逐项说明如下：")
        for k, rec in enumerate(diff_records + [r for r in unk_records if r not in diff_records], start=1):
            seq = rec.get("index", "")
            codes = "、".join(i["索引号"] for i in by_seq.get(seq, [])) or "（未附截图）"
            ph = doc.add_paragraph()
            _set_cn_font(ph.add_run("记录 %s｜%s（附件索引号 %s）"
                                    % (seq, rec.get("entity_name", ""), codes)),
                         "黑体", Pt(10.5), True)
            for d in rec.get("diff_rows", []):
                if d.get("same") is True:
                    continue
                mark = "【差异】" if d.get("same") is False else "【待确认】"
                _para(doc, "%s%s：被审计单位提供「%s」，工商登记信息「%s」。%s"
                      % (mark, d.get("item", ""), d.get("supplied", "") or "空",
                         d.get("registered", "") or "空", d.get("note", "")), indent=True, size=10)
            _para(doc, "综合结论：%s；匹配度 %s；风险等级 %s。"
                  % (rec.get("addr_status", ""), _deg(rec.get("addr_score")),
                     rec.get("risk_level", "")), indent=True, size=10)

    # ---------- 七、异常事项 ----------
    _sec(doc, "七、异常事项")
    abnormal = [r for r in records if r.get("risk_level") in ("高风险", "中风险")]
    if not abnormal:
        _para(doc, "本次核验未发现需要报告的异常事项。")
    else:
        for k, rec in enumerate(abnormal, start=1):
            seq = rec.get("index", "")
            codes = "、".join(i["索引号"] for i in by_seq.get(seq, [])) or "（未附截图）"
            _para(doc, "%d. 【%s｜%s】%s（附件索引号 %s）：%s。处置建议：%s"
                  % (k, rec.get("risk_level", ""), "/".join(rec.get("risk_codes", [])),
                     rec.get("entity_name", ""), codes,
                     rec.get("explanation", ""), rec.get("advice", "")))

    # ---------- 八、审计结论 ----------
    _sec(doc, "八、审计结论")
    conc = []
    if high:
        conc.append("经核对，存在 %d 条高风险事项，被审计单位提供的询证信息与工商登记信息存在实质性差异"
                    "或地址不可用/来源不可追溯，函证程序的适当性受到影响。我们已提请项目组暂缓寄发相关函证，"
                    "在取得被函证单位最新工商登记资料、核实有效投递地址后再行寄发，并根据需要扩大审计程序"
                    "（包括但不限于检查交易合同、验收单据、结算凭据及期后回款情况）。" % len(high))
    if mid:
        conc.append("另有 %d 条中风险事项，主要表现为逐项差异、名称以简称列示、缺少来源网址或查询截图"
                    "等证据留痕不足的情形。我们已建议补充工商信息来源与截图、通过电话或公开渠道核实后再行寄发。"
                    % len(mid))
    if low:
        conc.append("其余 %d 条记录的询证信息与工商登记信息一致，相关函证可按既定程序直接寄发"
                    "并保留邮寄凭证。" % len(low))
    conc.append("本执行记录所载核对结论仅基于上述询证信息、工商登记信息来源及所述核验方法；"
                "对无法获得充分适当证据支持的事项，已在结果中标注为“不确定”，未作一致性假设。"
                "工商登记信息查询结果以查询时点的公示信息为准，此后登记事项变更不影响查询时点的核对结论。")
    for c in conc:
        _para(doc, c)

    # ---------- 附录一 来源记录 ----------
    doc.add_page_break()
    _sec(doc, "附录一：工商登记信息来源记录")
    t6 = doc.add_table(rows=1, cols=6)
    t6.style = "Table Grid"
    for i, txt in enumerate(["附件索引号", "被函证单位", "工商信息来源（平台）",
                             "查询网址", "查询日期", "附件文件名"]):
        cell = t6.rows[0].cells[i]
        cell.text = ""
        _set_cn_font(cell.paragraphs[0].add_run(txt), "黑体", Pt(8), True)
    if manifest:
        for it in manifest:
            cells = t6.add_row().cells
            for j, v in enumerate([it["索引号"], it["被函证单位"], it["工商信息来源"] or "（未提供）",
                                   None, it["查询日期"] or "（未记录）", it["附件文件名"]]):
                cells[j].text = ""
                if v is not None:
                    _set_cn_font(cells[j].paragraphs[0].add_run(v), "宋体", Pt(8))
            pc = cells[3].paragraphs[0]
            pc.text = ""
            url = it.get("来源网址") or ""
            if url.startswith("http"):
                _add_hyperlink(pc, url, url, size=8)
            else:
                _set_cn_font(pc.add_run("（未记录）"), "宋体", Pt(8))
    else:
        cells = t6.add_row().cells
        for j, v in enumerate(["—", "—", "—", "本次未归集附件", "—", "—"]):
            cells[j].text = ""
            _set_cn_font(cells[j].paragraphs[0].add_run(v), "宋体", Pt(8))

    # ---------- 附录二 查询界面截图 ----------
    doc.add_page_break()
    _sec(doc, "附录二：工商信息查询界面截图")
    _para(doc, "下列截图系核对时点从公开工商信息渠道查询取得，已按索引号归档留存，"
               "作为本核对程序获取审计证据的记录。共 %d 张。" % len(manifest))
    img_manifest = [it for it in manifest if os.path.exists(it.get("绝对路径", ""))
                    and os.path.splitext(it["附件文件名"])[1].lower()
                    in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")]
    if not img_manifest:
        _para(doc, "本次未归集到可嵌入的查询界面截图（未提供截图目录或文件名）。")
    for it in img_manifest:
        cap = doc.add_paragraph()
        _set_cn_font(cap.add_run(
            "附件索引号 %s ｜ %s ｜ %s ｜ 查询日期 %s"
            % (it["索引号"], it["被函证单位"], it["工商信息来源"] or "（来源未记录）",
               it["查询日期"] or "（未记录）")), "黑体", Pt(9), True)
        try:
            doc.add_picture(it["绝对路径"], width=Inches(6.0))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:  # noqa: BLE001
            _para(doc, "（图片 %s 嵌入失败，请直接打开附件目录查看）" % it["附件文件名"])
        doc.add_paragraph()

    doc.add_paragraph()
    sign = doc.add_paragraph()
    _set_cn_font(sign.add_run("编制人：＿＿＿＿＿＿    复核人：＿＿＿＿＿＿    日期：＿＿＿＿＿＿"),
                 "宋体", Pt(10.5))

    doc.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Markdown 摘要
# ---------------------------------------------------------------------------
def build_markdown(records, meta, out_path, manifest=None, by_seq=None, index_no="B-3-1"):
    manifest = manifest or []
    by_seq = by_seq or {}
    high = [r for r in records if r.get("risk_level") == "高风险"]
    mid = [r for r in records if r.get("risk_level") == "中风险"]
    low = [r for r in records if r.get("risk_level") == "低风险"]
    L = []
    L.append("# 函证地址核对结果摘要\n")
    L.append("> 询证信息来源：%s ｜ 记录数：%d ｜ 附件数：%d ｜ 生成日期：%s\n"
             % (meta.get("source_file", ""), len(records), len(manifest), date.today().isoformat()))
    L.append("## 一、总体情况\n")
    L.append("| 风险等级 | 数量 |\n|---|---|")
    L.append("| 高风险 | %d |" % len(high))
    L.append("| 中风险 | %d |" % len(mid))
    L.append("| 低风险 | %d |" % len(low))
    L.append("")
    L.append("## 二、信息对照与核对结论\n")
    L.append("| # | 附件索引号 | 被审计单位提供的询证信息 | 工商登记信息 | 来源与网址 | 匹配结果 | 匹配度 | 风险等级 | 逐项差异 | 审计建议 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for n, r in enumerate(records, start=1):
        seq = r.get("index", n)
        codes = "、".join(i["索引号"] for i in by_seq.get(seq, [])) or "—"
        sup = "名称：%s<br>地址：%s" % (r.get("entity_name", ""),
                                      r.get("confirm_address", "") or "（空白）")
        reg = "名称：%s<br>地址：%s" % (r.get("registered_name", "") or "（未提供）",
                                      r.get("registered_address", "") or "（未提供）")
        src = "%s<br>%s<br>%s" % (r.get("reg_source", "") or "（未提供来源）",
                                  r.get("reg_source_url", "") or "（未记录网址）",
                                  r.get("query_date", "") or "（未记录日期）")
        L.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            seq, codes, sup, reg, src, r.get("addr_status", ""), _deg(r.get("addr_score")),
            r.get("risk_level", ""),
            (r.get("diff_text", "") or "").replace("|", "/"),
            (r.get("advice", "") or "").replace("|", "/")))
    L.append("")
    L.append("## 三、逐项差异明细\n")
    L.append("| # | 比对项目 | 被审计单位提供 | 工商登记信息 | 是否一致 | 说明 |")
    L.append("|---|---|---|---|---|---|")
    for n, r in enumerate(records, start=1):
        for d in r.get("diff_rows", []):
            same = {True: "一致", False: "**存在差异**", None: "无法比对"}[d.get("same")]
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                r.get("index", n), d.get("item", ""), d.get("supplied", "") or "（空）",
                d.get("registered", "") or "（空）", same, d.get("note", "")))
    L.append("")
    L.append("## 四、附件索引表\n")
    L.append("| 附件索引号 | 被函证单位 | 附件文件 | 来源平台 | 来源网址 | 查询日期 |")
    L.append("|---|---|---|---|---|---|")
    for it in manifest:
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            it["索引号"], it["被函证单位"], it["附件文件名"],
            it["工商信息来源"] or "—", it["来源网址"] or "—", it["查询日期"] or "—"))
    L.append("")
    L.append("## 五、判断依据留痕（逐条）\n")
    for n, r in enumerate(records, start=1):
        L.append("### %d. %s" % (r.get("index", n), r.get("entity_name", "")))
        for e in r.get("evidence", []):
            L.append("- %s" % e)
        L.append("- 【风险等级】%s；【审计判断】%s" % (
            r.get("risk_level", ""), r.get("advice", "")))
        L.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return out_path
