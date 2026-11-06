# -*- coding: utf-8 -*-
"""
生成示例函证清单 + 模拟工商信息查询界面截图（仅用于演示与测试，非审计工作流组成部分）。

用法： python make_sample.py
输出： ../assets/sample_input.csv 与 ../assets/sample_attachments/*.png
依赖： Pillow
"""
import csv
import hashlib
import os

from PIL import Image, ImageDraw, ImageFont

OUT = r"C:\Users\15274\.workbuddy\workspace\files\10368\3f5a46d7-afa5-48ad-8519-72df51c718e5\confirmation-address-auditor"
ATT = os.path.join(OUT, "assets", "sample_attachments")
os.makedirs(ATT, exist_ok=True)

USCC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"
W = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]


def fix(p17):
    total = sum(USCC_CHARS.index(c) * W[i] for i, c in enumerate(p17))
    r = 31 - (total % 31)
    r = 0 if r == 31 else r
    return p17 + USCC_CHARS[r]


def bad(p17):
    return p17 + ("A" if fix(p17)[-1] != "A" else "B")


GSXT = "https://www.gsxt.gov.cn/index.html"
QCC = "https://www.qcc.com/"
TYC = "https://www.tianyancha.com/"

rows = [
    dict(seq=1, name="长沙湘江科技有限公司", uscc=fix("91430100MA4L1A2B3"),
         addr="湖南省长沙市岳麓区麓谷大道627号", reg="湖南省长沙市岳麓区麓谷大道627号",
         phone="0731-88886666", contact="李会计", ctype="客户函证", regname="长沙湘江科技有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="01.png", chg=""),
    dict(seq=2, name="湖南三一智能装备有限责任公司", uscc=fix("91430100MA4L2C4D5"),
         addr="湖南省长沙市长沙县开发区三一路1号", reg="湖南省长沙市长沙县开发区三一路1号",
         phone="0731-84031188", contact="王经理", ctype="供应商函证", regname="湖南三一智能装备有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="02.png", chg=""),
    dict(seq=3, name="长沙远大住宅工业集团股份有限公司", uscc=fix("91430100MA4L3E6F7"),
         addr="湖南省长沙市岳麓区麓谷大道627号远大住工大厦", reg="长沙市岳麓区麓谷大道627号远大住工大厦",
         phone="0731-88991122", contact="刘女士", ctype="供应商函证", regname="长沙远大住宅工业集团股份有限公司",
         src="企查查", url=QCC, qd="2026-09-08", shot="03.png", chg=""),
    # 有来源网址、无截图 → M10
    dict(seq=4, name="深圳市华信物流有限公司", uscc=fix("91440300MA4L4G8H9"),
         addr="广东省深圳市南山区科技园南区A栋3楼", reg="广东省深圳市南山区高新南一道9号A栋301室",
         phone="0755-26668888", contact="陈先生", ctype="客户函证", regname="深圳市华信物流有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="", chg=""),
    dict(seq=5, name="广州天成贸易有限公司", uscc=fix("91440100MA4L5J1K2"),
         addr="广东省广州市天河区天河路200号", reg="广东省深圳市福田区福华路100号",
         phone="020-38889999", contact="赵经理", ctype="客户函证", regname="广州天成贸易有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="05.png", chg=""),
    dict(seq=6, name="上海恒瑞医药有限公司", uscc=fix("91310100MA4L6L3M4"),
         addr="", reg="上海市浦东新区张江高科技园区哈雷路998号",
         phone="021-58991234", contact="孙女士", ctype="客户函证", regname="上海恒瑞医药有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="06.png", chg=""),
    # 一址多照 + 地址频繁变更（H3+H4）+ 两张截图
    dict(seq=7, name="长沙金桥商务咨询有限公司", uscc=fix("91430100MA4L7N5P6"),
         addr="湖南省长沙市开福区芙蓉中路593号B座2201", reg="湖南省长沙市开福区芙蓉中路593号B座2201",
         phone="0731-82223333", contact="周先生", ctype="供应商函证", regname="长沙金桥商务咨询有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="07.png|07b.png", chg="3"),
    dict(seq=8, name="长沙普惠网络科技有限公司", uscc=fix("91430100MA4L8Q7R8"),
         addr="长沙市开福区芙蓉中路593号B座2201", reg="湖南省长沙市开福区芙蓉中路593号B座2201",
         phone="0731-82224444", contact="吴女士", ctype="客户函证", regname="长沙普惠网络科技有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="08.png", chg=""),
    dict(seq=9, name="长沙德胜企业管理有限公司", uscc=fix("91430100MA4L9U9T1"),
         addr="长沙市开福区芙蓉中路593号B座2201", reg="湖南省长沙市开福区芙蓉中路593号B座2201",
         phone="0731-82225555", contact="郑先生", ctype="客户函证", regname="长沙德胜企业管理有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="09.png", chg=""),
    # 第三方平台、未记录网址、无截图 → M9+M10
    dict(seq=10, name="武汉长江光电有限公司", uscc=bad("91420100MA4LAC2B3"),
         addr="湖北省武汉市东湖新技术开发区光谷大道77号", reg="湖北省武汉市东湖新技术开发区光谷大道77号",
         phone="021-66668888", contact="冯先生", ctype="供应商函证", regname="武汉长江光电有限公司",
         src="天眼查", url="", qd="", shot="", chg=""),
    dict(seq=11, name="北京京华机电设备有限公司", uscc=fix("91110100MA4LBD4E5"),
         addr="北京市朝阳区建国路88号", reg="北京市朝阳区建国路88号SOHO现代城A座1806室",
         phone="010-85886688", contact="蒋女士", ctype="供应商函证", regname="北京京华机电设备有限公司",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="11.png", chg=""),
    # 无来源、无网址、无截图、无注册地址 → M3+M4+M7+M8+M9+M10
    dict(seq=12, name="东莞市长盛塑胶制品厂", uscc="",
         addr="东莞市长安镇", reg="",
         phone="", contact="韩先生", ctype="供应商询证", regname="",
         src="", url="", qd="", shot="", chg=""),
    dict(seq=13, name="成都锦江商贸有限公司", uscc=fix("91510100MA4LCF6G7"),
         addr="四川省成都市锦江区红星路三段1号", reg="四川省成都市锦江区红星路三段1号",
         phone="028-86668888", contact="杨先生", ctype="银行函证", regname="成都锦江商贸有限公司",
         src="企查查", url=QCC, qd="2026-09-08", shot="13.png", chg=""),
    dict(seq=14, name="招商银行股份有限公司长沙分行", uscc=fix("91430100MA4LDH8J9"),
         addr="湖南省长沙市芙蓉区五一大道456号", reg="湖南省长沙市芙蓉区五一大道456号",
         phone="0731-85556666", contact="对公柜台", ctype="银行函证", regname="招商银行股份有限公司长沙分行",
         src="国家企业信用信息公示系统", url=GSXT, qd="2026-09-08", shot="14.png", chg=""),
]

# ---------------- 生成模拟查询界面截图 ----------------
FONT = "C:/Windows/Fonts/msyh.ttc"

def _f(sz, bold=False):
    p = "C:/Windows/Fonts/msyhbd.ttc" if bold else FONT
    try:
        return ImageFont.truetype(p, sz)
    except Exception:
        return ImageFont.truetype(FONT, sz)


def make_shot(path, title, url, head_color, subtitle, rec):
    Wd, Ht = 1040, 660
    im = Image.new("RGB", (Wd, Ht), "#FFFFFF")
    d = ImageDraw.Draw(im)
    # 窗口外框
    d.rectangle([0, 0, Wd - 1, Ht - 1], outline="#B7B7B7", width=2)
    # 标题栏
    d.rectangle([0, 0, Wd, 60], fill=head_color)
    d.text((22, 17), title, font=_f(24, True), fill="#FFFFFF")
    d.text((Wd - 470, 24), url, font=_f(15), fill="#D9E2F3")
    # 导航条
    d.rectangle([0, 60, Wd, 96], fill="#EEF3F9")
    d.text((22, 68), "首页      企业信用信息公示      信息公告      查询服务", font=_f(15), fill="#1F4E79")
    d.line([0, 96, Wd, 96], fill="#C9D6E4")
    # 面包屑
    d.text((22, 110), "当前位置：%s  >  企业（机构）基本信息查询" % title, font=_f(14), fill="#7F7F7F")
    # 查询结果卡片
    d.rectangle([22, 142, Wd - 22, Ht - 80], outline="#C9D6E4")
    d.rectangle([22, 142, Wd - 22, 182], fill="#EAF1F8")
    d.text((40, 150), "企业（机构）基本信息", font=_f(17, True), fill="#1F4E79")
    d.rectangle([Wd - 132, 150, Wd - 42, 174], fill="#C6E0B4", outline="#9DC284")
    d.text((Wd - 122, 152), "查询成功", font=_f(14, True), fill="#375623")

    yy = 202
    items = [
        ("统一社会信用代码", rec["uscc"] or "（未查询到）"),
        ("企业名称", rec["regname"] or rec["name"]),
        ("企业类型", "有限责任公司" if "有限" in rec["name"] else "其他"),
        ("注册地址", rec["reg"] or "（未查询到登记地址）"),
        ("登记状态", "存续（在营、开业、在册）"),
        ("成立日期", "2015-06-18"),
        ("登记机关", subtitle),
    ]
    for k, v in items:
        d.rectangle([22, yy, 250, yy + 40], fill="#F7F9FC", outline="#DCE5EF")
        d.text((38, yy + 10), k, font=_f(15), fill="#404040")
        d.text((268, yy + 10), str(v)[:46], font=_f(15, True), fill="#1F1F1F")
        yy += 40
    d.text((38, yy + 14), "查询时间：2026-09-08 10:24:31", font=_f(14), fill="#7F7F7F")
    d.text((38, yy + 40), "本页信息系从公开渠道查询取得，仅用于审计核对程序留痕。", font=_f(13), fill="#A6A6A6")
    # 示例水印
    d.text((Wd - 300, Ht - 40), "【示例数据 · 模拟查询页面】", font=_f(14, True), fill="#C00000")
    im.save(path)
    return path

made = []
for r in rows:
    if not r["shot"]:
        continue
    for fn in r["shot"].split("|"):
        src = r["src"] or "公开工商信息渠道"
        if "国家" in src:
            head, url, sub = "#1F4E79", "https://www.gsxt.gov.cn/index.html", "长沙市市场监督管理局"
        elif "企查查" in src:
            head, url, sub = "#2E75B6", "https://www.qcc.com/", "企查查·工商登记信息"
        elif "天眼查" in src:
            head, url, sub = "#C55A11", "https://www.tianyancha.com/", "天眼查·工商登记信息"
        else:
            head, url, sub = "#595959", "-", "公开工商信息渠道"
        make_shot(os.path.join(ATT, fn), src if "国家" not in src else "国家企业信用信息公示系统",
                  url, head, sub, r)
        made.append(fn)

# ---------------- 写出示例 CSV ----------------
header = ["被函证单位名称", "统一社会信用代码", "函证地址", "注册地址", "联系电话", "联系人",
          "函证类型", "工商登记名称", "工商信息来源", "来源网址", "查询日期",
          "查询界面截图附件", "注册地址变更次数"]
out = os.path.join(OUT, "assets", "sample_input.csv")
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(header)
    for r in rows:
        w.writerow([r["name"], r["uscc"], r["addr"], r["reg"], r["phone"], r["contact"],
                    r["ctype"], r["regname"], r["src"], r["url"], r["qd"], r["shot"], r["chg"]])

print("[OK] sample_input.csv -> %d 行" % len(rows))
print("[OK] 模拟截图 %d 张：%s" % (len(made), ", ".join(made)))
