"""回归测试 —— 全部基于构造的文本行，不依赖 OCR 引擎，可离线快速运行。

    python -m pytest tests/ -q          # 有 pytest 时
    python tests/test_pipeline.py       # 无 pytest 时直接跑
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ocr_core import classify, extract_contract, extract_invoice  # noqa: E402
from ocr_core.validate import (  # noqa: E402
    check_arithmetic, cn_amount_to_number, normalize_date, parse_money,
    uscc_checksum_ok,
)


# ---------------------------------------------------------------- validate

def test_cn_amount():
    cases = {
        "壹万贰仟叁佰肆拾伍元陆角柒分": 12345.67,
        "伍佰元整": 500.00,
        "壹亿零贰佰万元整": 102000000.00,
        "叁仟元整": 3000.00,
        "壹拾万元整": 100000.00,
        "玖佰玖拾玖元玖角玖分": 999.99,
        "人民币贰万元整": 20000.00,
        "柒分": 0.07,
    }
    for text, expect in cases.items():
        got = cn_amount_to_number(text)
        assert got is not None and abs(got - expect) < 0.001, f"{text} → {got}，期望 {expect}"


def test_uscc():
    assert uscc_checksum_ok("91310000MA1FL1QH57") is True
    assert uscc_checksum_ok("91350100M000100Y43") is True
    assert uscc_checksum_ok("91310000MA1FL1QH5K") is False
    assert uscc_checksum_ok("110101010101010101") is False
    assert uscc_checksum_ok("12345") is False


def test_date():
    assert normalize_date("2026年10月28日") == "2026-10-28"
    assert normalize_date("2026-1-5") == "2026-01-05"
    assert normalize_date("2019.3.8") == "2019-03-08"
    assert normalize_date("2026/13/40") is None
    assert normalize_date("2010-01-01") is None      # 早于 2015


def test_arithmetic():
    assert check_arithmetic(10000.0, 1300.0, 11300.0)["ok"] is True
    r = check_arithmetic(10000.0, 1300.0, 11300.02)
    assert r["ok"] is False and abs(r["diff"] + 0.02) < 1e-6
    assert check_arithmetic(None, 1300.0, 11300.0)["ok"] is None


def test_money():
    assert parse_money("¥111,250.00") == 111250.00
    assert parse_money("75000.00") == 75000.00
    assert parse_money("无") is None


# ---------------------------------------------------------------- classify

def _lines(texts, page=1, start_y=0, step=24):
    return [{"text": t, "score": 0.99, "page": page,
             "bbox": [0, start_y + i * step, 600, start_y + i * step + 20]}
            for i, t in enumerate(texts)]


def test_classify_invoice():
    lines = _lines(["增值税专用发票", "发票号码：01234567", "价税合计（小写）¥100.00",
                    "税额 ¥13.00", "购买方", "销售方"])
    r = classify.classify_texts(lines)
    assert r["type"] == "vat_invoice", r


def test_classify_contract():
    lines = _lines(["设备采购合同", "合同编号：HT-001", "甲方：A公司", "乙方：B公司",
                    "第一条 标的物", "第二条 价款", "违约责任", "争议解决", "本合同一式两份"])
    r = classify.classify_texts(lines)
    assert r["type"] == "contract", r


def test_classify_generic():
    r = classify.classify_texts(_lines(["今天天气不错", "我们去公园散步"]))
    assert r["type"] == "generic", r


# ---------------------------------------------------------------- 发票抽取

def _invoice_lines():
    """构造一张与真实 OCR 输出结构一致的发票行（含表头与合计行）。"""
    raw = [
        ("发票代码：3100201130", 55, 919),
        ("增值税专用发票", 58, 569),
        ("发票号码：01234567", 80, 919),
        ("开票日期：2026年10月20日", 105, 918),
        ("名称：上海示例制造有限公司", 155, 158),
        ("购买方", 149, 44),
        ("纳税人识别号：91310000MA1FL1QH57", 181, 157),
        ("名称：北京示例供应链有限公司", 289, 158),
        ("销售方", 283, 44),
        ("纳税人识别号：91350100M000100Y43", 315, 157),
        ("货物或应税劳务、服务名称", 434, 53),
        ("规格型号", 432, 480),
        ("单位", 433, 637),
        ("数量", 433, 719),
        ("单价", 431, 819),
        ("金额", 432, 1000),
        ("税率", 430, 1098),
        ("税额", 430, 1248),
        ("精密轴承组件A型", 476, 52),
        ("BRG-A200", 474, 481),
        ("套", 472, 637),
        ("120", 473, 719),
        ("625.00", 472, 819),
        ("75000.00", 474, 1000),
        ("13%", 473, 1100),
        ("9750.00", 474, 1251),
        ("合计", 553, 42),
        ("¥75000.00", 556, 1000),
        ("¥9750.00", 555, 1250),
        ("价税合计（大写）", 614, 48),
        ("壹拾壹万壹仟贰佰伍拾元整", 618, 249),
        ("(小写) ¥111250.00", 616, 913),
        ("备注：合同号HT-2026-1008", 682, 49),
        ("收款人：张三", 743, 57),
        ("复核人：李四", 741, 396),
        ("开票人：王五", 743, 697),
    ]
    return [{"text": t, "score": 0.99, "page": 1,
             "bbox": [x, y, x + 120, y + 22]} for t, y, x in raw]


def test_invoice_extract():
    r = extract_invoice.extract(_invoice_lines())
    f = r["fields"]
    assert f["invoice_no"]["value"] == "01234567"
    assert f["invoice_date"]["value"] == "2026-10-20"
    assert f["buyer_name"]["value"] == "上海示例制造有限公司"
    assert f["seller_name"]["value"] == "北京示例供应链有限公司"
    assert f["amount_ex_tax"]["value"] == 75000.00
    assert f["tax_amount"]["value"] == 9750.00          # 必须取税额列，不能取单价
    assert f["total_amount"]["value"] == 111250.00
    # 75000 + 9750 = 84750 ≠ 111250 —— 样本本身不勾稽，应报错而非静默通过
    assert "arithmetic_mismatch" in r["flags"]
    assert r["needs_review"] is True


def test_invoice_arithmetic_pass():
    """勾稽正确时应通过且不标复核。"""
    lines = [dict(l) for l in _invoice_lines()]
    for l in lines:
        if l["text"] == "¥75000.00":
            l["text"] = "¥100000.00"
        elif l["text"] == "75000.00":
            l["text"] = "100000.00"
        elif l["text"] == "¥9750.00":
            l["text"] = "¥11250.00"
        elif l["text"] == "9750.00":
            l["text"] = "11250.00"
    r = extract_invoice.extract(lines)
    assert r["fields"]["amount_ex_tax"]["value"] == 100000.00
    assert r["fields"]["tax_amount"]["value"] == 11250.00
    assert r["fields"]["total_amount"]["value"] == 111250.00
    assert "arithmetic_mismatch" not in r["flags"], r["flags"]


def test_invoice_missing_fields():
    r = extract_invoice.extract(_lines(["随便一些文字"]))
    assert r["grade"] == "D"
    assert any(x.startswith("missing:") for x in r["flags"])


# ---------------------------------------------------------------- 合同抽取

def _contract_lines():
    texts = [
        "设备采购合同",
        "合同编号：HT-2026-1008",
        "甲方（买方）：上海示例制造有限公司",
        "住所：上海市浦东新区示例路100号",
        "法定代表人：赵六",
        "乙方（卖方）：北京示例供应链有限公司",
        "住所：北京市海淀区示例大厦18层",
        "法定代表人：钱七",
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
        "第六条 质量保证",
        "质保期为24个月。",
        "第七条 争议解决",
        "提交上海仲裁委员会仲裁。",
        "甲方（盖章）：            乙方（盖章）：",
        "签订日期：2026年10月18日",
    ]
    return _lines(texts, step=36)


def test_contract_extract():
    r = extract_contract.extract(_contract_lines())
    kt = r["key_terms"]
    assert r["meta"]["title"] == "设备采购合同"
    assert r["meta"]["contract_no"] == "HT-2026-1008"
    assert r["meta"]["sign_date"] == "2026-10-18"
    # 总价必须取「合同总价」后的金额，不能取不含税额 100000
    assert kt["contract_amount"] == 111250.00
    assert kt["amount_cn_agrees"] is True
    assert kt["amount_is_estimate"] is True          # 原文有「暂定价」
    assert kt["payment"]["ratios"] == [10.0, 30.0, 60.0]   # 不含违约金 5%
    assert kt["warranty"]["value"] == 24
    assert kt["breach"]["dispute"] == "仲裁"


def test_contract_clause_split():
    r = extract_contract.extract(_contract_lines())
    nos = [c["no"] for c in r["clauses"]]
    assert nos == ["第一条", "第二条", "第三条", "第四条", "第五条", "第六条", "第七条"], nos
    # 「1、2、3、」应作为第四条子项，不另立条款
    fourth = next(c for c in r["clauses"] if c["no"] == "第四条")
    assert len(fourth.get("sub_items", [])) == 3


def test_contract_parties():
    r = extract_contract.extract(_contract_lines())
    names = [p["name"] for p in r["parties"]]
    assert "上海示例制造有限公司" in names
    assert "北京示例供应链有限公司" in names


def test_contract_amount_not_percent():
    """「合同总价的30%」不能被当成金额 3 或 30。"""
    r = extract_contract.extract(_contract_lines())
    vals = [c["value"] for c in r["key_terms"]["amount_candidates"]]
    assert 3.0 not in vals
    assert 30.0 not in vals
    assert 5.0 not in vals


# ---------------------------------------------------------------- 重复页

def test_duplicate_pages():
    import run_ocr as R
    lines = []
    for pg in (1, 2, 3):
        for i, t in enumerate(["设备采购合同", "第一条 标的物", "正文内容甲乙丙丁",
                               "第二条 价款", "金额一百万元", "第三条 期限"]):
            lines.append({"text": t, "score": 0.99, "page": pg,
                          "bbox": [0, i * 30, 600, i * 30 + 20]})
    dups = R._detect_duplicate_pages(lines)
    assert dups == {2, 3}, dups


# ---------------------------------------------------------------- runner

def _run_all() -> int:
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {len(fns)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
