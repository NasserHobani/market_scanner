# -*- coding: utf-8 -*-
"""Normalize AIA-13 analyst JSON into validator-compatible required fields."""
from __future__ import annotations

from typing import Any

# ═══ لا رأي ليس رأياً ═══
#
# قِيست ٧٥ مراجعة فيها قرار من النموذج::
#
#     wait          65
#     insufficient   5   ← «لا أستطيع الحكم»
#     avoid          4
#     watch          1
#     buy            0
#
# و«insufficient» لم تكن في الخريطة، فسقطت على الافتراضي وعُرضت
# «⚪ مراقبة». أي أنّ خمس حالات قال فيها النموذج **لا أعرف**
# ظهرت للمستخدم موقفاً.
#
# وأسوأ منها ``"none": "avoid"``: النموذج يقول «لا إجراء» فيُترجَم
# «⛔ تجنّب» — وهي توصية سلبية صريحة. لا موقفَ يصير موقفاً ضدّ.
#
# والافتراضي الصامت هو الآفة: نصٌّ فارغ، أو رفضٌ، أو مخرَجٌ تالف —
# كلّها كانت تُعرض «مراقبة». فالشاشة تمتلئ بآراءٍ لم يقلها أحد.
#
# فالآن: ما لا يُفهَم يُعلَن ``unknown`` ويُعرض «لا رأي».
_ACTION_MAP = {
    "buy": "buy", "long": "buy", "شراء": "buy",
    "sell": "sell", "short": "sell", "بيع": "sell",
    "wait": "wait", "انتظار": "wait", "hold": "wait",
    "watch": "watch", "مراقبة": "watch", "monitor": "watch",
    "avoid": "avoid", "تجنب": "avoid", "تجنّب": "avoid",

    # امتناعٌ صريح — يُعلَن ولا يُترجَم موقفاً
    "none": "unknown", "no_action": "unknown", "لا إجراء": "unknown",
    "insufficient": "unknown", "insufficient_data": "unknown",
    "unknown": "unknown", "unclear": "unknown", "n/a": "unknown",
    "لا أعرف": "unknown", "غير كافٍ": "unknown", "غير كاف": "unknown",
}

# القيم المسموح خروجها — يُتحقّق بها بدل الاعتماد على قيم الخريطة
ACTIONS = ("buy", "sell", "wait", "watch", "avoid", "unknown")

_DIR_MAP = {
    "bullish": "bullish", "صاعد": "bullish", "up": "bullish",
    "bearish": "bearish", "هابط": "bearish", "down": "bearish",
    "sideways": "sideways", "جانبي": "sideways", "range": "sideways",
    "unclear": "unclear", "غير واضح": "unclear", "unknown": "unclear",
}


def _clamp_conf(val: Any, default: float = 0.0) -> float:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return default
    if 0.0 < v <= 1.0:
        v *= 100.0
    return max(0.0, min(100.0, v))


def _norm_action(val: Any) -> str:
    """قرار النموذج مُوحَّداً — و«unknown» لما لا يُفهَم.

    الافتراضي كان ``"watch"``: أي أنّ كل مخرَجٍ تالف أو فارغ أو
    غير معروف كان يُعرض «مراقبة». فحصٌ لا يفشل ظاهرياً وينتج
    رأياً من لا شيء.
    """
    key = str(val or "").strip().lower()
    if key in _ACTION_MAP:
        return _ACTION_MAP[key]
    if key in ACTIONS:
        return key
    return "unknown"


def _norm_dir(val: Any) -> str:
    key = str(val or "").strip().lower()
    return _DIR_MAP.get(key, key if key in _DIR_MAP.values() else "unclear")


def extract_analyst_fields(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Pull optional AIA-13 fields from parsed/raw response."""
    src = dict(parsed or {})
    # Prefer nested analyst block if present
    nested = src.get("analyst") if isinstance(src.get("analyst"), dict) else {}
    merged = {**nested, **{k: v for k, v in src.items() if k != "analyst"}}

    reco = merged.get("recommendation")
    if not isinstance(reco, dict):
        reco = {}
    cmv = merged.get("current_market_view")
    if not isinstance(cmv, dict):
        cmv = {}
    nto = merged.get("near_term_outlook")
    if not isinstance(nto, dict):
        nto = {}
    pred = merged.get("statistical_prediction")
    if not isinstance(pred, dict):
        pred = {}
    assess = merged.get("advisor_assessment")
    if not isinstance(assess, dict):
        assess = {}

    action_raw = reco.get("action") or merged.get("advisor_action") or ""
    action = _norm_action(action_raw) if str(action_raw).strip() else ""
    conf = reco.get("confidence")
    if conf is None:
        conf = assess.get("confidence", merged.get("confidence"))
    conf_f = _clamp_conf(conf, float(merged.get("confidence") or 0) if merged.get("confidence") is not None else 0.0)

    direction = _norm_dir(cmv.get("direction") or merged.get("market_direction") or "")
    if not (cmv.get("direction") or merged.get("market_direction")):
        direction = ""
    outlook_raw = nto.get("direction") or merged.get("outlook_direction") or direction
    outlook_dir = _norm_dir(outlook_raw) if outlook_raw else ""
    try:
        horizon = int(nto.get("horizon_days") or 7)
    except (TypeError, ValueError):
        horizon = 7
    horizon = max(3, min(7, horizon))
    outlook_conf = _clamp_conf(nto.get("confidence"), conf_f) if nto.get("confidence") is not None else conf_f

    agreement = str(assess.get("agreement") or merged.get("agreement") or "partial").lower()
    if agreement == "insufficient":
        agreement = "partial"

    return {
        "language": merged.get("language") or "ar",
        "recommendation": {"action": action, "confidence": conf_f} if action else {"action": "", "confidence": conf_f},
        "current_market_view": {
            "direction": direction or "unclear",
            "confidence": _clamp_conf(cmv.get("confidence"), conf_f) if cmv else conf_f,
        },
        "near_term_outlook": {
            "horizon_days": horizon,
            "direction": outlook_dir or "unclear",
            "confidence": outlook_conf,
        },
        "summary": str(merged.get("summary") or ""),
        "positive_signals": list(merged.get("positive_signals") or []),
        "negative_signals": list(merged.get("negative_signals") or []),
        "risks": list(merged.get("risks") or []),
        "what_to_watch": list(merged.get("what_to_watch") or []),
        "invalidation_conditions": list(
            merged.get("invalidation_conditions") or merged.get("invalidation") or []
        ),
        # يُملأ لاحقاً من **المنصّة** لا من ادّعاء النموذج — انظر
        # ``gate_prediction`` أدناه. ما يصل هنا مجرّد ما قاله النموذج،
        # ولا يُعتمد قبل المقارنة بالحقيقة.
        "statistical_prediction": {
            "available": bool(pred.get("available")),
            "probability_win": pred.get("probability_win"),
            "model": pred.get("model"),
            "calibration": pred.get("calibration"),
            "oos": pred.get("oos"),
            "baseline": pred.get("baseline"),
        },
        "advisor_assessment": {
            "agreement": agreement if agreement in ("agree", "disagree", "partial") else "partial",
            "confidence": conf_f,
        },
        "supporting_evidence": list(merged.get("supporting_evidence") or []),
        "contradicting_evidence": list(merged.get("contradicting_evidence") or []),
        "missing_information": list(merged.get("missing_information") or []),
        "suggested_experiment": merged.get("suggested_experiment"),
        "shadow_mode_acknowledged": bool(merged.get("shadow_mode_acknowledged", True)),
        "scenarios": merged.get("scenarios") if isinstance(merged.get("scenarios"), dict) else {},
        "actionable_advice": str(merged.get("actionable_advice") or ""),
        "data_quality_note": str(merged.get("data_quality_note") or ""),
    }


def normalize_analyst_response(parsed: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure REQUIRED_FIELDS exist without dropping optional analyst extras."""
    src = dict(parsed or {})
    analyst = extract_analyst_fields(src)

    agreement = str(src.get("agreement") or analyst["advisor_assessment"]["agreement"] or "partial").lower()
    if agreement == "insufficient":
        agreement = "partial"
    if agreement not in ("agree", "disagree", "partial"):
        agreement = "partial"

    confidence = src.get("confidence")
    if confidence is None:
        confidence = analyst["recommendation"]["confidence"]
    confidence = _clamp_conf(confidence)

    summary = str(src.get("summary") or analyst.get("summary") or "").strip()
    reasoning = str(src.get("reasoning") or "").strip()
    if not reasoning:
        parts = [summary]
        if analyst.get("actionable_advice"):
            parts.append(str(analyst["actionable_advice"]))
        if analyst.get("data_quality_note"):
            parts.append(str(analyst["data_quality_note"]))
        reasoning = " ".join(p for p in parts if p).strip() or summary

    experiment = src.get("suggested_experiment")
    if not isinstance(experiment, dict):
        experiment = analyst.get("suggested_experiment")
    if not isinstance(experiment, dict):
        experiment = {"hypothesis": "", "method": "", "expected_outcome": ""}

    out = dict(src)
    out.update({
        "agreement": agreement,
        "confidence": confidence,
        "summary": summary or "لا توجد خلاصة كافية من الأدلة المتاحة.",
        "reasoning": reasoning or summary or "الأدلة غير كافية لتفصيل أوسع.",
        "supporting_evidence": list(src.get("supporting_evidence") or analyst["supporting_evidence"] or []),
        "contradicting_evidence": list(
            src.get("contradicting_evidence") or analyst["contradicting_evidence"] or []
        ),
        "risks": list(src.get("risks") or analyst["risks"] or []),
        "missing_information": list(
            src.get("missing_information") or analyst["missing_information"] or []
        ),
        "suggested_experiment": experiment,
        "shadow_mode_acknowledged": bool(src.get("shadow_mode_acknowledged", True)),
        "language": analyst["language"],
        "recommendation": analyst["recommendation"],
        "current_market_view": analyst["current_market_view"],
        "near_term_outlook": analyst["near_term_outlook"],
        "positive_signals": analyst["positive_signals"],
        "negative_signals": analyst["negative_signals"],
        "what_to_watch": analyst["what_to_watch"],
        "invalidation_conditions": analyst["invalidation_conditions"],
        "statistical_prediction": analyst["statistical_prediction"],
        "advisor_assessment": analyst["advisor_assessment"],
        "scenarios": analyst.get("scenarios") or {},
        "actionable_advice": analyst.get("actionable_advice") or "",
        "data_quality_note": analyst.get("data_quality_note") or "",
    })
    # Nested recommendation must not look like top-level buy/sell override keys —
    # keep nested only (already the case).
    return out
