# -*- coding: utf-8 -*-
"""Intelligence service — high-level API."""
from __future__ import annotations

from typing import Any, Iterable

from .insight import InsightReport
from .intelligence_engine import IntelligenceEngine, IntelligenceReport


class IntelligenceService:
    """Discover knowledge from historical trade rows — read-only analytics."""

    def __init__(self) -> None:
        self._engine = IntelligenceEngine()

    def analyze(self, rows: Iterable[dict], *,
                strategy_id: str = "default",
                summary_window: int | None = None) -> dict[str, Any]:
        report = self._engine.run(rows, strategy_id=strategy_id, summary_window=summary_window)
        return report.to_dict()

    def analyze_report(self, rows: Iterable[dict], *,
                       strategy_id: str = "default",
                       summary_window: int | None = None) -> IntelligenceReport:
        return self._engine.run(rows, strategy_id=strategy_id, summary_window=summary_window)

    def discover_patterns(self, rows: Iterable[dict]) -> dict[str, Any]:
        return self._engine.patterns.discover(rows).to_dict()

    def monitor_edge(self, rows: Iterable[dict]) -> dict[str, Any]:
        return self._engine.edge.analyze(rows).to_dict()

    def assess_health(self, rows: Iterable[dict]) -> dict[str, Any]:
        return self._engine.health.assess(list(rows)).to_dict()

    def generate_insights(self, rows: Iterable[dict], *,
                          strategy_id: str = "default") -> InsightReport:
        return self._engine.run(rows, strategy_id=strategy_id).insights
