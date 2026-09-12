# -*- coding: utf-8 -*-
"""Sample-aware reliability states for advisor evaluation metrics."""
from __future__ import annotations

from typing import Any

STATE_NO_DATA = "NO_DATA"
STATE_INSUFFICIENT = "INSUFFICIENT"
STATE_EARLY_SIGNAL = "EARLY_SIGNAL"
STATE_EMERGING = "EMERGING"
STATE_MEANINGFUL = "MEANINGFUL"
STATE_STRONG = "STRONG_SAMPLE"

THRESHOLDS = {
    STATE_NO_DATA: 0,
    STATE_INSUFFICIENT: 3,
    STATE_EARLY_SIGNAL: 10,
    STATE_EMERGING: 20,
    STATE_MEANINGFUL: 50,
}


def reliability_state(sample_size: int) -> str:
    n = max(0, int(sample_size or 0))
    if n == 0:
        return STATE_NO_DATA
    if n <= 2:
        return STATE_INSUFFICIENT
    if n <= 9:
        return STATE_EARLY_SIGNAL
    if n <= 19:
        return STATE_EMERGING
    if n <= 49:
        return STATE_MEANINGFUL
    return STATE_STRONG


def reliability_label(state: str, *, lang: str = "en") -> str:
    labels_en = {
        STATE_NO_DATA: "No data",
        STATE_INSUFFICIENT: "Insufficient sample",
        STATE_EARLY_SIGNAL: "Early signal",
        STATE_EMERGING: "Emerging",
        STATE_MEANINGFUL: "Meaningful sample",
        STATE_STRONG: "Strong sample",
    }
    labels_ar = {
        STATE_NO_DATA: "لا بيانات",
        STATE_INSUFFICIENT: "عيّنة غير كافية",
        STATE_EARLY_SIGNAL: "إشارة مبكرة",
        STATE_EMERGING: "ناشئ",
        STATE_MEANINGFUL: "عيّنة ذات معنى",
        STATE_STRONG: "عيّنة قوية",
    }
    if lang == "ar":
        return labels_ar.get(state, state)
    return labels_en.get(state, state)


def annotate_metric(metric: dict[str, Any] | None, *, value_key: str = "value") -> dict[str, Any]:
    """Add reliability state to a metric dict — never imply failure on small samples."""
    metric = dict(metric or {})
    n = int(metric.get("sample_size") or 0)
    state = reliability_state(n)
    metric["reliability_state"] = state
    metric["reliability_label"] = reliability_label(state)
    metric["reliability_label_ar"] = reliability_label(state, lang="ar")
    metric["interpretable"] = state in (STATE_MEANINGFUL, STATE_STRONG)
    if not metric.get(value_key) and n > 0:
        metric["caution"] = "Do not interpret accuracy as model failure on small samples"
    return metric


def evaluation_ui_envelope(sample_size: int, overall_accuracy: float | None,
                           advisor_score: float | None, grade: str) -> dict[str, Any]:
    state = reliability_state(sample_size)
    return {
        "sample_size": sample_size,
        "overall_accuracy": overall_accuracy,
        "advisor_score": advisor_score,
        "grade": grade,
        "reliability_state": state,
        "reliability_label": reliability_label(state),
        "reliability_label_ar": reliability_label(state, lang="ar"),
        "interpretable": state in (STATE_MEANINGFUL, STATE_STRONG),
        "accuracy_caution": (
            "Accuracy is not statistically meaningful at this sample size"
            if state in (STATE_NO_DATA, STATE_INSUFFICIENT, STATE_EARLY_SIGNAL) else ""
        ),
    }
