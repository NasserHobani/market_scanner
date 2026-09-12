# -*- coding: utf-8 -*-
"""Compare platform decision, LightGBM prediction, and LLM assessment."""
from __future__ import annotations

from typing import Any


def _normalize_action(action: str) -> str:
    a = str(action or "").upper().strip()
    if a in ("BUY", "LONG", "WIN"):
        return "BUY"
    if a in ("SELL", "SHORT", "LOSS"):
        return "SELL"
    return a


def _prediction_direction(pred: dict[str, Any]) -> str:
    if not pred.get("available"):
        return ""
    label = str(pred.get("prediction") or "").upper()
    if label == "WIN":
        return "BUY"
    if label == "LOSS":
        return "SELL"
    return label


def _llm_agreement(llm: dict[str, Any]) -> str:
    return str(llm.get("agreement") or llm.get("advisor_agreement") or "").lower()


def analyze(*,
            platform_action: str,
            prediction: dict[str, Any],
            llm_assessment: dict[str, Any],
            platform_confidence: float | None = None) -> dict[str, Any]:
    """Return fusion_state and agreement breakdown."""
    plat = _normalize_action(platform_action)
    pred_dir = _prediction_direction(prediction)
    llm_agree = _llm_agreement(llm_assessment)
    pred_available = bool(prediction.get("available"))

    if not pred_available:
        return {
            "fusion_state": "PREDICTION_UNAVAILABLE",
            "platform_action": plat,
            "prediction_direction": None,
            "llm_agreement": llm_agree or "insufficient",
            "aligned": False,
            "details": "no active statistical prediction",
        }

    pred_prob = prediction.get("probability_win")
    plat_bullish = plat in ("BUY", "LONG", "")
    pred_bullish = pred_dir in ("BUY", "WIN", "")
    pred_conflicts_platform = (
        plat and pred_dir and (
            (plat_bullish and not pred_bullish) or (not plat_bullish and pred_bullish)
        )
    )

    llm_disagrees = llm_agree in ("disagree", "partial")
    llm_agrees = llm_agree in ("agree", "supported")

    if plat and pred_dir and llm_agrees and not pred_conflicts_platform:
        state = "ALIGNED"
    elif pred_conflicts_platform and llm_disagrees:
        state = "STATISTICAL_CONFLICT"
    elif pred_conflicts_platform:
        state = "PREDICTION_CONFLICT"
    elif llm_disagrees and not pred_conflicts_platform:
        state = "LLM_CONFLICT"
    elif llm_agree in ("insufficient", "") and pred_available:
        state = "INSUFFICIENT_EVIDENCE"
    else:
        state = "MIXED"

    return {
        "fusion_state": state,
        "platform_action": plat,
        "prediction_direction": pred_dir,
        "prediction_probability_win": pred_prob,
        "llm_agreement": llm_agree,
        "platform_confidence": platform_confidence,
        "aligned": state == "ALIGNED",
        "statistical_conflict": pred_conflicts_platform,
        "llm_conflict": llm_disagrees,
    }
