# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 标准化引擎 (Stage 2 / Deterministic Core)
================================================================
职责（Stage 2 数据标准化）：
  1) 通用文本清洗：全角转半角、去空白、去标点
  2) 企业名称标准化：组织形式归一、字号提取、行政区划前缀剥离
  3) 地址标准化：省 / 市 / 区县 / 详址分层解析 + 同义词转换 + 数字归一
  4) 统一社会信用代码（GB 32100-2015）校验位算法校验
  5) 相似度计算：字符串序列比 + 字符二元组 Jaccard + 行政区划层级得分

设计原则：
  - 全部为确定性算法，不依赖外部 API，可在无网环境下复现
  - 不做任何"假设一致"的推断；信息不足时返回可解释的中间态
  - 所有函数返回结构化 dict，便于上层保留判断依据
"""
import re
from difflib import SequenceMatcher

# ============================================================================
# 一、通用文本清洗
# ============================================================================

_PUNCT_RE = re.compile(
    r"[\s\u3000\u00a0·\-—_/.\\,，。;；:：'\"“”‘’()（）\[\]【】<>《》|+*&#@!！?？~￥$%^&、]"
)


def to_halfwidth(s) -> str:
    """全角字符转半角（含全角空格）。"""
    if s is None:
        return ""
    s = str(s)
    out = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:
            code = 0x20
        elif 0xFF01 <= code <= 0xFF5E:
            code -= 0xFEE0
        out.append(chr(code))
    return "".join(out)


def clean_text(s) -> str:
    """去空白、去标点、转半角，得到可与原始文本分离的"紧凑串"。"""
    s = to_halfwidth(s)
    s = _PUNCT_RE.sub("", s)
    return s.strip()


def is_blank(s) -> bool:
    """判断字段是否实质为空（含 None、NaN、空白、常见占位符）。"""
    if s is None:
        return True
    t = to_halfwidth(s).strip()
    if t == "" or t.lower() in ("nan", "none", "null", "无", "-", "—", "n/a", "/"):
        return True
    return False


# ============================================================================
# 二、企业名称标准化
# ============================================================================

# 组织形式词（按长度倒序移除，避免"有限责任公司"被"公司"先截断）
ORG_TOKENS = [
    "有限责任公司", "股份有限公司", "集团有限公司", "有限合伙企业",
    "合伙企业", "有限公司", "分公司", "子公司", "控股", "集团",
    "有限责任", "有限", "责任", "股份", "个体", "工商户",
    "公司", "厂", "中心", "研究院", "研究所", "事务所",
    "商行", "经营部", "门市部", "商店", "超市", "酒店", "宾馆",
]

PROVINCE_LONG = [
    "内蒙古自治区", "广西壮族自治区", "西藏自治区", "宁夏回族自治区",
    "新疆维吾尔自治区", "香港特别行政区", "澳门特别行政区",
    "北京市", "天津市", "上海市", "重庆市",
    "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省", "江苏省",
    "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省",
    "湖北省", "湖南省", "广东省", "海南省", "四川省", "贵州省",
    "云南省", "陕西省", "甘肃省", "青海省", "台湾省",
]

PROVINCE_SHORT = [
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
    "北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林",
    "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
    "甘肃", "青海", "台湾",
]

_ADMIN_PREFIX_RE = re.compile(
    r"^(?:.{2,8}?(?:省|自治区|特别行政区|市|区|县|旗)){1,3}"
)


def _strip_admin_prefix(core: str) -> str:
    """剥离名称开头的行政区划前缀（如"长沙市"/"湖南"），用于简称比对。"""
    if not core:
        return core
    s = core
    for p in sorted(PROVINCE_SHORT, key=len, reverse=True):
        if s.startswith(p):
            s = s[len(p):]
            break
    s2 = _ADMIN_PREFIX_RE.sub("", s)
    return s2 or s


def normalize_entity_name(name) -> dict:
    """
    返回 {
      raw       原始值
      full      清洗后完整串（仅去空白标点 + 全半角归一）
      full_unified  进一步把"有限责任公司"归一为"有限公司"
      core      去掉组织形式词后的字号
      core_na   字号再剥离行政区划前缀（简称比对用）
      blank     是否为空
    }
    """
    if is_blank(name):
        return {"raw": "", "full": "", "full_unified": "", "core": "",
                "core_na": "", "blank": True}

    full = clean_text(name)
    full_unified = full.replace("有限责任公司", "有限公司").replace("股份有限公司", "有限公司")
    core = full
    for t in sorted(ORG_TOKENS, key=len, reverse=True):
        core = core.replace(t, "")
    core = core.strip() or full
    core_na = _strip_admin_prefix(core)
    return {
        "raw": str(name).strip(),
        "full": full,
        "full_unified": full_unified,
        "core": core,
        "core_na": core_na,
        "blank": False,
    }


def entity_similarity(a, b):
    """
    企业名称相似度（0~1）。返回 (score, reason)
    匹配优先级：完整归一一致 > 字号一致 > 字号互含 > 字符相似
    """
    na, nb = normalize_entity_name(a), normalize_entity_name(b)
    if na["blank"] or nb["blank"]:
        return 0.0, "名称为空，无法比对"

    if na["full"] == nb["full"]:
        return 1.00, "名称完全一致"
    if na["full_unified"] == nb["full_unified"]:
        return 0.99, "组织形式表述差异（有限公司/有限责任公司），实质一致"

    ca, cb = na["core_na"], nb["core_na"]
    if ca and ca == cb:
        return 0.97, "字号一致（行政区划前缀/组织形式表述差异）"
    if ca and cb and (ca in cb or cb in ca):
        return 0.90, "字号互为包含（疑似简称或名称不完整）"

    ratio = SequenceMatcher(None, na["full"], nb["full"]).ratio()
    if ca and cb:
        ratio = max(ratio, SequenceMatcher(None, ca, cb).ratio() * 0.95)
    if ratio >= 0.75:
        return round(ratio, 4), "名称高度相似但存在用字差异，需人工确认"
    return round(ratio, 4), "名称存在实质性差异"


# ============================================================================
# 三、地址标准化
# ============================================================================

# 地址同义词 / 简称归一（长词优先）
ADDR_SYNONYMS = [
    ("高新技术产业开发区", "高新区"),
    ("经济技术开发区", "开发区"),
    ("经济开发区", "开发区"),
    ("工业园区", "工业区"),
    ("科技园区", "科技园"),
    ("第一大道", "1大道"),
    ("街道办", "街道"),
    ("居民委员会", "居委会"),
    ("中国", ""),  # 国名前缀无信息量
]

_CN_NUM = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5",
           "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}

# 中文数字 + 单位 → 阿拉伯数字（保守：仅作用于 号/栋/楼/室/层/单元/区 语境）
_CN_NUM_UNIT_RE = re.compile(
    r"([一二两三四五六七八九十])(?=(号楼|栋|幢|座|室|层|楼|单元|号|弄|区))"
)

# 省 / 市 / 区县 抽取
_RE_PROVINCE = re.compile(r"^(.{2,8}?(?:省|自治区|特别行政区))")
_RE_CITY = re.compile(r"^(.{2,8}?(?:市|自治州|地区|盟))")
_RE_DISTRICT = re.compile(r"^(.{2,10}?(?:新区|区|县|旗|市))")

# 详址元素
_RE_ROAD = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{0,16}?(?:大道|大街|大路|路|街|道|巷|弄|里|村|镇|乡|屯|工业区|开发区|科技园))")
_RE_DOOR = re.compile(r"(\d+(?:-\d+)?号)")
_RE_BUILDING = re.compile(r"(\d+号楼|\d+栋|\d+幢|\d+座|[A-Za-z]座|\d+期)")
_RE_ROOM = re.compile(r"(\d+室|\d+层|\d+F|\d+单元|\d+楼)")


def normalize_address_text(addr) -> str:
    """地址文本归一：半角化 → 同义词替换 → 中文数字归一 → 去标点空白。"""
    s = to_halfwidth(addr)
    for k, v in ADDR_SYNONYMS:
        s = s.replace(k, v)
    s = _CN_NUM_UNIT_RE.sub(lambda m: _CN_NUM.get(m.group(1), m.group(1)), s)
    s = _PUNCT_RE.sub("", s)
    return s.strip()


def parse_address(addr) -> dict:
    """
    分层解析地址。返回：
      {province, city, district, detail,
       road, door, building, room, has_room, parseable, reason}
    """
    res = {"province": "", "city": "", "district": "", "detail": "",
           "road": "", "door": "", "building": "", "room": "",
           "has_room": False, "parseable": False, "reason": ""}

    if is_blank(addr):
        res["reason"] = "地址为空"
        return res

    s = normalize_address_text(addr)
    if len(s) < 4:
        res["reason"] = "地址过短，无法解析"
        return res

    rest = s
    # 省级
    m = _RE_PROVINCE.match(rest)
    if m:
        res["province"] = m.group(1)
        rest = rest[m.end():]
    else:
        for p in sorted(PROVINCE_LONG + PROVINCE_SHORT, key=len, reverse=True):
            if rest.startswith(p):
                res["province"] = p
                rest = rest[len(p):]
                break

    # 市级（优先匹配"自治州/地区/盟"；直辖市/县级市由后续区县规则兜底）
    m = _RE_CITY.match(rest)
    if m:
        res["city"] = m.group(1)
        rest = rest[m.end():]

    # 区县级
    m = _RE_DISTRICT.match(rest)
    if m:
        res["district"] = m.group(1)
        rest = rest[m.end():]

    detail = rest
    res["detail"] = detail

    m = _RE_ROAD.search(detail)
    if m:
        res["road"] = m.group(1)
    m = _RE_DOOR.search(detail)
    if m:
        res["door"] = m.group(1)
    m = _RE_BUILDING.search(detail)
    if m:
        res["building"] = m.group(1)
    m = _RE_ROOM.search(detail)
    if m:
        res["room"] = m.group(1)
        res["has_room"] = True

    if res["province"] or res["city"] or res["district"] or res["road"] or res["door"]:
        res["parseable"] = True
    else:
        res["reason"] = "未识别到省市区或道路门牌等有效地址元素"
    return res


def _addr_tokens(s: str) -> set:
    """把地址切成可比对的最小单元：数字+单位 token + 中文二元组。"""
    toks = set()
    s = normalize_address_text(s)
    for m in re.finditer(r"\d+(?:号楼|栋|幢|座|室|层|楼|单元|号|弄|区|路|街|道)", s):
        toks.add(m.group())
    cn = re.sub(r"[0-9A-Za-z]+", " ", s)
    for part in cn.split(" "):
        part = part.strip()
        for i in range(len(part) - 1):
            toks.add(part[i:i + 2])
    return toks


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _hier_score(ca: dict, cb: dict):
    """行政区划层级得分 + 首个冲突层级。"""
    levels = ["province", "city", "district"]
    matched = present = 0
    conflict_level = None
    for lv in levels:
        a, b = ca[lv], cb[lv]
        if a and b:
            present += 1
            if a == b or a.startswith(b) or b.startswith(a):
                matched += 1
            elif conflict_level is None:
                conflict_level = lv
    score = (matched / present) if present else 0.5
    return score, conflict_level


def address_similarity(a, b):
    """
    地址相似度（0~100）。返回 dict：
      {score, status, seq, jaccard, hier, conflict_level,
       ca, cb, diff_reasons}
    其中 status ∈ {一致, 基本一致, 部分一致, 不一致, 无法比对}
    """
    ca, cb = parse_address(a), parse_address(b)
    out = {"ca": ca, "cb": cb, "conflict_level": None,
           "seq": 0.0, "jaccard": 0.0, "hier": 0.0, "diff_reasons": []}

    if is_blank(a) or is_blank(b):
        out.update(score=None, status="无法比对")
        out["diff_reasons"].append(
            "函证地址为空" if is_blank(a) else "注册地址为空（未提供可比对基准）")
        return out

    if not ca["parseable"]:
        out["diff_reasons"].append("函证地址无法解析出有效地址元素")
    if not cb["parseable"]:
        out["diff_reasons"].append("注册地址无法解析出有效地址元素")

    sa, sb = normalize_address_text(a), normalize_address_text(b)
    seq = SequenceMatcher(None, sa, sb).ratio()
    jac = _jaccard(_addr_tokens(a), _addr_tokens(b))
    hier, conflict = _hier_score(ca, cb)

    score = 100.0 * (0.45 * seq + 0.30 * jac + 0.25 * hier)

    # 行政区划冲突 → 上限约束（不允许因详址巧合而误判一致）
    caps = {"province": 35.0, "city": 55.0, "district": 75.0}
    if conflict:
        score = min(score, caps[conflict])
        lv_cn = {"province": "省级", "city": "市级", "district": "区县级"}[conflict]
        out["diff_reasons"].append("%s行政区划不一致（%s ≠ %s）" % (
            lv_cn, ca[conflict] or "空", cb[conflict] or "空"))
    out["conflict_level"] = conflict

    if score >= 95 and not conflict:
        status = "一致"
    elif score >= 80:
        status = "基本一致"
    elif score >= 60:
        status = "部分一致"
    else:
        status = "不一致"

    # 补充差异描述
    if ca["has_room"] != cb["has_room"]:
        out["diff_reasons"].append(
            "楼层/房号信息缺失（%s有、%s无）" % ("函证地址" if ca["has_room"] else "注册地址",
                                          "函证地址" if not ca["has_room"] else "注册地址"))
    for lv, cn in (("road", "道路"), ("door", "门牌号")):
        if ca[lv] and cb[lv] and ca[lv] != cb[lv]:
            out["diff_reasons"].append("%s表述不一致（%s ≠ %s）" % (cn, ca[lv], cb[lv]))

    out.update(score=round(score, 1), status=status,
               seq=round(seq, 4), jaccard=round(jac, 4), hier=round(hier, 4))
    return out


# ---------------------------------------------------------------------------
# 三·补充：逐项差异明细（供底稿"信息对照 + 逐项差异说明"使用）
# ---------------------------------------------------------------------------

_DIFF_ITEMS = [
    ("company", "公司名称"),
    ("province", "省份/直辖市"),
    ("city", "地级市/自治州"),
    ("district", "区/县"),
    ("road", "道路/街道"),
    ("door", "门牌号"),
    ("building", "楼栋"),
    ("room", "房间/楼层"),
]


def element_diff(entity_name, registered_name, confirm_address, registered_address):
    """
    逐项比对"被审计单位提供的询证信息"与"工商登记信息"。
    返回 list[dict]：{key, item, supplied, registered, same, note}

    same 取值：
      True  一致
      False 存在差异
      None  一方缺失，无法比对（不确定）
    """
    na, nb = normalize_entity_name(entity_name), normalize_entity_name(registered_name)
    pa, pb = parse_address(confirm_address), parse_address(registered_address)

    rows = []
    # ① 公司名称
    if na["blank"] or nb["blank"]:
        rows.append({"key": "company", "item": "公司名称",
                     "supplied": str(entity_name or "").strip(),
                     "registered": str(registered_name or "").strip(),
                     "same": None, "note": "一方缺失，名称一致性未执行（不确定）"})
    else:
        sim, reason = entity_similarity(entity_name, registered_name)
        rows.append({"key": "company", "item": "公司名称",
                     "supplied": na["raw"], "registered": nb["raw"],
                     "same": sim >= 0.95, "note": reason})

    # ② 地址各层级
    for key, label in _DIFF_ITEMS[1:]:
        va, vb = pa.get(key, ""), pb.get(key, "")
        if not va and not vb:
            continue
        if not va or not vb:
            rows.append({"key": key, "item": label, "supplied": va, "registered": vb,
                         "same": None,
                         "note": "一方缺失（%s），该项无法比对（不确定）"
                                 % ("被审计单位提供信息缺失" if not va else "工商登记信息缺失")})
            continue
        eq = va == vb or va.startswith(vb) or vb.startswith(va)
        rows.append({"key": key, "item": label, "supplied": va, "registered": vb,
                     "same": eq, "note": "一致" if eq else "表述不一致"})

    # ③ 行政区划层级的"表述省略"软化：
    #    省/市/区县属可省略的层级（如"长沙市岳麓区…"省略"湖南省"），
    #    当双方无任何实质冲突（无 same=False）且存在已核对一致的行政区划层级时，
    #    将单侧缺失的行政区划层级判为"表述省略、实质一致"，避免产生无意义噪声。
    #    注：道路/门牌号/楼栋/房间楼层不适用软化——缺失将直接影响投递，仍标"无法比对"。
    admin_keys = {"province", "city", "district"}
    has_conflict = any(r["same"] is False for r in rows)
    has_anchor = any(r["same"] is True and r["key"] in admin_keys for r in rows)
    if has_anchor and not has_conflict:
        for r in rows:
            if r["same"] is None and r["key"] in admin_keys:
                r["same"] = True
                r["note"] = "一方未表述该层级（地址简写），实质一致"
    return rows


def diff_summary_text(diff_rows):
    """把逐项差异明细压缩为一句话，用于 Excel「异常说明」补充。"""
    bad = [r for r in diff_rows if r["same"] is False]
    unk = [r for r in diff_rows if r["same"] is None]
    parts = []
    if bad:
        parts.append("差异项：" + "、".join(
            "%s（%s ≠ %s）" % (r["item"], r["supplied"] or "空", r["registered"] or "空")
            for r in bad))
    if unk:
        parts.append("待确认项：" + "、".join(r["item"] for r in unk))
    if not parts:
        return "逐项比对无差异"
    return "；".join(parts)


# ============================================================================
# 四、统一社会信用代码校验（GB 32100-2015）
# ============================================================================
USCC_CHARS = "0123456789ABCDEFGHJKLMNPQRTUWXY"  # 31 位字符集（排除 I O S V Z）
USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]


def uscc_check(code):
    """返回 (是否通过, 说明)。校验位按 GB 32100-2015 计算。"""
    if is_blank(code):
        return None, "统一社会信用代码为空（不确定）"
    c = clean_text(code).upper()
    if len(c) != 18:
        return False, "长度非 18 位（实际 %d 位）" % len(c)
    bad = [ch for ch in c if ch not in USCC_CHARS]
    if bad:
        return False, "含非法字符 %s（不应出现 I/O/S/V/Z）" % "".join(sorted(set(bad)))
    total = sum(USCC_CHARS.index(c[i]) * USCC_WEIGHTS[i] for i in range(17))
    r = 31 - (total % 31)
    r = 0 if r == 31 else r
    expect = USCC_CHARS[r]
    if expect == c[17]:
        return True, "校验位正确"
    return False, "校验位错误（第 18 位应为 %s，实际 %s）" % (expect, c[17])


# ============================================================================
# 五、电话 / 行政区号辅助校验
# ============================================================================

CITY_AREA_CODE = {
    "北京": "010", "上海": "021", "天津": "022", "重庆": "023",
    "长沙": "0731", "株洲": "0731", "湘潭": "0731",
    "广州": "020", "深圳": "0755", "武汉": "027", "成都": "028",
    "杭州": "0571", "南京": "025", "西安": "029", "郑州": "0371",
    "济南": "0531", "青岛": "0532", "合肥": "0551", "福州": "0591",
    "厦门": "0592", "南昌": "0791", "昆明": "0871", "贵阳": "0851",
    "沈阳": "024", "大连": "0411", "哈尔滨": "0451", "长春": "0431",
    "石家庄": "0311", "太原": "0351", "南宁": "0771", "海口": "0898",
    "兰州": "0931", "银川": "0951", "西宁": "0971", "乌鲁木齐": "0991",
    "呼和浩特": "0471", "拉萨": "0891", "苏州": "0512", "无锡": "0510",
    "宁波": "0574", "温州": "0577", "东莞": "0769", "佛山": "0757",
}

_BANK_KEYWORDS = ["银行", "信用社", "农商", "农村商业", "邮政储蓄", "支行", "分行", "营业部",
                  "credit", "bank", "financial", "财务有限公司"]


def phone_area_consistency(phone, addr_parsed: dict):
    """
    电话区号与地址所在城市一致性。返回 (status, reason)
    status ∈ {一致, 不一致, 无法比对}
    区号位数规则：010~029（直辖市及大区中心）为 3 位；其余为 0xxx 共 4 位。
    避免对 "02038889999" 之类无分隔符号码的贪婪误取。
    """
    if is_blank(phone):
        return "无法比对", "联系电话为空"
    p = clean_text(phone)
    m = re.match(r"^0", p)
    if not m:
        if p.startswith("1") and len(p) >= 11:
            return "无法比对", "手机号码，无区号可比对"
        return "无法比对", "未识别到区号"
    if re.match(r"^0(1|2)\d", p):
        code = p[:3]
    else:
        code = p[:4] if len(p) >= 4 else p
    city = addr_parsed.get("city", "") or addr_parsed.get("province", "")
    if not city:
        return "无法比对", "地址未识别到城市，无法比对区号"
    for name, expected in CITY_AREA_CODE.items():
        if name in city:
            if code == expected:
                return "一致", "区号 %s 与地址城市 %s 匹配" % (code, name)
            return "不一致", "区号 %s 与地址城市 %s 应使用 %s" % (code, name, expected)
    return "无法比对", "地址城市未纳入区号基准库"


def is_bank_like(name: str) -> bool:
    n = (name or "").lower()
    return any(k.lower() in n for k in _BANK_KEYWORDS)
