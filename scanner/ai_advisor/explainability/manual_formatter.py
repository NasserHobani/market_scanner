# -*- coding: utf-8 -*-
"""Map AdvisorReview + recommendation to manual analysis display model."""
from __future__ import annotations

from typing import Any


def _overall_decision(agreement: str, side: str, confidence: float) -> str:
    side = (side or "buy").lower()
    agree = (agreement or "").lower()
    conf = float(confidence or 0)
    bullish = side in ("buy", "long")
    if agree in ("agree", "full") and conf >= 75:
        return "Strong Buy" if bullish else "Strong Sell"
    if agree in ("agree", "partial") and conf >= 55:
        return "Buy" if bullish else "Sell"
    if agree == "disagree" or conf < 40:
        return "Avoid"
    return "Watch"


def _expected_scenario(agreement: str, side: str) -> str:
    agree = (agreement or "").lower()
    bullish = (side or "buy").lower() in ("buy", "long")
    if agree in ("agree", "partial"):
        return "Bullish" if bullish else "Bearish"
    if agree == "disagree":
        return "Bearish" if bullish else "Bullish"
    return "Sideways"


def format_manual_analysis(review: dict[str, Any], *,
                           recommendation: dict[str, Any] | None = None,
                           metrics: dict[str, Any] | None = None,
                           review_type: str = "manual") -> dict[str, Any]:
    """Manual analysis display model — Arabic analyst fields when present."""
    reco = recommendation or {}
    side = reco.get("side", "buy")
    agreement = review.get("agreement", "")
    confidence = float(review.get("confidence") or 0)
    supporting = review.get("supporting_evidence") or []
    contradicting = review.get("contradicting_evidence") or []
    risks = review.get("risks") or []
    missing = review.get("missing_information") or []
    experiment = review.get("suggested_experiment") or {}

    try:
        from scanner.ai_advisor.analyst.normalize import extract_analyst_fields
        analyst = extract_analyst_fields(review.get("raw_response") or review)
    except Exception:  # noqa: BLE001
        analyst = {}

    advice = analyst.get("recommendation") or {}
    advisor_action = advice.get("action") or ""
    market_view = analyst.get("current_market_view") or {}
    outlook = analyst.get("near_term_outlook") or {}
    watch = analyst.get("what_to_watch") or []
    invalidate = analyst.get("invalidation_conditions") or [
        r for r in risks[:3]
    ] or [
        "كسر مستوى الدعم/المقاومة الرئيسي",
        "انعكاس الاتجاه على HTF",
        "فشل تأكيد BOS",
    ]

    wait_hint = (
        "الأفضل الانتظار حتى يظهر تأكيد أوضح."
        if (agreement == "disagree" or confidence < 50 or advisor_action in ("wait", "avoid"))
        else "الشروط متوافقة نسبيًا — راجع مناطق الدخول والمخاطر قبل التنفيذ."
    )

    before_entry = missing[:5] or watch[:5] or [
        "تأكيد مشاركة الحجم (RVOL)",
        "التحقق من توافق HTF",
        "انتظار تأكيد هيكلي (BOS/CHOCH)",
    ]

    overall = {
        "buy": "شراء",
        "sell": "بيع",
        "wait": "انتظار",
        "watch": "مراقبة",
        "avoid": "تجنب",
    }.get(advisor_action) or _overall_decision(agreement, side, confidence)

    scenario = {
        "bullish": "صاعد",
        "bearish": "هابط",
        "sideways": "جانبي",
        "unclear": "غير واضح",
    }.get(str(outlook.get("direction") or market_view.get("direction") or ""), "") or _expected_scenario(
        agreement, side
    )

    return {
        "review_id": review.get("review_id", ""),
        "review_type": review_type,
        "overall_decision": overall,
        "advisor_action": advisor_action,
        "confidence": confidence,
        "executive_summary": review.get("summary", ""),
        "current_market_view": market_view,
        "near_term_outlook": outlook,
        "actionable_advice": analyst.get("actionable_advice") or wait_hint,
        "data_quality_note": analyst.get("data_quality_note") or "",
        "detailed_analysis": {
            "trend": _extract_section(review.get("reasoning", ""), "trend"),
            "momentum": _extract_section(review.get("reasoning", ""), "momentum"),
            "structure": _extract_section(review.get("reasoning", ""), "structure"),
            "risk": "; ".join(risks[:3]) if risks else "",
            "strength": "; ".join(
                e.get("note", "") for e in supporting[:3] if isinstance(e, dict)
            ),
            "weakness": "; ".join(
                e.get("note", "") for e in contradicting[:3] if isinstance(e, dict)
            ),
            "full_reasoning": review.get("reasoning", ""),
        },
        "positive_signals": analyst.get("positive_signals") or supporting,
        "negative_signals": analyst.get("negative_signals") or contradicting,
        "important_risks": risks,
        "expected_scenario": scenario,
        "suggested_entry_zone": _zone(reco, "entry"),
        "suggested_stop_zone": _zone(reco, "stop"),
        "suggested_target_zone": _zone(reco, "target"),
        "before_entering": before_entry,
        "invalidation": invalidate,
        "what_to_watch": watch,
        "should_wait": wait_hint,
        "suggested_experiment": experiment,
        "agreement": agreement,
        "recommendation": reco,
        "statistical_prediction": analyst.get("statistical_prediction") or {},
        "metrics": metrics or {},
        "status": review.get("status", "accepted"),
        "accepted": review.get("accepted", True),
    }


def _zone(reco: dict[str, Any], kind: str) -> str:
    if kind == "entry":
        v = reco.get("entry")
        return str(v) if v is not None else "See chart / platform recommendation"
    if kind == "stop":
        v = reco.get("stop")
        return str(v) if v is not None else "Define below structure / ATR-based"
    if kind == "target":
        v = reco.get("r_target") or reco.get("target")
        rr = reco.get("rr")
        if v is not None:
            return str(v)
        if rr:
            return f"{rr}R target"
        return "Platform R-target"
    return ""


def _extract_section(reasoning: str, keyword: str) -> str:
    """Best-effort paragraph containing keyword."""
    if not reasoning:
        return ""
    kw = keyword.lower()
    for sentence in reasoning.replace("\n", " ").split(". "):
        if kw in sentence.lower():
            return sentence.strip() + ("." if not sentence.endswith(".") else "")
    return ""
