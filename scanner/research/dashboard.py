# -*- coding: utf-8 -*-
"""Assemble full quant research dashboard payload."""
from __future__ import annotations

from typing import Iterable

from scanner.tracking import summarize

from .baselines_loader import baseline_comparison
from .confidence import confidence_report
from .contribution import factor_contributions
from .events import count_independent_events
from .experiments_loader import load_experiments
from .health import health_panel
from .trends import trends_payload


def build_dashboard(rows: Iterable[dict], *,
                    market: str = "",
                    timeframe: str = "") -> dict:
    rows = list(rows)
    overall = summarize(rows)
    indep = count_independent_events(rows)
    experiments, running = load_experiments()
    baselines = baseline_comparison(
        rows, market=market or "crypto", timeframe=timeframe or "4h")
    confidence = confidence_report(rows, indep)
    contributions = factor_contributions(rows)
    trends = trends_payload(rows)
    health = health_panel(
        overall, rows,
        running_experiments=running,
        baseline_pass=baselines.get("gate_pass", False),
    )
    return {
        "overall": overall,
        "health": health,
        "trends": trends,
        "experiments": experiments,
        "contributions": contributions,
        "confidence": confidence,
        "baselines": baselines,
        "independent_events": indep,
    }
