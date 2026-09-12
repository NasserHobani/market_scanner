# -*- coding: utf-8 -*-
"""Localized user-facing presentation for AI reviews — AIA-06.1."""
from __future__ import annotations

import re
from typing import Any

SUPPORTED_LANGUAGES = ("ar", "en")
DEFAULT_LANGUAGE = "ar"

AGREEMENT_LABELS = {
    "ar": {
        "agree": "متفق مع النظام",
        "disagree": "مختلف مع النظام",
        "partial": "متفق جزئيًا",
        "unknown": "غير محدد",
    },
    "en": {
        "agree": "Agrees with platform",
        "disagree": "Disagrees with platform",
        "partial": "Partial agreement",
        "unknown": "Unknown",
    },
}

VERDICT_LABELS = {
    "ar": {
        "buy": "شراء",
        "sell": "بيع",
        "none": "انتظار / عدم تداول",
        "watch": "مراقبة",
        "avoid": "تجنّب",
        "unknown": "لا رأي",
    },
    "en": {
        "buy": "Buy",
        "sell": "Sell",
        "none": "Wait / no trade",
        "watch": "Watch",
        "avoid": "Avoid",
        "unknown": "No opinion",
    },
}

VERDICT_EMOJI = {
    "buy": "🟢",
    "sell": "🔴",
    "none": "⏸️",
    "wait": "🟡",
    "watch": "👁️",
    "avoid": "⛔",
}

TITLE_LABELS = {
    "ar": {"review": "تحليل المستشار", "manual": "تحليل المستشار — يدوي"},
    "en": {"review": "Advisor Analysis", "manual": "Manual Advisor Analysis"},
}

CONFIDENCE_LABELS = {
    "ar": "ثقة المستشار",
    "en": "Advisor confidence",
}

DIRECTION_LABELS = {
    "ar": {
        "bullish": "صاعد",
        "bearish": "هابط",
        "sideways": "جانبي",
        "unclear": "غير واضح",
    },
    "en": {
        "bullish": "Bullish",
        "bearish": "Bearish",
        "sideways": "Sideways",
        "unclear": "Unclear",
    },
}

ADVISOR_ACTION_LABELS = {
    "ar": {
        "buy": "🟢 شراء",
        "sell": "🔴 بيع",
        "wait": "🟡 انتظار",
        "watch": "⚪ مراقبة",
        "avoid": "⛔ تجنب",
        # امتناعٌ يُعلَن — لا يُخفى خلف «مراقبة»
        "unknown": "◌ لا رأي",
    },
    "en": {
        "buy": "🟢 Buy",
        "sell": "🔴 Sell",
        "wait": "🟡 Wait",
        "watch": "⚪ Watch",
        "avoid": "⛔ Avoid",
        "unknown": "◌ No opinion",
    },
}

UNAVAILABLE = {"ar": "غير متاح", "en": "Not available"}

# Human-friendly Arabic phrasing — not literal MT.
_PHRASE_AR = [
    (r"\bno actionable edge\b", "لا توجد أفضلية تداول واضحة"),
    (r"\bactionable edge\b", "أفضلية تداول قابلة للتنفيذ"),
    (r"\bdata gaps?\b", "البيانات غير مكتملة"),
    (r"\binsufficient\b", "غير كافٍ"),
    (r"\bnot available\b", "غير متاح"),
    (r"\bunavailable\b", "غير متاح"),
    (r"\bsimilarity win rate\b", "معدل نجاح الحالات التاريخية المشابهة"),
    (r"\bwin rate\b", "معدل النجاح"),
    (r"\bclosed trades?\b", "صفقات مغلقة"),
    (r"\bnone action\b", "قرار بعدم التداول"),
    (r"\bplatform(?:'s)?\b", "النظام"),
    (r"\bwell[- ]supported\b", "مدعوم جيدًا"),
    (r"\bpervasive\b", "واسع الانتشار"),
    (r"\bconflicting signals?\b", "الإشارات متعارضة"),
    (r"\bmissing information\b", "معلومات ناقصة"),
    (r"\bpositive signal\b", "إشارة إيجابية"),
    (r"\bnegative signal\b", "إشارة سلبية"),
    (r"\bwait\b", "انتظار"),
    (r"\bavoid\b", "تجنّب"),
]


def localize_phrase(text: str, lang: str) -> str:
    """Rule-based friendly Arabic for common advisor phrases; English unchanged."""
    if not text or lang == "en":
        return text
    out = text
    for pattern, repl in _PHRASE_AR:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def agreement_label(agreement: str, lang: str = DEFAULT_LANGUAGE) -> str:
    key = (agreement or "unknown").lower()
    return AGREEMENT_LABELS.get(lang, AGREEMENT_LABELS["ar"]).get(key, AGREEMENT_LABELS[lang]["unknown"])


def platform_action(recommendation: dict[str, Any] | None) -> str:
    reco = recommendation or {}
    side = str(reco.get("side") or reco.get("direction") or "").lower()
    action = str(reco.get("action") or "").lower()
    if side in ("buy", "long"):
        return "buy"
    if side in ("sell", "short"):
        return "sell"
    if action in ("none", "hold", "wait", ""):
        return "none"
    if action in ("unknown", "insufficient", "unclear"):
        return "unknown"
    if action in ("watch", "monitor"):
        return "watch"
    if side:
        return side
    return "none"


def verdict_label(action: str, lang: str = DEFAULT_LANGUAGE) -> str:
    key = (action or "none").lower()
    return VERDICT_LABELS.get(lang, VERDICT_LABELS["ar"]).get(key, action)


def verdict_display(action: str, lang: str = DEFAULT_LANGUAGE, *, prefix_platform: bool = False) -> str:
    emoji = VERDICT_EMOJI.get((action or "none").lower(), "")
    label = verdict_label(action, lang)
    if prefix_platform and lang == "ar" and action == "buy":
        return f"{emoji} {label} — وفق قرار النظام".strip()
    if prefix_platform and lang == "en" and action == "buy":
        return f"{emoji} {label} — per platform decision".strip()
    return f"{emoji} {label}".strip()


def _signal_items(evidence: list[Any], lang: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ev in evidence or []:
        if isinstance(ev, str):
            items.append({"text": localize_phrase(ev, lang), "evidence_id": "", "href": ""})
            continue
        if not isinstance(ev, dict):
            continue
        note = ev.get("note") or ev.get("text") or ""
        if not note.strip():
            continue
        items.append({
            "text": localize_phrase(note, lang),
            "evidence_id": ev.get("evidence_id", ""),
            "href": ev.get("href", ""),
            "section": ev.get("label") or ev.get("section", ""),
        })
    return items


def _string_list(items: list[Any], lang: str) -> list[str]:
    out: list[str] = []
    for x in items or []:
        if isinstance(x, str) and x.strip():
            out.append(localize_phrase(x.strip(), lang))
        elif isinstance(x, dict) and x.get("note"):
            out.append(localize_phrase(str(x["note"]), lang))
    return out


def _build_executive_summary(review: dict[str, Any], lang: str, action: str, agree: str) -> str:
    raw = (review.get("summary") or "").strip()
    if lang == "en" and raw:
        return raw[:600]

    conf = review.get("confidence")
    sym = review.get("symbol", "")
    risks = review.get("risks") or []
    missing = review.get("missing_information") or []
    supporting = review.get("supporting_evidence") or []

    if lang == "ar":
        if agree == "disagree":
            return (
                f"يختلف Claude مع قرار النظام لـ {sym}. "
                f"{'أبرز سبب: ' + localize_phrase(str(risks[0]), 'ar') if risks else ''}"
                f"{' درجة الثقة ' + str(int(conf)) + '%.' if conf is not None else ''}"
            ).strip()
        if action == "none" or action == "watch":
            base = (
                "لا أوصي بالدخول في هذه الصفقة حاليًا. "
                if agree != "agree"
                else "قرار النظام بعدم التداول مدعوم بالأدلة الحالية. "
            )
            if missing:
                base += "توجد فجوات في البيانات أو طبقات القرار غير مكتملة. "
            elif not supporting:
                base += "لا توجد أفضلية تداول واضحة بناءً على الأدلة المتاحة. "
            else:
                base += localize_phrase(raw[:280], "ar") if raw else "الأدلة لا تبرر دخولًا قويًا الآن. "
            if risks:
                base += f" أهم مخاطرة: {localize_phrase(str(risks[0]), 'ar')}."
            return base.strip()
        if action == "buy":
            return (
                "الأدلة الحالية تدعم سيناريو الشراء، مع توافق بين اتجاه النظام وتقييم Claude. "
                + (localize_phrase(raw[:200], "ar") if raw else "")
            ).strip()
        if action == "sell":
            return (
                "الأدلة تشير إلى ضغط بيعي محتمل وفق قرار النظام. "
                + (localize_phrase(raw[:200], "ar") if raw else "")
            ).strip()
        if raw:
            return localize_phrase(raw[:400], "ar")
        return "لا توجد خلاصة كافية — راجع الأدلة التقنية."

    return raw[:600] if raw else "No summary available."


def _what_could_change(review: dict[str, Any], lang: str) -> str:
    exp = review.get("suggested_experiment") or {}
    missing = review.get("missing_information") or []
    if lang == "ar":
        if isinstance(exp, dict) and exp.get("expected_outcome"):
            return localize_phrase(str(exp["expected_outcome"]), "ar")
        if missing:
            return "انتظار: " + "؛ ".join(_string_list(missing[:3], "ar"))
        return "تأكيد أقوى من Market Structure وبقية طبقات القرار قبل اعتبار الصفقة قابلة للتنفيذ."
    if isinstance(exp, dict) and exp.get("expected_outcome"):
        return str(exp["expected_outcome"])
    if missing:
        return "Awaiting: " + "; ".join(_string_list(missing[:3], "en"))
    return "Stronger confirmation from decision layers before treating the setup as actionable."


def _disagreement_block(review: dict[str, Any], lang: str, platform: str, claude_view: str) -> dict[str, Any] | None:
    agree = (review.get("agreement") or "").lower()
    if agree != "disagree":
        return None
    risks = _string_list(review.get("risks"), lang)
    contra = _signal_items(review.get("contradicting_evidence") or [], lang)
    key_point = contra[0]["text"] if contra else (risks[0] if risks else "")
    labels = {
        "ar": {
            "platform": "قرار النظام",
            "claude": "رأي المستشار",
            "why": "لماذا يختلف المستشار؟",
            "key": "أهم نقطة خلاف",
            "watch": "ماذا نراقب؟",
        },
        "en": {
            "platform": "Platform decision",
            "claude": "Advisor opinion",
            "why": "Why does the advisor disagree?",
            "key": "Key point of disagreement",
            "watch": "What to watch",
        },
    }[lang if lang in ("ar", "en") else "ar"]
    return {
        "title": "🟠 المستشار يختلف مع النظام" if lang == "ar" else "🟠 Advisor disagrees with platform",
        "platform_decision": verdict_display(platform, lang),
        "claude_opinion": claude_view,
        "why": risks or [c["text"] for c in contra[:3]],
        "key_point": key_point,
        "watch_for": _what_could_change(review, lang),
        "labels": labels,
    }


def _partial_block(review: dict[str, Any], lang: str) -> dict[str, Any] | None:
    if (review.get("agreement") or "").lower() != "partial":
        return None
    pos = _signal_items(review.get("supporting_evidence") or [], lang)
    neg = _signal_items(review.get("contradicting_evidence") or [], lang)
    if lang == "ar":
        return {
            "title": "🟡 اتفاق جزئي",
            "agrees_with": [p["text"] for p in pos[:4]],
            "disagrees_with": [n["text"] for n in neg[:4]],
            "why": (
                "يوجد توافق في بعض الطبقات مع تحفظات في أخرى — راجع الأدلة قبل التنفيذ."
                if not neg
                else "الخلاف ناتج عن تعارض بين إشارات الاتجاه وبقية طبقات القرار."
            ),
        }
    return {
        "title": "🟡 Partial agreement",
        "agrees_with": [p["text"] for p in pos[:4]],
        "disagrees_with": [n["text"] for n in neg[:4]],
        "why": "Some layers align while others remain cautious — verify evidence before acting.",
    }


def build_presentation(review: dict[str, Any], lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    """Build localized presentation from canonical review dict. No LLM call."""
    lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    agree = (review.get("agreement") or "unknown").lower()
    reco = review.get("recommendation") or {}
    action = platform_action(reco)
    conf = review.get("confidence")
    conf_display = f"{int(round(float(conf)))}%" if conf is not None else UNAVAILABLE[lang]

    # AIA-13 analyst fields (from review dict or raw_response) — no second LLM call
    try:
        from scanner.ai_advisor.analyst.normalize import extract_analyst_fields
        analyst = extract_analyst_fields(review.get("raw_response") or review)
    except Exception:  # noqa: BLE001
        analyst = {}

    advice = analyst.get("recommendation") or review.get("recommendation_advice") or {}
    advisor_action = str(advice.get("action") or "").lower()
    if not advisor_action:
        advisor_action = "avoid" if agree == "disagree" else (
            "wait" if action == "none" else action
        )
    market_view = analyst.get("current_market_view") or review.get("current_market_view") or {}
    outlook = analyst.get("near_term_outlook") or review.get("near_term_outlook") or {}
    stat_pred = analyst.get("statistical_prediction") or review.get("statistical_prediction") or {}

    # حاجز العرض للمراجعات القديمة.
    #
    # بوّابة ``analyst.gate`` تحمي كل مراجعة جديدة، لكنّ السجلّ يحوي
    # مراجعات كُتبت قبلها وقد تحمل احتمالاً اخترعه النموذج. وهذه تُعرَض
    # اليوم كما هي، فيقرأ المستخدم رقماً لا نموذج وراءه.
    #
    # القاعدة هنا: احتمال بلا اسم نموذج يذكره السجلّ ليس احتمالاً
    # مقيساً. النموذج النشط يُسجَّل باسمه دائماً؛ فغياب الاسم مع حضور
    # الرقم قرينة كافية على الاختراع.
    if stat_pred.get("available") and not stat_pred.get("model"):
        stat_pred = {**stat_pred, "available": False, "probability_win": None,
                     "legacy_ungated": True}

    pos = _signal_items(
        analyst.get("positive_signals") or review.get("supporting_evidence") or [], lang
    )
    if not pos:
        pos = _signal_items(review.get("supporting_evidence") or [], lang)
    neg = _signal_items(
        analyst.get("negative_signals") or review.get("contradicting_evidence") or [], lang
    )
    if not neg:
        neg = _signal_items(review.get("contradicting_evidence") or [], lang)
    missing = _string_list(review.get("missing_information"), lang)
    risks = _string_list(analyst.get("risks") or review.get("risks"), lang)
    watch = _string_list(analyst.get("what_to_watch") or review.get("what_to_watch"), lang)
    invalidate = _string_list(
        analyst.get("invalidation_conditions") or review.get("invalidation_conditions"), lang
    )

    review_type = review.get("review_type", "automatic")
    title_key = "manual" if review_type == "manual" else "review"

    dir_labels = DIRECTION_LABELS.get(lang, DIRECTION_LABELS["ar"])
    action_labels = ADVISOR_ACTION_LABELS.get(lang, ADVISOR_ACTION_LABELS["ar"])
    mv_dir = str(market_view.get("direction") or "unclear")
    out_dir = str(outlook.get("direction") or "unclear")
    advisor_conf = advice.get("confidence")
    if advisor_conf is None:
        advisor_conf = conf
    advisor_conf_disp = (
        f"{int(round(float(advisor_conf)))}%" if advisor_conf is not None else UNAVAILABLE[lang]
    )

    claude_view = action_labels.get(advisor_action, verdict_display(advisor_action, lang))

    # Separate confidences
    platform_conf = reco.get("confidence")
    if platform_conf is None:
        platform_conf = review.get("platform_confidence")
    pred_prob = None
    if stat_pred.get("available") and stat_pred.get("probability_win") is not None:
        try:
            pw = float(stat_pred["probability_win"])
            pred_prob = f"{pw * 100:.0f}%" if pw <= 1 else f"{pw:.0f}%"
        except (TypeError, ValueError):
            pred_prob = None

    presentation: dict[str, Any] = {
        "language": lang,
        "symbol": review.get("symbol", ""),
        "timeframe": review.get("timeframe", ""),
        "review_id": review.get("review_id", ""),
        "title": TITLE_LABELS[lang][title_key],
        "agreement": agree,
        "agreement_label": agreement_label(agree, lang),
        "agreement_tone": "success" if agree == "agree" else "risk" if agree == "disagree" else "warn",
        "confidence_label": CONFIDENCE_LABELS[lang],
        "confidence": conf,
        "confidence_display": conf_display,
        "platform_action": action,
        "platform_decision": verdict_display(action, lang),
        "claude_opinion": claude_view,
        "advisor_decision": action_labels.get(advisor_action, advisor_action),
        "advisor_action": advisor_action,
        "advisor_confidence_display": advisor_conf_disp,
        "current_market_view": dir_labels.get(mv_dir, mv_dir),
        "current_market_view_key": mv_dir,
        "near_term_outlook": dir_labels.get(out_dir, out_dir),
        "near_term_outlook_key": out_dir,
        "near_term_horizon": outlook.get("horizon_days") or 7,
        "near_term_confidence": outlook.get("confidence"),
        "platform_confidence_display": (
            f"{int(round(float(platform_conf)))}%" if platform_conf is not None else UNAVAILABLE[lang]
        ),
        "prediction_probability_display": pred_prob or UNAVAILABLE[lang],
        "prediction_available": bool(stat_pred.get("available")),
        "statistical_prediction": stat_pred,
        "executive_summary": (
            localize_phrase(str(analyst.get("summary") or ""), lang)
            if analyst.get("summary")
            else _build_executive_summary(review, lang, action, agree)
        ),
        "actionable_advice": localize_phrase(str(analyst.get("actionable_advice") or ""), lang),
        "data_quality_note": localize_phrase(str(analyst.get("data_quality_note") or ""), lang),
        "positive_signals": pos,
        "negative_signals": neg,
        "missing_information": missing,
        "main_risks": risks,
        "what_to_watch": watch,
        "invalidation_conditions": invalidate,
        "what_could_change": (
            "؛ ".join(invalidate[:3]) if invalidate else _what_could_change(review, lang)
        ),
        "scenarios": {
            "bullish": localize_phrase(
                str((analyst.get("scenarios") or {}).get("bullish") or ""), lang
            ),
            "base": localize_phrase(
                str((analyst.get("scenarios") or {}).get("base") or ""), lang
            ),
            "bearish": localize_phrase(
                str((analyst.get("scenarios") or {}).get("bearish") or ""), lang
            ),
        },
        "final_verdict": action_labels.get(advisor_action) or verdict_display(
            action, lang, prefix_platform=(agree == "agree" and action == "buy")
        ),
        "disagreement": _disagreement_block(review, lang, action, claude_view),
        "partial": _partial_block(review, lang),
        "technical": {
            "title": "الأدلة" if lang == "ar" else "Evidence",
            "reasoning": review.get("reasoning", ""),
            "supporting_evidence": review.get("supporting_evidence") or [],
            "contradicting_evidence": review.get("contradicting_evidence") or [],
            "package_diagnostics": review.get("package_diagnostics") or {},
            "validation": {
                "grounding_score": review.get("grounding_score"),
                "hallucination_score": review.get("hallucination_score"),
            },
            "provider": review.get("provider", "") or review.get("provider_id", ""),
            "model": review.get("model", "") or review.get("model_name", ""),
        },
    }

    presentation["sections"] = _visible_sections(presentation)
    return presentation


def build_presentations(review: dict[str, Any]) -> dict[str, Any]:
    """Both languages for client-side switching without re-fetch / without LLM."""
    return {
        "ar": build_presentation(review, "ar"),
        "en": build_presentation(review, "en"),
    }


def _visible_sections(p: dict[str, Any]) -> list[str]:
    sections = ["header", "agreement", "confidence", "market_view", "outlook", "executive_summary"]
    if p.get("actionable_advice"):
        sections.append("actionable_advice")
    if p.get("positive_signals"):
        sections.append("positive_signals")
    if p.get("negative_signals"):
        sections.append("negative_signals")
    if p.get("missing_information"):
        sections.append("missing_information")
    if p.get("main_risks"):
        sections.append("main_risks")
    if p.get("what_to_watch"):
        sections.append("what_to_watch")
    if p.get("invalidation_conditions") or p.get("what_could_change"):
        sections.append("invalidation")
    if p.get("data_quality_note"):
        sections.append("data_quality")
    sc = p.get("scenarios") or {}
    if sc.get("bullish") or sc.get("base") or sc.get("bearish"):
        sections.append("scenarios")
    if p.get("disagreement"):
        sections.append("disagreement")
    if p.get("partial"):
        sections.append("partial")
    sections.append("confidences")
    sections.append("final_verdict")
    sections.append("technical")
    return sections


def history_verdict(review: dict[str, Any], lang: str = DEFAULT_LANGUAGE) -> str:
  """Short verdict for history table."""
  p = build_presentation(review, lang)
  return p.get("final_verdict", "")
