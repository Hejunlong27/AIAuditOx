"""生成测试样本：仿真增值税专用发票 + 简单合同。仅用于链路验证，不含真实数据。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def font(size: int):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_invoice(out: Path, dpi_scale: int = 1) -> Path:
    W, H = 1400, 900
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title = font(34)
    f_big = font(22)
    f = font(18)
    f_sm = font(15)

    # 外框
    d.rectangle([30, 30, W - 30, H - 30], outline="#8B1A1A", width=3)
    # 标题
    d.text((W // 2 - 130, 55), "增值税专用发票", font=f_title, fill="#8B1A1A")
    d.text((W // 2 - 70, 100), "（发票联）", font=f_sm, fill="#8B1A1A")

    # 右上号码区
    d.text((W - 480, 55), "发票代码：3100201130", font=f_sm, fill="#333")
    d.text((W - 480, 80), "发票号码：01234567", font=f_sm, fill="#333")
    d.text((W - 480, 105), "开票日期：2026年10月20日", font=f_sm, fill="#333")
    d.text((W - 480, 130), "校验码：8823 1145 6677 9901", font=f_sm, fill="#333")

    # 购买方
    d.text((50, 150), "购买方", font=f_big, fill="#333")
    d.text((160, 152), "名称：上海示例制造有限公司", font=f, fill="#222")
    d.text((160, 180), "纳税人识别号：91310000MA1FL1QH57", font=f, fill="#222")
    d.text((160, 208), "地址、电话：上海市浦东新区示例路 100 号 021-58880000", font=f, fill="#222")
    d.text((160, 236), "开户行及账号：工商银行示例支行 1001234509300012345", font=f, fill="#222")
    d.line([40, 270, W - 40, 270], fill="#8B1A1A", width=2)

    # 销售方
    d.text((50, 285), "销售方", font=f_big, fill="#333")
    d.text((160, 287), "名称：北京示例供应链有限公司", font=f, fill="#222")
    d.text((160, 315), "纳税人识别号：91110108MA01ABCD2X", font=f, fill="#222")
    d.text((160, 343), "地址、电话：北京市海淀区示例大厦 010-62000000", font=f, fill="#222")
    d.text((160, 371), "开户行及账号：建设银行示例支行 1100104500050023456", font=f, fill="#222")
    d.line([40, 405, W - 40, 405], fill="#8B1A1A", width=2)

    # 明细表
    cols = [50, 480, 640, 720, 820, 1000, 1100, 1250, 1350]
    headers = ["货物或应税劳务、服务名称", "规格型号", "单位", "数量", "单价", "金额", "税率", "税额"]
    y = 425
    d.line([40, y, W - 40, y], fill="#8B1A1A", width=2)
    for i, h in enumerate(headers):
        d.text((cols[i] + 4, y + 8), h, font=f_sm, fill="#333")
    y += 40
    d.line([40, y, W - 40, y], fill="#8B1A1A", width=1)

    rows = [
        ["精密轴承组件 A 型", "BRG-A200", "套", "120", "625.00", "75000.00", "13%", "9750.00"],
        ["技术服务费", "-", "项", "1", "25000.00", "25000.00", "6%", "1500.00"],
    ]
    for r in rows:
        y += 10
        for i, cell in enumerate(r):
            d.text((cols[i] + 4, y), cell, font=f_sm, fill="#222")
        y += 30
        d.line([40, y, W - 40, y], fill="#D9B3B3", width=1)

    # 合计
    y += 12
    d.text((50, y), "合    计", font=f, fill="#333")
    d.text((cols[5] + 4, y), "¥100000.00", font=f, fill="#222")
    d.text((cols[7] + 4, y), "¥11250.00", font=f, fill="#222")

    y += 45
    d.line([40, y, W - 40, y], fill="#8B1A1A", width=2)
    d.text((50, y + 12), "价税合计（大写）", font=f, fill="#333")
    d.text((250, y + 12), "壹拾壹万壹仟贰佰伍拾元整", font=f_big, fill="#8B1A1A")
    d.text((900, y + 12), "（小写）¥111250.00", font=f_big, fill="#8B1A1A")

    # 备注
    y += 70
    d.line([40, y, W - 40, y], fill="#8B1A1A", width=1)
    d.text((50, y + 10), "备注：合同号 HT-2026-1008", font=f_sm, fill="#333")

    # 三栏
    y += 60
    d.line([40, y, W - 40, y], fill="#8B1A1A", width=1)
    d.text((60, y + 12), "收款人：张三", font=f_sm, fill="#333")
    d.text((400, y + 12), "复核人：李四", font=f_sm, fill="#333")
    d.text((700, y + 12), "开票人：王五", font=f_sm, fill="#333")
    d.text((1000, y + 12), "销售方：（章）", font=f_sm, fill="#333")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


def make_contract(out: Path) -> Path:
    W, H = 1240, 1754  # A4 @150dpi
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_title = font(30)
    f = font(19)
    f_b = font(20)

    d.text((W // 2 - 150, 80), "设备采购合同", font=f_title, fill="black")
    d.text((W // 2 - 90, 130), "合同编号：HT-2026-1008", font=f, fill="black")

    y = 190
    lines = [
        ("甲方（买方）：上海示例制造有限公司", f_b),
        ("住所：上海市浦东新区示例路 100 号", f),
        ("法定代表人：赵六", f),
        ("乙方（卖方）：北京示例供应链有限公司", f_b),
        ("住所：北京市海淀区示例大厦 18 层", f),
        ("法定代表人：钱七", f),
        ("", f),
        ("根据《中华人民共和国民法典》及相关法律法规，甲乙双方本着平等自愿、", f),
        ("诚实信用的原则，就设备采购事宜达成如下协议：", f),
        ("", f),
        ("第一条 标的物", f_b),
        ("乙方向甲方供应精密轴承组件 A 型 120 套，技术服务 1 项，具体规格", f),
        ("型号见附件一《供货清单》。", f),
        ("", f),
        ("第二条 合同价款", f_b),
        ("本合同总价为人民币壹拾壹万壹仟贰佰伍拾元整（¥111,250.00），其中", f),
        ("不含税金额 100,000.00 元，增值税税额 11,250.00 元。该价格为暂定价，", f),
        ("最终以实际供货数量结算。", f),
        ("", f),
        ("第三条 履行期限", f_b),
        ("本合同自 2026年10月20日 起至 2027年10月19日 止，乙方应于合同生效", f),
        ("后 30 日内完成首批交付。", f),
        ("", f),
        ("第四条 付款方式", f_b),
        ("1、合同签订后 5 个工作日内，甲方支付合同总价的 30% 作为预付款；", f),
        ("2、货物验收合格后 15 个工作日内，甲方支付合同总价的 60%；", f),
        ("3、剩余 10% 作为质保金，质保期满且无质量问题后 30 日内无息支付。", f),
        ("", f),
        ("第五条 违约责任", f_b),
        ("任何一方违约，应向守约方支付合同总价 5% 的违约金；逾期交付的，", f),
        ("每逾期一日按合同总价的 0.5‰ 计算违约金。", f),
        ("", f),
        ("第六条 质量保证", f_b),
        ("乙方保证货物质量符合国家标准，质保期为 24 个月，自验收合格之日起算。", f),
        ("", f),
        ("第七条 争议解决", f_b),
        ("因本合同发生的争议，双方应协商解决；协商不成的，提交上海仲裁委员会仲裁。", f),
        ("", f),
        ("第八条 其他", f_b),
        ("本合同一式肆份，甲乙双方各执贰份，自双方签字盖章之日起生效。", f),
        ("", f),
        ("甲方（盖章）：                    乙方（盖章）：", f_b),
        ("", f),
        ("法定代表人：赵六                  法定代表人：钱七", f),
        ("", f),
        ("签订日期：2026年10月18日          签订日期：2026年10月18日", f),
    ]
    for text, fnt in lines:
        d.text((80, y), text, font=fnt, fill="black")
        y += 36 if fnt is f_b else 32

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent / "samples"
    a = make_invoice(base / "示例-增值税专用发票.png")
    b = make_contract(base / "示例-设备采购合同.png")
    print(a, a.stat().st_size)
    print(b, b.stat().st_size)
