# -*- coding: utf-8 -*-
"""Configurable evidence thresholds for learning recommendations."""
from __future__ import annotations

# Minimum sample sizes for recommendation strength (inclusive lower bounds).
THRESHOLD_INSUFFICIENT_MAX = 1
THRESHOLD_EMERGING = 3
THRESHOLD_RECURRING = 10
THRESHOLD_STRONG = 20

RECOMMENDATION_INSUFFICIENT_EN = "Insufficient evidence"
RECOMMENDATION_INSUFFICIENT_AR = "أدلة غير كافية — لا تغيّر الإعدادات بناءً على هذه الحالة وحدها"

RECOMMENDATION_EMERGING_EN = "Emerging pattern"
RECOMMENDATION_EMERGING_AR = "نمط ناشئ — راقب التكرار قبل اتخاذ إجراء"

RECOMMENDATION_RECURRING_EN = "Recurring pattern"
RECOMMENDATION_RECURRING_AR = "نمط متكرر — يستحق المراجعة في مختبر البحث"

RECOMMENDATION_STRONG_EN = "Strong recurring pattern"
RECOMMENDATION_STRONG_AR = "نمط قوي ومتكرر — أولوية عالية للتحقق التجريبي"


def recommendation_for_sample(sample_size: int) -> dict[str, str]:
    """Return recommendation label (EN + AR) and strength key for a sample size."""
    n = max(0, int(sample_size or 0))
    if n <= THRESHOLD_INSUFFICIENT_MAX:
        return {
            "strength": "insufficient",
            "recommendation": RECOMMENDATION_INSUFFICIENT_EN,
            "recommendation_ar": RECOMMENDATION_INSUFFICIENT_AR,
        }
    if n < THRESHOLD_EMERGING:
        return {
            "strength": "insufficient",
            "recommendation": RECOMMENDATION_INSUFFICIENT_EN,
            "recommendation_ar": RECOMMENDATION_INSUFFICIENT_AR,
        }
    if n < THRESHOLD_RECURRING:
        return {
            "strength": "emerging",
            "recommendation": RECOMMENDATION_EMERGING_EN,
            "recommendation_ar": RECOMMENDATION_EMERGING_AR,
        }
    if n < THRESHOLD_STRONG:
        return {
            "strength": "recurring",
            "recommendation": RECOMMENDATION_RECURRING_EN,
            "recommendation_ar": RECOMMENDATION_RECURRING_AR,
        }
    return {
        "strength": "strong",
        "recommendation": RECOMMENDATION_STRONG_EN,
        "recommendation_ar": RECOMMENDATION_STRONG_AR,
    }
