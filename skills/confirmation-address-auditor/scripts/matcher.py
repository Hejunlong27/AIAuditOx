# -*- coding: utf-8 -*-
"""
函证地址智能核对助手 —— 三级匹配引擎 (Stage 3)
================================================
一级匹配 (L1)：标准化后字符串精确匹配
二级匹配 (L2)：语义相似度匹配（序列比 + 二元组 Jaccard + 行政区划层级）
三级匹配 (L3)：企业信息合理性判断（名称一致性 / 信用代码校验 / 电话区号一致性
              / 函证类型与地址性质 / 一址多照聚簇）

输出：匹配状态、匹配度（0~100）、差异原因（保留全部依据）
"""
from collections import defaultdict

from normalizer import (
    address_similarity, entity_similarity, normalize_address_text,
    parse_address, uscc_check, phone_area_consistency, is_bank_like, is_blank,
    clean_text, element_diff, diff_summary_text,
)

VALID_STATUS = ("一致", "基本一致", "部分一致", "不一致", "无法比对")


def _addr_cluster_key(addr) -> str:
    """地址聚簇键：省+市+区县+道路+门牌+楼栋，缺失时退回全文归一。"""
    p = parse_address(addr)
    key = "".join([p["province"], p["city"], p["district"], p["road"],
                   p["door"], p["building"]])
    if len(key) < 4:
        key = normalize_address_text(addr)
    return key


def run_matching(records):
    """
    records: List[dict] 每条含 entity_name / uscc / confirm_address /
             registered_address / phone / contact / confirm_type
    返回 List[dict] 匹配结果（含全部判断依据）
    """
    n = len(records)

    # ---- L3 前置：构建地址聚簇（识别人为"一址多照"） ----
    bucket = defaultdict(list)
    for i, r in enumerate(records):
        k = _addr_cluster_key(r.get("registered_address"))
        if k and len(k) >= 4:
            bucket[k].append(i)
        k2 = _addr_cluster_key(r.get("confirm_address"))
        if k2 and len(k2) >= 4 and k2 != k:
            bucket[k2].append(i)

    cluster_flag = {}
    for k, idxs in bucket.items():
        uniq = set()
        for i in idxs:
            u = clean_text(records[i].get("uscc")) or records[i].get("entity_name")
            uniq.add(u)
        if len(uniq) >= 3:
            for i in idxs:
                cluster_flag[i] = (len(uniq), k)

    results = []
    for i, r in enumerate(records):
        ev = []
        # L3-① 名称一致性：仅当提供"工商登记名称"时执行，否则标记"不确定"，不做假设
        reg_name = r.get("registered_name")
        if is_blank(reg_name):
            name_sim, name_reason = None, "未提供工商登记名称，名称一致性未执行（不确定）"
        else:
            name_sim, name_reason = entity_similarity(r.get("entity_name"), reg_name)
        ev.append("【名称校验】%s%s" % (
            name_reason, "" if name_sim is None else "（相似度 %.2f）" % name_sim))

        addr = address_similarity(r.get("confirm_address"),
                                  r.get("registered_address"))
        l1_hit = addr.get("status") in ("一致", "基本一致") and addr.get("seq", 0) == 1.0
        ev.append("【地址匹配】一级字符串精确匹配：%s" % ("命中" if l1_hit else "未命中"))
        ev.append("【地址匹配】二级语义匹配：匹配度 %.1f（序列比 %.4f / 二元组 %.4f / 层级 %.4f）"
                  % (addr.get("score") or 0.0, addr.get("seq", 0),
                     addr.get("jaccard", 0), addr.get("hier", 0)))
        for d in addr.get("diff_reasons", []):
            ev.append("【差异】%s" % d)

        uscc_ok, uscc_reason = uscc_check(r.get("uscc"))
        ev.append("【信用代码校验】%s" % uscc_reason)

        # 电话校验：优先与函证地址城市比对，函证地址缺失时回退注册地址城市
        ca = addr.get("ca", {}) or {}
        cb = addr.get("cb", {}) or {}
        phone_ref = ca if (ca.get("city") or ca.get("province")) else cb
        phone_ref_src = "函证地址" if phone_ref is ca else "注册地址"
        phone_status, phone_reason = phone_area_consistency(
            r.get("phone"), phone_ref)
        if phone_ref_src == "注册地址" and phone_status != "无法比对":
            phone_reason += "（函证地址未识别到城市，以注册地址城市比对）"
        ev.append("【电话区号校验】%s" % phone_reason)

        ctype = (r.get("confirm_type") or "").strip()
        bank_like = is_bank_like(r.get("entity_name"))
        type_note = ""
        if ctype:
            if ("银行" in ctype and not bank_like):
                type_note = "函证类型标注为银行函证，但被函证单位名称未体现金融机构特征，需复核"
            elif ("客户" in ctype or "供应商" in ctype) and bank_like:
                type_note = "函证类型标注为客户/供应商，但被函证单位名称呈金融机构特征，需复核"
        if type_note:
            ev.append("【函证类型校验】%s" % type_note)

        cf = cluster_flag.get(i)
        if cf:
            ev.append("【一址多照】该地址在本次数据集内对应 %d 个不同主体，存在地址聚簇异常" % cf[0])

        # 投递点颗粒度：函证地址可解析但缺少门牌号 → 无法确定具体投递点
        missing_door = bool(ca.get("parseable")) and not ca.get("door")
        if missing_door:
            ev.append("【投递点】函证地址未包含门牌号，投递点不明确")

        # 逐项差异明细（底稿"信息对照 + 逐项差异说明"用）
        diff_rows = element_diff(r.get("entity_name"), r.get("registered_name"),
                                 r.get("confirm_address"), r.get("registered_address"))
        diff_text = diff_summary_text(diff_rows)
        ev.append("【逐项差异】%s" % diff_text)

        results.append({
            "index": i + 1,
            "entity_name": r.get("entity_name", ""),
            "uscc": r.get("uscc", ""),
            "confirm_address": r.get("confirm_address", ""),
            "registered_address": r.get("registered_address", ""),
            "phone": r.get("phone", ""),
            "contact": r.get("contact", ""),
            "confirm_type": r.get("confirm_type", ""),

            "name_sim": round(name_sim, 4) if name_sim is not None else None,
            "name_reason": name_reason,

            "addr_score": addr.get("score"),
            "addr_status": addr.get("status"),
            "addr_seq": addr.get("seq", 0),
            "addr_jaccard": addr.get("jaccard", 0),
            "addr_hier": addr.get("hier", 0),
            "addr_conflict": addr.get("conflict_level"),
            "addr_diff": addr.get("diff_reasons", []),
            "confirm_parsed": addr.get("ca", {}),
            "reg_parsed": addr.get("cb", {}),

            "uscc_ok": uscc_ok,
            "uscc_reason": uscc_reason,
            "phone_status": phone_status,
            "phone_reason": phone_reason,
            "type_note": type_note,
            "cluster": cf[0] if cf else 0,
            "missing_door": missing_door,

            "registered_name": r.get("registered_name", ""),
            "reg_source": r.get("reg_source", ""),
            "reg_source_url": r.get("reg_source_url", ""),
            "query_date": r.get("query_date", ""),
            "screenshot": r.get("screenshot", ""),
            "diff_rows": diff_rows,
            "diff_text": diff_text,

            "evidence": ev,
        })
    return results
