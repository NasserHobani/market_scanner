# -*- coding: utf-8 -*-
"""Separate platform, statistical, and LLM confidence — never mix."""
from __future__ import annotations

from typing import Any


def separate_confidences(*,
                         recommendation: dict[str, Any] | None = None,
                         prediction: dict[str, Any] | None = None,
                         llm_response: dict[str, Any] | None = None) -> dict[str, Any]:
    reco = recommendation or {}
    pred = prediction or {}
    llm = llm_response or {}

    platform_conf = reco.get("confidence")
    if platform_conf is not None:
        try:
            platform_conf = float(platform_conf)
            if platform_conf > 1:
                platform_conf = platform_conf / 100.0
        except (TypeError, ValueError):
            platform_conf = None

    prob_win = pred.get("probability_win")
    if prob_win is None:
        prob_win = pred.get("probability")
    prob_loss = pred.get("probability_loss")
    if prob_win is not None:
        try:
            prob_win = float(prob_win)
            if prob_win > 1:
                prob_win = prob_win / 100.0
        except (TypeError, ValueError):
            prob_win = None
    if prob_loss is None and prob_win is not None:
        prob_loss = round(1.0 - prob_win, 4)

    llm_conf = llm.get("confidence")
    if llm_conf is not None:
        try:
            llm_conf = float(llm_conf)
            if llm_conf > 1:
                llm_conf = llm_conf / 100.0
        except (TypeError, ValueError):
            llm_conf = None

    return {
        "platform_confidence": platform_conf,
        "prediction_probability": {
            "win": prob_win,
            "loss": prob_loss,
        },
        "llm_confidence": llm_conf,
        "labels": {
            "platform": "platform_confidence",
            "prediction": "statistical_probability",
            "llm": "llm_review_confidence",
        },
    }
