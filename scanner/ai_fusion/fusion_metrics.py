# -*- coding: utf-8 -*-
"""Fusion and prediction metrics from history + evaluations."""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from .fusion_history import FusionHistory

EARLY_SIGNAL_MIN = 10


def _accuracy(correct: list[bool | None]) -> float | None:
    vals = [c for c in correct if c is not None]
    if not vals:
        return None
    return round(sum(1 for c in vals if c) / len(vals), 4)


def compute_metrics(*,
                    history: list[dict[str, Any]] | None = None,
                    evaluations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    hist = history if history is not None else FusionHistory().list_all()
    evals = evaluations or []

    n = len(hist)
    status = "EARLY_SIGNAL" if n < EARLY_SIGNAL_MIN else "MEASURED"

    pred_available = sum(1 for h in hist if h.get("prediction_available"))
    states = Counter(h.get("fusion_state") for h in hist)
    conflicts = sum(
        1 for h in hist
        if str(h.get("fusion_state", "")).upper() in (
            "LLM_CONFLICT", "PREDICTION_CONFLICT", "STATISTICAL_CONFLICT", "MIXED"
        )
    )

    claude_rows = [h for h in hist if h.get("provider") == "claude"]
    qwen_rows = [h for h in hist if h.get("provider") in ("ollama", "qwen")]

    pred_correct = [e.get("prediction", {}).get("correct") for e in evals]
    llm_correct = [e.get("llm", {}).get("correct") for e in evals]
    platform_correct = [e.get("platform", {}).get("correct") for e in evals]
    fusion_useful = [e.get("fusion", {}).get("useful") for e in evals]

    claude_cost = sum(float(h.get("estimated_cost") or 0) for h in claude_rows)
    qwen_cost = sum(float(h.get("estimated_cost") or 0) for h in qwen_rows)
    escalations = sum(1 for h in hist if h.get("escalated"))

    return {
        "status": status,
        "sample_size": n,
        "evaluation_samples": len(evals),
        "prediction_availability_rate": round(pred_available / n, 4) if n else 0,
        "fusion_state_distribution": dict(states),
        "conflict_rate": round(conflicts / n, 4) if n else 0,
        "llm_agreement_rate": round(
            sum(1 for h in hist if str(h.get("llm_agreement", "")).lower() == "agree") / n, 4
        ) if n else 0,
        "platform_accuracy": _accuracy(platform_correct),
        "prediction_accuracy": _accuracy(pred_correct),
        "llm_accuracy": _accuracy(llm_correct),
        "fusion_accuracy": _accuracy(fusion_useful),
        "claude": {
            "reviews": len(claude_rows),
            "accuracy": None,
            "estimated_cost": round(claude_cost, 4),
        },
        "qwen": {
            "reviews": len(qwen_rows),
            "accuracy": None,
            "estimated_cost": round(qwen_cost, 4),
        },
        "cost": {
            "claude_escalations": escalations,
            "claude_avoided": max(0, len(qwen_rows) - escalations),
            "avg_cost_per_review": round(
                (claude_cost + qwen_cost) / n, 6
            ) if n else 0,
        },
    }


def calibration_buckets(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    rows = []
    for lo, hi in buckets:
        matching = [
            e for e in evaluations
            if e.get("prediction", {}).get("available")
            and lo <= float(e["prediction"].get("probability_win") or 0) < hi
        ]
        if not matching:
            rows.append({"range": f"{int(lo*100)}-{int(hi*100)}", "predictions": 0})
            continue
        expected = sum(float(e["prediction"]["probability_win"]) for e in matching)
        actual = sum(1 for e in matching if e["prediction"].get("correct"))
        rows.append({
            "range": f"{int(lo*100)}-{int(hi*100)}",
            "predictions": len(matching),
            "expected_wins": round(expected, 2),
            "actual_wins": actual,
            "calibration_error": round(abs(actual - expected) / len(matching), 4) if matching else None,
        })
    return rows
