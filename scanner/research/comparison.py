# -*- coding: utf-8 -*-
"""Comparison engine — strategy, filter, market, timeframe, version."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scanner.research.metrics import MetricsEngine
from scanner.research.statistics import summarize_differences


@dataclass
class ComparisonResult:
    """Structured comparison between two research groups."""

    comparison_id: str
    comparison_type: str
    label_a: str
    label_b: str
    metrics_a: dict[str, Any] = field(default_factory=dict)
    metrics_b: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    winner: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "comparison_type": self.comparison_type,
            "label_a": self.label_a,
            "label_b": self.label_b,
            "metrics_a": self.metrics_a,
            "metrics_b": self.metrics_b,
            "statistics": self.statistics,
            "winner": self.winner,
            "notes": list(self.notes),
        }


class ComparisonEngine:
    """Compare research groups with statistical differences."""

    def __init__(self, metrics: MetricsEngine | None = None) -> None:
        self._metrics = metrics or MetricsEngine()

    def compare(self, rows_a: list[dict], rows_b: list[dict], *,
                label_a: str = "A",
                label_b: str = "B",
                comparison_type: str = "group_vs_group") -> ComparisonResult:
        ma = self._metrics.compute(rows_a)
        mb = self._metrics.compute(rows_b)
        stats = summarize_differences(ma, mb, label_a=label_a, label_b=label_b)
        winner = self._pick_winner(ma, mb, label_a, label_b)
        notes = self._build_notes(ma, mb, stats)

        return ComparisonResult(
            comparison_id=f"cmp_{label_a}_vs_{label_b}",
            comparison_type=comparison_type,
            label_a=label_a,
            label_b=label_b,
            metrics_a=ma,
            metrics_b=mb,
            statistics=stats,
            winner=winner,
            notes=notes,
        )

    def strategy_vs_strategy(self, rows_a: list[dict], rows_b: list[dict], *,
                             name_a: str, name_b: str) -> ComparisonResult:
        return self.compare(rows_a, rows_b, label_a=name_a, label_b=name_b,
                            comparison_type="strategy_vs_strategy")

    def filter_vs_filter(self, rows_a: list[dict], rows_b: list[dict], *,
                         filter_a: str, filter_b: str) -> ComparisonResult:
        return self.compare(rows_a, rows_b, label_a=filter_a, label_b=filter_b,
                            comparison_type="filter_vs_filter")

    def market_vs_market(self, rows_a: list[dict], rows_b: list[dict], *,
                         market_a: str, market_b: str) -> ComparisonResult:
        return self.compare(rows_a, rows_b, label_a=market_a, label_b=market_b,
                            comparison_type="market_vs_market")

    def timeframe_vs_timeframe(self, rows_a: list[dict], rows_b: list[dict], *,
                               tf_a: str, tf_b: str) -> ComparisonResult:
        return self.compare(rows_a, rows_b, label_a=tf_a, label_b=tf_b,
                            comparison_type="timeframe_vs_timeframe")

    def version_vs_version(self, rows_a: list[dict], rows_b: list[dict], *,
                           version_a: str, version_b: str) -> ComparisonResult:
        return self.compare(rows_a, rows_b, label_a=version_a, label_b=version_b,
                            comparison_type="version_vs_version")

    def _pick_winner(self, ma: dict, mb: dict,
                     label_a: str, label_b: str) -> str:
        exp_a = ma.get("expectancy")
        exp_b = mb.get("expectancy")
        if exp_a is None or exp_b is None:
            return "inconclusive"
        if exp_a > exp_b:
            return label_a
        if exp_b > exp_a:
            return label_b
        return "tie"

    def _build_notes(self, ma: dict, mb: dict,
                     stats: dict) -> list[str]:
        notes: list[str] = []
        if not stats.get("both_reliable"):
            notes.append("Sample size below reliability threshold (n<20)")
        notes.append(stats.get("significance_note") or "")
        if ma.get("reliable") and mb.get("reliable"):
            delta = stats.get("differences", {}).get("expectancy", {}).get("delta")
            if delta is not None:
                notes.append(f"Expectancy delta: {delta:+.3f}R")
        return [n for n in notes if n]
