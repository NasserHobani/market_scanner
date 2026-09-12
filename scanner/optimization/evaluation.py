# -*- coding: utf-8 -*-
"""Evaluate parameter sets against trade rows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from scanner.research.metrics import MetricsEngine
from scanner.tracking import LOST, WON


GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


def _parse_time(row: dict) -> datetime | None:
    for key in ("closed_at", "signal_at", "opened_at"):
        val = row.get(key)
        if val is None:
            continue
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
    return None


def sort_rows_by_time(rows: list[dict]) -> list[dict]:
    """Sort trade rows chronologically — no look-ahead."""
    indexed = [(i, _parse_time(r), r) for i, r in enumerate(rows)]
    indexed.sort(key=lambda x: (x[1] is None, x[1] or datetime.min, x[0]))
    return [r for _, _, r in indexed]


def apply_parameters(rows: list[dict], params: dict[str, Any]) -> list[dict]:
    """Filter trade rows according to strategy parameters."""
    filtered = list(rows)

    min_score = params.get("min_score")
    if min_score is not None:
        filtered = [r for r in filtered
                      if r.get("score") is not None and float(r["score"]) >= float(min_score)]

    min_confidence = params.get("min_confidence")
    if min_confidence is not None:
        filtered = [r for r in filtered
                    if r.get("confidence") is not None
                    and float(r["confidence"]) >= float(min_confidence)]

    require_htf = params.get("require_htf")
    if require_htf:
        filtered = [r for r in filtered if "htf" in (r.get("factors") or [])]

    min_grade = params.get("min_grade")
    if min_grade:
        threshold = GRADE_ORDER.get(str(min_grade).upper(), 0)
        filtered = [r for r in filtered
                    if GRADE_ORDER.get(str(r.get("grade", "")).upper(), 0) >= threshold]

    market = params.get("market")
    if market:
        filtered = [r for r in filtered if r.get("market") == market]

    timeframe = params.get("timeframe")
    if timeframe:
        filtered = [r for r in filtered if r.get("timeframe") == timeframe]

    min_r = params.get("min_r_multiple")
    if min_r is not None:
        filtered = [r for r in filtered
                    if r.get("status") not in (WON, LOST)
                    or (r.get("r_multiple") is not None and float(r["r_multiple"]) >= float(min_r))]

    return filtered


class ParameterEvaluator:
    """Rank parameter sets using deterministic metrics."""

    def __init__(self, metrics: MetricsEngine | None = None) -> None:
        self._metrics = metrics or MetricsEngine()

    def evaluate(self, rows: list[dict], params: dict[str, Any]) -> dict[str, Any]:
        filtered = apply_parameters(rows, params)
        metrics = self._metrics.compute(filtered)
        closed = [r for r in filtered if r.get("status") in (WON, LOST)]
        return {
            "params": dict(params),
            "trade_count": metrics.get("trade_count", 0),
            "closed_trades": metrics.get("closed_trades", 0),
            "win_rate": metrics.get("win_rate"),
            "expectancy": metrics.get("expectancy"),
            "profit_factor": metrics.get("profit_factor"),
            "avg_r": metrics.get("avg_r"),
            "median_r": metrics.get("median_r"),
            "max_drawdown_r": metrics.get("max_drawdown_r"),
            "sharpe": metrics.get("sharpe"),
            "recovery_factor": metrics.get("recovery_factor"),
            "reliable": metrics.get("reliable", False),
            "oos_performance": None,
            "filtered_count": len(filtered),
            "closed_sample": len(closed),
        }

    def evaluate_oos(self, train_rows: list[dict], test_rows: list[dict],
                     params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate in-sample and out-of-sample without look-ahead."""
        is_result = self.evaluate(train_rows, params)
        oos_result = self.evaluate(test_rows, params)
        is_result["oos_performance"] = {
            "trade_count": oos_result.get("trade_count"),
            "closed_trades": oos_result.get("closed_trades"),
            "win_rate": oos_result.get("win_rate"),
            "expectancy": oos_result.get("expectancy"),
            "profit_factor": oos_result.get("profit_factor"),
            "avg_r": oos_result.get("avg_r"),
            "max_drawdown_r": oos_result.get("max_drawdown_r"),
            "reliable": oos_result.get("reliable"),
        }
        return is_result
