# -*- coding: utf-8 -*-
"""Evaluate near-term outlook separately from entry recommendation — AIA-13."""
from __future__ import annotations

from typing import Any

from .normalize import extract_analyst_fields, _norm_dir


def _outcome_direction(trade_result: dict[str, Any]) -> str:
    """Map closed trade outcome to a coarse direction for outlook scoring."""
    explicit = trade_result.get("outlook_realized") or trade_result.get("realized_direction")
    if explicit:
        return _norm_dir(explicit)
    r = trade_result.get("r_multiple")
    status = str(trade_result.get("status") or "").lower()
    side = str(trade_result.get("side") or trade_result.get("direction") or "buy").lower()
    won = status in ("won", "win") or (r is not None and float(r) > 0)
    lost = status in ("lost", "loss") or (r is not None and float(r) < 0)
    long_side = side in ("buy", "long")
    if won:
        return "bullish" if long_side else "bearish"
    if lost:
        return "bearish" if long_side else "bullish"
    return "unclear"


def evaluate_outlook(response: dict[str, Any] | None,
                     trade_result: dict[str, Any] | None) -> dict[str, Any]:
    """Compare advisor near-term outlook vs realized trade/market outcome.

    Separates:
    - recommendation_correct (handled elsewhere)
    - outlook_correct / direction_forecast_correct
    """
    trade_result = trade_result or {}
    analyst = extract_analyst_fields(response or {})
    outlook = analyst.get("near_term_outlook") or {}
    predicted = _norm_dir(outlook.get("direction"))
    realized = _outcome_direction(trade_result)

    outlook_correct: bool | None
    if predicted in ("unclear", "sideways") or realized == "unclear":
        outlook_correct = None  # not scoreable cleanly
    else:
        outlook_correct = predicted == realized

    conf = outlook.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None

    overconfident = False
    underconfident = False
    if outlook_correct is False and conf_f is not None and conf_f >= 75:
        overconfident = True
    if outlook_correct is True and conf_f is not None and conf_f <= 40:
        underconfident = True

    return {
        "outlook_direction_predicted": predicted,
        "outlook_direction_realized": realized,
        "outlook_horizon_days": outlook.get("horizon_days") or 7,
        "outlook_confidence": conf_f,
        "outlook_correct": outlook_correct,
        "direction_forecast_correct": outlook_correct,
        "outlook_overconfident": overconfident,
        "outlook_underconfident": underconfident,
        "advisor_action": (analyst.get("recommendation") or {}).get("action"),
        "market_view_direction": (analyst.get("current_market_view") or {}).get("direction"),
    }


def outlook_pattern_label(evaluation: dict[str, Any] | None) -> str:
    """Learning-friendly pattern tag — research validates; no auto-modify."""
    ev = evaluation or {}
    predicted = ev.get("outlook_direction_predicted") or "unclear"
    correct = ev.get("outlook_correct")
    if correct is True:
        if predicted == "bullish":
            return "correct_bullish_outlook"
        if predicted == "bearish":
            return "correct_bearish_outlook"
        return "correct_outlook"
    if correct is False:
        if predicted == "bullish":
            return "incorrect_bullish_outlook"
        if predicted == "bearish":
            return "incorrect_bearish_outlook"
        return "incorrect_outlook"
    if ev.get("outlook_overconfident"):
        return "overconfidence"
    if ev.get("outlook_underconfident"):
        return "underconfidence"
    if predicted == "sideways":
        return "sideways_outlook_unscored"
    return "outlook_unscored"
