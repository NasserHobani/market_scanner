# -*- coding: utf-8 -*-
"""Failure classification for advisor evaluations — AIA-05.5."""
from __future__ import annotations

from typing import Any

HIGH_CONFIDENCE_THRESHOLD = 80
LOW_CONFIDENCE_THRESHOLD = 60

FAILURE_TYPES = frozenset({
    "hallucination",
    "missed_warning",
    "wrong_agreement",
    "other_failure",
    "false_warning",
    "partial_on_loss",
    "partial_on_win",
    "correct_disagreement",
    "incorrect_disagreement",
    "low_confidence_wrong",
    "high_confidence_wrong",
})

SUCCESS_TYPES = frozenset({
    "agree_success",
    "correct_disagreement",
})


def outcome_label(*, won: bool, lost: bool) -> str:
    if won:
        return "win"
    if lost:
        return "loss"
    return "neutral"


def advisor_correctness(*, agreement: str, won: bool, lost: bool) -> bool:
    """Explicit advisor correctness — partial is never fully correct."""
    agreement = str(agreement or "partial").lower()
    if agreement == "agree" and won:
        return True
    if agreement == "disagree" and lost:
        return True
    return False


def classify_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Classify one evaluation record or in-flight evaluation fields."""
    agreement = str(evaluation.get("advisor_agreement")
                    or evaluation.get("agreement", "partial")).lower()
    won = bool(evaluation.get("won"))
    lost = bool(evaluation.get("lost"))
    if not won and not lost:
        status = str(evaluation.get("trade_result", "")).upper()
        won = status in ("WON", "WIN") or (
            evaluation.get("r_multiple") is not None
            and float(evaluation["r_multiple"]) > 0
        )
        lost = status in ("LOST", "LOSS") or (
            evaluation.get("r_multiple") is not None
            and float(evaluation["r_multiple"]) < 0
        )

    hallucination = bool(evaluation.get("hallucination"))
    missed_warning = bool(evaluation.get("missed_warning"))
    false_warning = bool(evaluation.get("false_warning"))
    confidence = float(evaluation.get("advisor_confidence") or 0)

    correct = advisor_correctness(agreement=agreement, won=won, lost=lost)
    outcome = outcome_label(won=won, lost=lost)

    evaluation_type = "other_failure"
    failure_type: str | None = None
    is_failure = False

    if hallucination:
        evaluation_type = failure_type = "hallucination"
        is_failure = True
    elif agreement == "partial" and lost:
        evaluation_type = failure_type = "partial_on_loss"
        is_failure = True
    elif agreement == "partial" and won:
        evaluation_type = failure_type = "partial_on_win"
        is_failure = True
    elif missed_warning:
        evaluation_type = failure_type = "missed_warning"
        is_failure = True
    elif agreement == "disagree" and won:
        evaluation_type = failure_type = "incorrect_disagreement"
        is_failure = True
        false_warning = True
    elif agreement == "disagree" and lost:
        evaluation_type = "correct_disagreement"
        failure_type = None
        is_failure = False
    elif agreement == "agree" and lost:
        evaluation_type = failure_type = "wrong_agreement"
        is_failure = True
    elif false_warning and won and agreement != "disagree":
        evaluation_type = failure_type = "false_warning"
        is_failure = True
    elif agreement == "agree" and won:
        evaluation_type = "agree_success"
        is_failure = False
    elif not correct:
        evaluation_type = failure_type = "other_failure"
        is_failure = True

    secondary_type: str | None = None
    if is_failure:
        if confidence >= HIGH_CONFIDENCE_THRESHOLD:
            secondary_type = "high_confidence_wrong"
        elif confidence < LOW_CONFIDENCE_THRESHOLD:
            secondary_type = "low_confidence_wrong"

    return {
        "agreement": agreement,
        "outcome": outcome,
        "advisor_correct": correct,
        "evaluation_type": evaluation_type,
        "failure_type": failure_type,
        "secondary_type": secondary_type,
        "is_failure": is_failure,
        "false_warning": false_warning,
    }
