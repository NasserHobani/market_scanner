# -*- coding: utf-8 -*-
"""Reusable deterministic research metrics."""
from __future__ import annotations

import statistics
from typing import Any, Iterable

from scanner.tracking import LOST, WON, summarize


class MetricsEngine:
    """Compute explainable metrics from trade rows."""

    def compute(self, rows: Iterable[dict]) -> dict[str, Any]:
        rows = list(rows)
        stats = summarize(rows)
        closed = [r for r in rows if r.get("status") in (WON, LOST)]
        rs = [float(r["r_multiple"]) for r in closed
              if r.get("r_multiple") is not None]

        median_r = round(statistics.median(rs), 3) if rs else None

        return {
            "trade_count": len(rows),
            "closed_trades": stats.get("closed") or 0,
            "wins": stats.get("wins") or 0,
            "losses": stats.get("losses") or 0,
            "win_rate": stats.get("win_rate"),
            "expectancy": stats.get("expectancy"),
            "profit_factor": stats.get("profit_factor"),
            "avg_r": stats.get("avg_r"),
            "median_r": median_r,
            "total_r": stats.get("total_r"),
            "avg_win_r": stats.get("avg_win_r"),
            "avg_loss_r": stats.get("avg_loss_r"),
            "max_drawdown_r": stats.get("max_drawdown_r"),
            "sharpe": stats.get("sharpe"),
            "recovery_factor": stats.get("recovery_factor"),
            "consistency_score": stats.get("consistency_score"),
            "stdev_r": stats.get("stdev_r"),
            "reliable": bool(stats.get("reliable")),
            "win_rate_low": stats.get("win_rate_low"),
            "win_rate_high": stats.get("win_rate_high"),
        }

    def compute_many(self, groups: dict[str, list[dict]]) -> dict[str, dict[str, Any]]:
        return {label: self.compute(rows) for label, rows in groups.items()}
