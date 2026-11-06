"""生成带文本层的多页 PDF 测试样本。"""
from pathlib import Path

import pymupdf as fitz

LINES = [
    "设备采购合同",
    "合同编号：HT-2026-1008",
    "甲方（买方）：上海示例制造有限公司",
    "乙方（卖方）：北京示例供应链有限公司",
    "第一条 标的物",
    "乙方向甲方供应精密轴承组件A型120套。",
    "第二条 合同价款",
    "本合同总价为人民币壹拾壹万壹仟贰佰伍拾元整（¥111,250.00），其中",
    "不含税金额100,000.00元，增值税税额11,250.00元。该价格为暂定价。",
    "第三条 履行期限",
    "本合同自2026年10月20日起至2027年10月19日止。",
    "第四条 付款方式",
    "1、合同签订后5个工作日内，甲方支付合同总价的30%作为预付款；",
    "2、货物验收合格后15个工作日内，甲方支付合同总价的60%；",
    "3、剩余10%作为质保金。",
    "第五条 违约责任",
    "任何一方违约，应向守约方支付合同总价5%的违约金。",
    "第六条 争议解决",
    "提交上海仲裁委员会仲裁。",
    "甲方（盖章）：            乙方（盖章）：",
    "签订日期：2026年10月18日",
]

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "samples" / "示例-多页合同.pdf"
    doc = fitz.open()
    for pno in range(3):
        page = doc.new_page(width=595, height=842)
        y = 60
        for t in LINES:
            page.insert_text((50, y), t, fontname="china-s", fontsize=11)
            y += 26
        page.insert_text((260, 800), f"第{pno + 1}页 共3页", fontname="china-s", fontsize=9)
    doc.save(str(out))
    doc.close()
    print(out, out.stat().st_size, "bytes")
