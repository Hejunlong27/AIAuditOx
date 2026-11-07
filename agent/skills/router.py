"""技能路由（PART 7.4）。

三级策略：关键词/索引匹配 → 别名与科目号匹配 → 交人工确认。

**绝不强行选一个错技能**。当最高分不唯一、或分数低于阈值时，
返回 :class:`RouteDecision` 并把候选交回给调用方要求确认——
路由错的代价是整份底稿错科目，比让用户多点一次贵得多。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.models.enums import ConflictSeverity
from agent.skills.registry import SkillEntry, SkillRegistry

# 科目号 → 技能 ID 的弱映射（来自各包 SKILL.md 的「对应所内科目编号」）
SUBJECT_CODE_MAP: dict[str, tuple[str, ...]] = {
    "1001": ("z-1-1-cash-on-hand",),
    "1002": ("z-1-2-bank-deposits",),
    "1012": ("z-1-3-other-monetary-funds",),
    "1121": ("z-2-1-notes-receivable",),
    "1122": ("z-2-accounts-receivable",),
    "1123": ("z-3-prepayments",),
    "1221": ("z-4-other-receivables",),
    "1131": ("z-6-dividends-receivable",),
    "1132": ("z-7-interest-receivable",),
    "2001": ("f-1-borrowings",),
    "2201": ("f-3-notes-payable",),
    "2202": ("f-4-accounts-payable",),
    "2211": ("f-6-payroll-payable",),
    "2203": ("f-8-advances-from-customers",),
    "2221": ("f-9-taxes-payable",),
    "2231": ("f-10-interest-payable",),
    "2232": ("f-11-dividends-payable",),
    "2241": ("f-12-other-payables",),
    "2401": ("f-13-deferred-income",),
    "6001": ("s-1-revenue",),
    "6401": ("s-8-taxes-and-surcharges",),
    "6601": ("s-9-selling-expenses",),
    "6602": ("s-10-admin-expenses",),
    "6603": ("s-11-financial-expenses",),
    "6604": ("s-14-credit-impairment",),
}

# 常用口语别名 → 技能 ID（用户不会说"货币资金·银行存款"）
ALIAS_MAP: dict[str, str] = {
    "银行": "z-1-2-bank-deposits",
    "银行存款": "z-1-2-bank-deposits",
    "银行账户": "z-1-2-bank-deposits",
    "货币资金": "z-1-2-bank-deposits",
    "余额调节表": "z-1-2-bank-deposits",
    "函证": "z-1-2-bank-deposits",
    "库存现金": "z-1-1-cash-on-hand",
    "现金": "z-1-1-cash-on-hand",
    "其他货币资金": "z-1-3-other-monetary-funds",
    "应收账款": "z-2-accounts-receivable",
    "应收票据": "z-2-1-notes-receivable",
    "预付": "z-3-prepayments",
    "其他应收": "z-4-other-receivables",
    "短期借款": "f-1-borrowings",
    "应付账款": "f-4-accounts-payable",
    "应付票据": "f-3-notes-payable",
    "应付职工薪酬": "f-6-payroll-payable",
    "工资": "f-6-payroll-payable",
    "应交税费": "f-9-taxes-payable",
    "预收": "f-8-advances-from-customers",
    "收入": "s-1-revenue",
    "营业收入": "s-1-revenue",
    "销售费用": "s-9-selling-expenses",
    "管理费用": "s-10-admin-expenses",
    "财务费用": "s-11-financial-expenses",
    "信用减值": "s-14-credit-impairment",
}

# 低于此分视为"没把握"，必须问人
MIN_CONFIDENT_SCORE = 30
# 最高分与次高分差距小于此值视为"打平"，必须问人
TIE_MARGIN = 10


@dataclass
class RouteCandidate:
    skill_id: str
    name: str
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class RouteDecision:
    """路由结果。"""

    skill_id: str | None
    confidence: float
    candidates: list[RouteCandidate]
    needs_confirmation: bool
    reason: str
    severity: ConflictSeverity = ConflictSeverity.INFO

    @property
    def decided(self) -> bool:
        return self.skill_id is not None and not self.needs_confirmation


class SkillRouter:
    """把一句自然语言需求路由到技能包。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def search_candidates(self, user_request: str, *, limit: int = 5) -> list[RouteCandidate]:
        text = (user_request or "").strip()
        if not text:
            return []
        scores: dict[str, int] = {}
        reasons: dict[str, list[str]] = {}

        def bump(sid: str, points: int, why: str) -> None:
            scores[sid] = scores.get(sid, 0) + points
            reasons.setdefault(sid, []).append(why)

        # 1) 科目号直击（最强信号）
        for code in re.findall(r"\b(\d{4})\b", text):
            for sid in SUBJECT_CODE_MAP.get(code, ()):
                bump(sid, 60, f"命中科目号 {code}")

        # 2) 别名（长的优先，避免"现金"抢先于"库存现金"）
        for alias in sorted(ALIAS_MAP, key=len, reverse=True):
            if alias in text:
                bump(ALIAS_MAP[alias], 45, f"别名「{alias}」")

        # 3) 注册表全文检索
        for entry in self.registry.search(text, limit=limit * 4):
            base = _entry_score(entry, text)
            if base > 0:
                bump(entry.id, base, "索引检索命中")

        out: list[RouteCandidate] = []
        for sid, score in scores.items():
            try:
                entry = self.registry.get(sid)
            except KeyError:
                continue
            # 规范型/工具型不是科目技能，参与路由会误导
            if entry.variant in ("standard",):
                continue
            out.append(
                RouteCandidate(
                    skill_id=sid, name=entry.name, score=score, reasons=reasons.get(sid, [])
                )
            )
        out.sort(key=lambda c: (-c.score, c.skill_id))
        return out[:limit]

    def route(self, user_request: str) -> RouteDecision:
        candidates = self.search_candidates(user_request)
        if not candidates:
            return RouteDecision(
                skill_id=None,
                confidence=0.0,
                candidates=[],
                needs_confirmation=True,
                reason="没有任何技能命中该请求，请补充科目名称或科目号",
                severity=ConflictSeverity.BLOCKING,
            )
        best = candidates[0]
        total = sum(c.score for c in candidates) or 1
        confidence = round(best.score / total, 3)

        if best.score < MIN_CONFIDENT_SCORE:
            return RouteDecision(
                skill_id=None,
                confidence=confidence,
                candidates=candidates,
                needs_confirmation=True,
                reason=f"最高分 {best.score} 低于置信阈值 {MIN_CONFIDENT_SCORE}，不足以自动选定",
                severity=ConflictSeverity.WARNING,
            )
        if len(candidates) > 1 and (best.score - candidates[1].score) < TIE_MARGIN:
            return RouteDecision(
                skill_id=None,
                confidence=confidence,
                candidates=candidates,
                needs_confirmation=True,
                reason=(
                    f"「{best.skill_id}」({best.score}) 与 "
                    f"「{candidates[1].skill_id}」({candidates[1].score}) 分数接近，需人工确认"
                ),
                severity=ConflictSeverity.WARNING,
            )
        return RouteDecision(
            skill_id=best.skill_id,
            confidence=confidence,
            candidates=candidates,
            needs_confirmation=False,
            reason=f"命中「{best.skill_id}」，依据：" + "；".join(best.reasons[:4]),
        )

    def confirm_route(self, skill_id: str, user_request: str = "") -> RouteDecision:
        """人工确认路由结果。校验技能存在且是科目技能组。"""
        entry = self.registry.get(skill_id)
        if entry.variant not in ("skill-group", "orchestrator"):
            raise ValueError(
                f"技能 {skill_id} 形态为 {entry.variant}，不能作为审计任务主技能"
            )
        return RouteDecision(
            skill_id=skill_id,
            confidence=1.0,
            candidates=[RouteCandidate(skill_id=skill_id, name=entry.name, score=100, reasons=["人工确认"])],
            needs_confirmation=False,
            reason="人工确认路由",
        )


def _entry_score(entry: SkillEntry, text: str) -> int:
    low = text.lower()
    score = 0
    if entry.id in low:
        score += 40
    if entry.name and entry.name in text:
        score += 30
    # 描述里出现请求中的 2 字片段才给分，避免长描述无脑命中
    if entry.description:
        hits = sum(1 for i in range(len(low) - 1) if low[i : i + 2] in entry.description)
        if hits >= 3:
            score += 10
    return score
