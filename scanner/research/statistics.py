# -*- coding: utf-8 -*-
"""Statistical helpers for research — deterministic, no ML."""
from __future__ import annotations

from typing import Any


def mean_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


def pct_change(a: float | None, b: float | None) -> float | None:
    """Percent change from baseline b to treatment a."""
    if a is None or b is None or b == 0:
        return None
    return round((a - b) / abs(b) * 100, 2)


def reliability_flag(n: int, *, min_n: int = 20) -> bool:
    return n >= min_n


def wilson_overlap(low_a: float | None, high_a: float | None,
                   low_b: float | None, high_b: float | None) -> bool | None:
    """Check if Wilson intervals overlap — simple significance proxy."""
    if None in (low_a, high_a, low_b, high_b):
        return None
    return not (high_a < low_b or high_b < low_a)


def summarize_differences(metrics_a: dict[str, Any],
                          metrics_b: dict[str, Any],
                          *, label_a: str = "A",
                          label_b: str = "B") -> dict[str, Any]:
    """Expose statistical differences between two metric sets."""
    diffs: dict[str, Any] = {}
    for key in ("expectancy", "win_rate", "profit_factor", "avg_r", "median_r",
                "max_drawdown_r", "sharpe", "recovery_factor"):
        va = metrics_a.get(key)
        vb = metrics_b.get(key)
        diffs[key] = {
            label_a: va,
            label_b: vb,
            "delta": mean_diff(va, vb) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None,
            "pct_change": pct_change(va, vb) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None,
        }

    n_a = metrics_a.get("closed_trades") or 0
    n_b = metrics_b.get("closed_trades") or 0
    wr_overlap = wilson_overlap(
        metrics_a.get("win_rate_low"), metrics_a.get("win_rate_high"),
        metrics_b.get("win_rate_low"), metrics_b.get("win_rate_high"),
    )

    return {
        "differences": diffs,
        "sample_sizes": {label_a: n_a, label_b: n_b},
        "both_reliable": reliability_flag(n_a) and reliability_flag(n_b),
        "win_rate_intervals_disjoint": (wr_overlap is False),
        "significance_note": (
            "Win rate intervals do not overlap — difference may be meaningful"
            if wr_overlap is False else
            "Win rate intervals overlap — difference not statistically distinguishable"
            if wr_overlap is True else
            "Insufficient data for interval comparison"
        ),
    }
