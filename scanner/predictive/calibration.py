# -*- coding: utf-8 -*-
"""Prediction calibration analysis."""
from __future__ import annotations

import statistics
from typing import Any

CALIBRATION_BUCKETS = [
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.80),
    (0.80, 0.90),
    (0.90, 1.01),
]


def brier_score(y_true: list[int], y_proba: list[float]) -> float:
    if not y_true:
        return 0.0
    return round(sum((p - t) ** 2 for p, t in zip(y_proba, y_true)) / len(y_true), 4)


def calibration_report(y_true: list[int], y_proba: list[float], *,
                       min_bucket_samples: int = 5) -> dict[str, Any]:
    buckets = []
    for lo, hi in CALIBRATION_BUCKETS:
        indices = [i for i, p in enumerate(y_proba) if lo <= p < hi]
        if not indices:
            buckets.append({
                "range": f"{int(lo*100)}-{int(hi*100)}",
                "predicted_mid": round((lo + hi) / 2, 2),
                "actual_rate": None,
                "sample_size": 0,
            })
            continue
        actual = sum(y_true[i] for i in indices) / len(indices)
        buckets.append({
            "range": f"{int(lo*100)}-{int(hi*100)}",
            "predicted_mid": round((lo + hi) / 2, 2),
            "actual_rate": round(actual, 4),
            "sample_size": len(indices),
            "calibration_error": round(abs(actual - (lo + hi) / 2), 4),
        })

    populated = [b for b in buckets if b["sample_size"] >= min_bucket_samples]
    max_err = max((b.get("calibration_error") or 0) for b in populated) if populated else 1.0
    mean_err = (
        statistics.mean(b["calibration_error"] for b in populated)
        if populated else 1.0
    )

    if len(populated) < 2:
        status = "INSUFFICIENT_SAMPLE"
    elif mean_err <= 0.10:
        status = "GOOD"
    elif mean_err <= 0.20:
        status = "ACCEPTABLE"
    else:
        status = "CALIBRATION_FAILED"

    return {
        "buckets": buckets,
        "brier_score": brier_score(y_true, y_proba),
        "mean_calibration_error": round(mean_err, 4),
        "max_calibration_error": round(max_err, 4),
        "calibration_status": status,
        "trustworthy": status in ("GOOD", "ACCEPTABLE"),
    }
