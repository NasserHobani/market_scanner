# -*- coding: utf-8 -*-
"""Confidence intervals and significance for research metrics."""
from __future__ import annotations

import math
import random
from typing import Iterable


def bootstrap_ci(values: list[float], *, n_resamples: int = 2000,
                 alpha: float = 0.05, seed: int = 42) -> dict:
    """Bootstrap CI for mean R (expectancy)."""
    if not values:
        return {"low": None, "high": None, "se": None, "method": "bootstrap"}
    if len(values) == 1:
        v = values[0]
        return {"low": round(v, 3), "high": round(v, 3), "se": 0.0, "method": "bootstrap"}
    rnd = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        sample = [values[rnd.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    mean = sum(values) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in values) / n) / math.sqrt(n)
    return {
        "low": round(means[lo_idx], 3),
        "high": round(means[hi_idx], 3),
        "se": round(se, 3),
        "method": "bootstrap",
    }


def p_value_vs_zero(values: list[float], *, n_perm: int = 5000, seed: int = 42) -> float | None:
    """Two-sided permutation p-value: H0 mean = 0."""
    if len(values) < 3:
        return None
    observed = sum(values) / len(values)
    rnd = random.Random(seed)
    count = 0
    for _ in range(n_perm):
        flipped = [x if rnd.random() > 0.5 else -x for x in values]
        if abs(sum(flipped) / len(flipped)) >= abs(observed):
            count += 1
    return round(count / n_perm, 4)


def confidence_report(rows: Iterable[dict], independent_events: int) -> dict:
    """Full confidence panel for closed trades."""
    from scanner.tracking import WON, LOST, summarize, wilson

    rows = list(rows)
    closed = [r for r in rows if r.get("status") in (WON, LOST)]
    all_r = [float(r["r_multiple"]) for r in closed if r.get("r_multiple") is not None]
    s = summarize(rows)
    n = len(all_r)
    wins = sum(1 for r in closed if r.get("status") == WON)
    ci = bootstrap_ci(all_r)
    pval = p_value_vs_zero(all_r)
    warnings: list[str] = []
    if n < 20:
        warnings.append(f"عيّنة صغيرة: {n} صفقة محسومة (الحد الأدنى 20)")
    if independent_events < 10:
        warnings.append(f"أحداث مستقلة قليلة: {independent_events} (الحد الأدنى 10)")
    if s.get("win_rate_high") and s.get("win_rate_low"):
        width = s["win_rate_high"] - s["win_rate_low"]
        if width > 25:
            warnings.append(f"مجال ويلسون واسع: {width:.0f} نقطة مئوية")
    significant = pval is not None and pval < 0.05 and (s.get("expectancy") or 0) > 0
    return {
        "expectancy": s.get("expectancy"),
        "expectancy_ci_low": ci["low"],
        "expectancy_ci_high": ci["high"],
        "expectancy_se": ci["se"],
        "win_rate": s.get("win_rate"),
        "win_rate_low": s.get("win_rate_low"),
        "win_rate_high": s.get("win_rate_high"),
        "sample_size": n,
        "independent_events": independent_events,
        "p_value_vs_zero": pval,
        "significant": significant,
        "reliable": s.get("reliable"),
        "warnings": warnings,
    }
