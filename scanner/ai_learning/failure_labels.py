# -*- coding: utf-8 -*-
"""Arabic/English display labels and lesson titles for failure types."""
from __future__ import annotations

FAILURE_LABELS_AR: dict[str, str] = {
    "hallucination": "هلوسة",
    "missed_warning": "تحذير مفقود",
    "wrong_agreement": "اتفاق خاطئ",
    "other_failure": "فشل آخر",
    "false_warning": "تحذير خاطئ",
    "partial_on_loss": "اتفاق جزئي على صفقة خاسرة",
    "partial_on_win": "اتفاق جزئي على صفقة رابحة",
    "correct_disagreement": "اعتراض صحيح",
    "incorrect_disagreement": "اعتراض خاطئ",
    "high_confidence_wrong": "ثقة مرتفعة مع نتيجة خاطئة",
    "low_confidence_wrong": "ثقة منخفضة مع نتيجة خاطئة",
    "success_cluster": "نمط نجاح",
}

FAILURE_TITLES_EN: dict[str, str] = {
    "hallucination": "Claude cited evidence not present in the decision package",
    "missed_warning": "Claude failed to warn before a significant loss",
    "wrong_agreement": "Claude agreed with a trade that subsequently lost",
    "other_failure": "Advisor review did not align with trade outcome",
    "false_warning": "Claude was overly cautious on winning trades",
    "partial_on_loss": "Partial agreement failed to anticipate downside",
    "partial_on_win": "Partial agreement on trades that still won",
    "correct_disagreement": "Claude correctly challenged a losing platform decision",
    "incorrect_disagreement": "Claude disagreed with trades that subsequently won",
    "high_confidence_wrong": "Claude showed overconfidence on incorrect reviews",
    "low_confidence_wrong": "Low-confidence reviews still produced incorrect guidance",
    "success_cluster": "Advisor correctly assessed trades in this segment",
}

FAILURE_DESCRIPTIONS_AR: dict[str, str] = {
    "false_warning": "حذر المستشار من الدخول أو أشار لمخاطر، لكن الصفقة أغلقت بربح.",
    "partial_on_loss": "أبدى المستشار اتفاقاً جزئياً، لكن الصفقة أغلقت بخسارة.",
    "partial_on_win": "أبدى المستشار اتفاقاً جزئياً والصفقة ربحت — التقييم غير حاسم.",
    "correct_disagreement": "اعترض المستشار على الإشارة وكانت الصفقة خاسرة — اعتراض صحيح.",
    "incorrect_disagreement": "اعترض المستشار على الإشارة لكن الصفقة ربحت.",
    "wrong_agreement": "وافق المستشار على الصفقة لكنها أغلقت بخسارة.",
    "hallucination": "استشهد المستشار بأدلة غير موجودة في حزمة القرار.",
    "missed_warning": "لم يحذر المستشار قبل خسارة كبيرة.",
    "high_confidence_wrong": "أبدى المستشار ثقة عالية لكن التقييم كان خاطئاً.",
    "low_confidence_wrong": "ثقة منخفضة لكن التوجيه كان مضللاً.",
    "other_failure": "لم يتوافق تقييم المستشار مع نتيجة الصفقة.",
    "success_cluster": "أصاب المستشار في تقييم صفقات هذه الشريحة.",
}


def title_ar(failure_type: str) -> str:
    return FAILURE_LABELS_AR.get(failure_type, failure_type.replace("_", " "))


def title_en(failure_type: str) -> str:
    return FAILURE_TITLES_EN.get(failure_type, failure_type.replace("_", " ").title())


def description_ar(failure_type: str) -> str:
    return FAILURE_DESCRIPTIONS_AR.get(failure_type, "")
