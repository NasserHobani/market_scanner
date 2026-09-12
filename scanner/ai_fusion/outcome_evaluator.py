# -*- coding: utf-8 -*-
"""Evaluate platform, prediction, and LLM separately on trade close."""
from __future__ import annotations

from typing import Any

from scanner.ai_learning.failure_classifier import classify_evaluation

FUSION_PATTERNS = (
    "prediction_correct_llm_wrong",
    "prediction_wrong_llm_correct",
    "prediction_and_llm_agree_correct",
    "prediction_and_llm_agree_wrong",
    "llm_overrides_good_prediction",
    "llm_rejects_bad_prediction",
    "prediction_conflict",
    "repeated_prediction_failure",
)


def _trade_won(trade_result: dict[str, Any]) -> bool:
    status = str(trade_result.get("status", "")).lower()
    r = trade_result.get("r_multiple")
    return status in ("won", "win") or (r is not None and float(r) > 0)


def evaluate_outcome(*,
                     trade_result: dict[str, Any],
                     fusion_record: dict[str, Any] | None = None,
                     advisor_evaluation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Additive fusion evaluation — does not replace advisor evaluation."""
    won = _trade_won(trade_result)
    fusion = fusion_record or {}
    adv = advisor_evaluation or {}

    pred_available = bool(fusion.get("prediction_available"))
    pred_label = str(fusion.get("prediction_label") or "").upper()
    pred_prob = fusion.get("prediction_probability")
    pred_correct = None
    if pred_available and pred_label:
        actual = "WIN" if won else "LOSS"
        pred_correct = pred_label == actual

    llm_agreement = fusion.get("llm_agreement") or adv.get("advisor_agreement", "")
    llm_conf = fusion.get("llm_confidence") or adv.get("advisor_confidence")
    llm_assessment = fusion.get("llm_prediction_assessment", "")

    platform_correct = adv.get("advisor_correct")
    if platform_correct is None:
        platform_correct = won if str(llm_agreement).lower() == "agree" else None

    fusion_state = str(fusion.get("fusion_state", "PREDICTION_UNAVAILABLE")).upper()
    pattern = _detect_pattern(
        pred_available=pred_available,
        pred_correct=pred_correct,
        llm_agreement=str(llm_agreement).lower(),
        advisor_correct=adv.get("advisor_correct"),
        fusion_state=fusion_state,
        won=won,
    )

    llm_eval = classify_evaluation({
        "advisor_agreement": llm_agreement,
        "won": won,
        "lost": not won,
        "hallucination": adv.get("hallucination", False),
        "false_warning": adv.get("false_warning", False),
        "missed_warning": adv.get("missed_warning", False),
        "advisor_confidence": llm_conf or 0,
        "trade_result": trade_result.get("status", ""),
        "r_multiple": trade_result.get("r_multiple"),
    })

    return {
        "trade_id": trade_result.get("trade_id", ""),
        "platform": {"correct": platform_correct},
        "prediction": {
            "available": pred_available,
            "probability_win": pred_prob,
            "correct": pred_correct,
            "label": pred_label,
        },
        "llm": {
            "agreement": llm_agreement,
            "confidence": llm_conf,
            "assessment": llm_assessment,
            "correct": llm_eval.get("advisor_correct"),
            "failure_type": llm_eval.get("failure_type"),
        },
        "fusion": {
            "state": fusion_state,
            "pattern": pattern,
            "useful": pattern in ("prediction_and_llm_agree_correct", "llm_rejects_bad_prediction"),
        },
    }


def _detect_pattern(*,
                    pred_available: bool,
                    pred_correct: bool | None,
                    llm_agreement: str,
                    advisor_correct: bool | None,
                    fusion_state: str,
                    won: bool) -> str:
    if not pred_available:
        return "prediction_unavailable"
    if fusion_state in ("PREDICTION_CONFLICT", "STATISTICAL_CONFLICT"):
        return "prediction_conflict"
    if pred_correct is True and advisor_correct is False:
        return "prediction_correct_llm_wrong"
    if pred_correct is False and advisor_correct is True:
        return "prediction_wrong_llm_correct"
    if pred_correct is True and llm_agreement == "agree":
        return "prediction_and_llm_agree_correct"
    if pred_correct is False and llm_agreement == "agree":
        return "prediction_and_llm_agree_wrong"
    if pred_correct is True and llm_agreement == "disagree":
        return "llm_overrides_good_prediction"
    if pred_correct is False and llm_agreement == "disagree":
        return "llm_rejects_bad_prediction"
    if pred_correct is False:
        return "repeated_prediction_failure"
    return "neutral"
