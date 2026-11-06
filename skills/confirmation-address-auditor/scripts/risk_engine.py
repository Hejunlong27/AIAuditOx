# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 风险识别与审计判断引擎 (Stage 4 / Stage 5)
====================================================================
Stage 4 风险识别：按"高风险 / 中风险 / 低风险"三级输出，每条风险保留规则编号与依据。
Stage 5 审计判断：生成 是否建议发送函证 / 是否需要电话确认 /
                  是否需要获取工商变更资料 / 是否需要扩大审计程序。

风险规则编号：
  高风险 H1 函证地址与注册地址实质不一致（行政区划冲突或匹配度 < 60）
  高风险 H2 函证地址为空或无法解析出有效地址元素（地址不可用/疑似不存在）
  高风险 H3 地址对应多个主体（一址多照 / 地址聚簇异常）
  高风险 H4 企业注册地址频繁变化（需提供变更次数；未提供则列示为"不确定"）
  中风险 M1 地址表述/格式差异（指向同一地但文字不一致）
  中风险 M2 楼层或房号信息缺失（一方有、一方无）
  中风险 M3 名称以简称出现，无法确认主体唯一性（或未提供工商登记名称）
  中风险 M4 统一社会信用代码校验位错误
  中风险 M5 联系电话区号与地址所在城市不一致
  中风险 M6 函证类型与地址（主体性质）不匹配
  中风险 M7 函证地址缺少门牌号（投递点不明确）
  中风险 M8 注册地址缺失，无法执行一致性核验（不确定）
  中风险 M9 未提供工商信息来源（查询平台/网址），工商登记信息缺乏可追溯来源
  中风险 M10 未提供工商信息查询界面截图附件，核对过程缺乏证据留痕
"""
from normalizer import is_blank

RISK_ORDER = {"低风险": 0, "中风险": 1, "高风险": 2}


def assess(rec, reg_change_count=None, evidence=None, require_evidence=True):
    """
    rec: matcher.run_matching 输出的单条结果
    reg_change_count: 可选的工商注册地址变更次数（若数据源提供）
    返回 dict：risk_level / risk_items / explanation / advice / flags
    """
    items = []  # (code, level, desc)

    score = rec.get("addr_score")
    status = rec.get("addr_status")
    conflict = rec.get("addr_conflict")
    diffs = rec.get("addr_diff", [])
    cf = rec.get("cluster", 0)

    # ---------------- 高风险 ----------------
    if score is not None and (conflict or score < 60):
        items.append(("H1", "高风险",
                      "函证地址与注册地址实质不一致（匹配度 %s，%s），存在函证寄送对象错误风险"
                      % (("%.1f" % score) if score is not None else "—",
                         ("%s行政区划冲突" % {"province": "省级", "city": "市级",
                                             "district": "区县级"}.get(conflict, ""))
                         if conflict else "相似度低于阈值")))

    if is_blank(rec.get("confirm_address")):
        items.append(("H2", "高风险", "函证地址为空，无法执行函证寄发程序"))
    else:
        cp = rec.get("confirm_parsed", {})
        if not cp.get("parseable"):
            items.append(("H2", "高风险",
                          "函证地址无法解析出有效地址元素（%s），疑似地址不存在或结构异常"
                          % (cp.get("reason") or "格式异常")))

    if cf and cf >= 3:
        items.append(("H3", "高风险",
                      "该地址在本次数据集内对应 %d 个不同主体，涉嫌一址多照/空壳注册，需评估舞弊风险"
                      % cf))

    if reg_change_count is not None and reg_change_count >= 2:
        items.append(("H4", "高风险",
                      "被函证单位注册地址在报告期内变更 %d 次，地址稳定性存疑，需获取工商变更档案"
                      % reg_change_count))

    # ---------------- 中风险 ----------------
    # M1 仅在存在"实质性差异项"时触发：仅省级/市级前缀省略等地址简写不构成风险
    sub_diff = [d for d in rec.get("diff_rows", []) if d.get("same") is False]
    unk_diff = [d for d in rec.get("diff_rows", []) if d.get("same") is None]
    if status in ("基本一致", "部分一致") and (sub_diff or unk_diff):
        items.append(("M1", "中风险",
                      "函证地址与注册地址指向同一地点但存在逐项差异（匹配度 %.1f）；差异项：%s"
                      % (score if score is not None else 0,
                         "、".join(d["item"] for d in (sub_diff + unk_diff)))))

    if any("楼层" in d or "房号" in d for d in diffs):
        items.append(("M2", "中风险", "楼层/房号信息缺失，具体投递点不明确"))

    if rec.get("name_sim") is None:
        items.append(("M3", "中风险", "未提供工商登记名称，名称一致性未执行，主体唯一性未确认（不确定）"))
    elif rec.get("name_sim") is not None and rec["name_sim"] < 0.95:
        items.append(("M3", "中风险",
                      "被函证单位名称与工商登记名称存在差异（相似度 %.2f），%s"
                      % (rec["name_sim"], rec.get("name_reason", ""))))

    if rec.get("uscc_ok") is False:
        items.append(("M4", "中风险", "统一社会信用代码校验未通过：%s" % rec.get("uscc_reason")))
    elif rec.get("uscc_ok") is None:
        items.append(("M4", "中风险", "统一社会信用代码为空，无法校验主体身份（不确定）"))

    if rec.get("phone_status") == "不一致":
        items.append(("M5", "中风险", "联系电话区号与地址所在城市不一致：%s" % rec.get("phone_reason")))

    if rec.get("type_note"):
        items.append(("M6", "中风险", rec["type_note"]))

    if rec.get("missing_door"):
        items.append(("M7", "中风险", "函证地址缺少门牌号，投递点不明确，存在无法送达或错投风险"))

    if status == "无法比对" and not is_blank(rec.get("confirm_address")):
        items.append(("M8", "中风险",
                      "注册地址缺失，无法执行地址一致性核验，一致性结论未取得（不确定）"))

    # ---------------- 证据留痕（工商信息来源与查询截图） ----------------
    ev = evidence or {}
    if require_evidence and ev:
        if ev.get("缺来源平台") and ev.get("缺来源网址"):
            items.append(("M9", "中风险",
                          "未记录工商信息来源（查询平台及网址），工商登记信息缺乏可追溯来源"))
        elif ev.get("缺来源网址"):
            items.append(("M9", "中风险",
                          "未记录工商信息查询网址，来源可追溯性不足（仅标注来源平台：%s）"
                          % ev.get("工商信息来源", "")))
        if ev.get("缺查询截图"):
            items.append(("M10", "中风险",
                          "未附工商信息查询界面截图，核对过程缺乏证据留痕，不足以作为审计证据留存"))

    # ---------------- 汇总等级 ----------------
    if not items:
        level = "低风险"
    else:
        level = max((i[1] for i in items), key=lambda x: RISK_ORDER[x])

    if items:
        explanation = "；".join("%s[%s] %s" % (c, lv, d) for c, lv, d in items)
    elif status in ("基本一致", "部分一致"):
        explanation = ("函证地址与注册地址指向同一地点，仅存在地址简写等表述差异"
                       "（匹配度 %s），逐一比对未发现实质性差异" % (score if score is not None else "—"))
    else:
        explanation = "函证地址与注册地址一致，各项校验未发现异常"

    # ---------------- Stage 5 审计判断 ----------------
    codes = {c for c, _, _ in items}
    if "H1" in codes or "H2" in codes or "H3" in codes:
        send = "暂缓发送，核实后重新评估"
    elif level == "中风险":
        send = "建议核实后再发送"
    else:
        send = "建议发送"

    need_phone = level != "低风险"
    need_reg_change = ("H1" in codes) or ("H4" in codes) or ("H3" in codes)
    need_extend = ("H1" in codes) or ("H2" in codes) or ("H3" in codes)

    advice_parts = []
    if "H1" in codes:
        advice_parts.append("暂缓寄发，先取得被函证单位最新营业执照或通过国家企业信用信息公示系统核实注册地址；"
                            "如差异系迁址所致，取得工商变更登记资料；并考虑执行替代审计程序（检查合同、"
                            "验收单、结算单据及期后回款）")
    if "H2" in codes:
        advice_parts.append("重新获取有效投递地址后再行寄发；无法获取时改由项目组现场递交或执行替代程序")
    if "H3" in codes:
        advice_parts.append("核查该地址是否为企业注册托管地址，评估是否存在关联方集中代收；"
                            "结合舞弊风险评估扩大函证范围并加强函证过程控制")
    if "H4" in codes:
        advice_parts.append("获取报告期内工商变更登记档案，询问管理层变更原因，评估对交易真实性的影响")
    if "M1" in codes or "M2" in codes:
        advice_parts.append("寄发前通过电话或公开渠道核实门牌/楼层/房号，确保投递地址完整准确")
    if "M7" in codes:
        advice_parts.append("补充门牌号等投递点信息后寄发，必要时改用快递面单地址回执留痕")
    if "M3" in codes:
        advice_parts.append("取得工商登记全称，确认被函证主体唯一性后再寄发")
    if "M4" in codes:
        advice_parts.append("核对统一社会信用代码，防止函证对象串户")
    if "M5" in codes:
        advice_parts.append("核实联系电话归属，防范地址与联系方式被篡改")
    if "M6" in codes:
        advice_parts.append("复核函证类型划分与函证对象性质的匹配性")
    if "M8" in codes:
        advice_parts.append("向被审计单位索取被函证单位的工商登记地址，补充一致性核验后再行寄发")
    if "M9" in codes:
        advice_parts.append("在底稿中补充工商登记信息来源平台与查询网址；官方渠道优先采用国家企业信用信息"
                            "公示系统（www.gsxt.gov.cn），第三方平台（企查查/天眼查）仅作补充并交叉验证")
    if "M10" in codes:
        advice_parts.append("补充工商信息查询界面截图，按索引号归档后作为本核对程序的审计证据留存")
    if not advice_parts:
        advice_parts.append("地址核验正常，按既定函证程序寄发，保留邮寄凭证与回函记录")

    return {
        "risk_level": level,
        "risk_items": items,
        "risk_codes": sorted(codes),
        "explanation": explanation,
        "advice": "；".join(advice_parts),
        "flags": {
            "send_confirm": send,
            "need_phone": need_phone,
            "need_reg_change_doc": need_reg_change,
            "need_extend_procedure": need_extend,
        },
    }


def assess_all(results, reg_change_map=None, evidence_map=None, require_evidence=True):
    """
    批量评估。
      reg_change_map: {uscc 或 名称: 变更次数}
      evidence_map:   {记录序号: {缺来源网址 / 缺查询截图 / 工商信息来源 ...}}
    """
    reg_change_map = reg_change_map or {}
    evidence_map = evidence_map or {}
    out = []
    for r in results:
        key_u = str(r.get("uscc") or "").strip()
        key_n = str(r.get("entity_name") or "").strip()
        cnt = reg_change_map.get(key_u, reg_change_map.get(key_n))
        ev = evidence_map.get(r.get("index"))
        a = assess(r, cnt, ev, require_evidence)
        merged = dict(r)
        merged.update(a)
        out.append(merged)
    return out
