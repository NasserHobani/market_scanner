# -*- coding: utf-8 -*-
"""System health score and KPI panel."""
from __future__ import annotations

from typing import Iterable


def _norm(value: float | None, lo: float, hi: float) -> float:
    if value is None:
        return 0.0
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def health_score(summary: dict, *, baseline_pass: bool = False) -> dict:
    """Composite 0-100 health score with decomposition."""
    exp = summary.get("expectancy") or 0.0
    pf = summary.get("profit_factor") or 0.0
    sharpe = summary.get("sharpe") or 0.0
    dd = summary.get("max_drawdown_r") or 0.0
    reliable = 1.0 if summary.get("reliable") else 0.0
    baseline = 1.0 if baseline_pass else 0.0

    parts = {
        "expectancy": round(35 * _norm(exp, 0.0, 0.5), 1),
        "profit_factor": round(20 * _norm(pf, 1.0, 2.0), 1),
        "sharpe": round(15 * _norm(sharpe, 0.0, 1.5), 1),
        "drawdown": round(15 * (1 - _norm(dd, 0.0, 20.0)), 1),
        "reliability": round(10 * reliable, 1),
        "baseline": round(5 * baseline, 1),
    }
    score = round(sum(parts.values()))
    if score >= 70:
        label = "صحي"
    elif score >= 45:
        label = "مراقَب"
    else:
        label = "ضعيف"
    return {"score": score, "label": label, "parts": parts}


def health_panel(summary: dict, rows: Iterable[dict], *,
                 running_experiments: int = 0,
                 baseline_pass: bool = False) -> dict:
    rows = list(rows)
    hs = health_score(summary, baseline_pass=baseline_pass)
    return {
        "health_score": hs["score"],
        "health_label": hs["label"],
        "health_parts": hs["parts"],
        "expectancy": summary.get("expectancy"),
        "profit_factor": summary.get("profit_factor"),
        "avg_r": summary.get("avg_r"),
        "max_drawdown_r": summary.get("max_drawdown_r"),
        "sharpe": summary.get("sharpe"),
        "recovery_factor": summary.get("recovery_factor"),
        "open_trades": summary.get("open"),
        "pending_trades": summary.get("pending"),
        "paper_trades": summary.get("total"),
        "closed_trades": summary.get("closed"),
        "running_experiments": running_experiments,
        "consistency_score": summary.get("consistency_score"),
    }
