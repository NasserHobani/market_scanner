# -*- coding: utf-8 -*-
"""Intelligence engine — orchestrates the full discovery pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .edge_monitor import EdgeMonitor, EdgeMonitorReport
from .historical_statistics import HistoricalStatistics, HistoricalStatisticsEngine, StatRow
from .insight import InsightEngine, InsightReport
from .knowledge_summary import KnowledgeSummary, KnowledgeSummaryEngine
from .market_memory import MarketMemory, MarketMemoryEngine
from .pattern_engine import PatternEngine, PatternReport
from .strategy_health import StrategyHealthEngine, StrategyHealthReport
from .trend_monitor import TrendMonitor, TrendMonitorReport


@dataclass
class IntelligenceReport:
    """Full intelligence pipeline output."""

    strategy_id: str = "default"
    patterns: PatternReport = field(default_factory=PatternReport)
    edge: EdgeMonitorReport = field(default_factory=EdgeMonitorReport)
    trend: TrendMonitorReport = field(default_factory=TrendMonitorReport)
    market_memory: MarketMemory = field(default_factory=MarketMemory)
    strategy_health: StrategyHealthReport = field(default_factory=StrategyHealthReport)
    historical_statistics: HistoricalStatistics = field(default_factory=HistoricalStatistics)
    knowledge_summary: KnowledgeSummary = field(default_factory=lambda: KnowledgeSummary(0, 0, None, None))
    insights: InsightReport = field(default_factory=InsightReport)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "generated_at": self.generated_at,
            "patterns": self.patterns.to_dict(),
            "edge": self.edge.to_dict(),
            "trend": self.trend.to_dict(),
            "market_memory": self.market_memory.to_dict(),
            "strategy_health": self.strategy_health.to_dict(),
            "historical_statistics": self.historical_statistics.to_dict(),
            "knowledge_summary": self.knowledge_summary.to_dict(),
            "insights": self.insights.to_dict(),
        }


class IntelligenceEngine:
    """Orchestrate pattern discovery, edge monitoring, and insight generation."""

    def __init__(self) -> None:
        self.patterns = PatternEngine()
        self.edge = EdgeMonitor()
        self.trend = TrendMonitor()
        self.memory = MarketMemoryEngine()
        self.health = StrategyHealthEngine()
        self.statistics = HistoricalStatisticsEngine()
        self.summary = KnowledgeSummaryEngine()
        self.insights = InsightEngine()

    def run(self, rows: Iterable[dict], *,
            strategy_id: str = "default",
            summary_window: int | None = None) -> IntelligenceReport:
        rows = list(rows)
        pattern_report = self.patterns.discover(rows)
        edge_report = self.edge.analyze(rows)
        trend_report = self.trend.analyze(rows)
        memory = self.memory.build(rows)
        health_report = self.health.assess(
            rows,
            pattern_count=len(pattern_report.patterns),
            market_memory_count=len(memory.records),
        )
        stat_rows = [
            StatRow(
                key=p.pattern_id, label=p.label, trade_count=p.trade_count,
                win_rate=p.win_rate, expectancy=p.expectancy,
                profit_factor=p.profit_factor, total_r=p.total_r,
            )
            for p in pattern_report.patterns
        ]
        stats = self.statistics.generate(rows, pattern_rows=stat_rows)
        knowledge_summary = self.summary.summarize(rows, window=summary_window)
        insight_report = self.insights.build(
            patterns=pattern_report,
            edge=edge_report,
            health=health_report,
            statistics=stats,
            summary=knowledge_summary,
            strategy_id=strategy_id,
        )

        return IntelligenceReport(
            strategy_id=strategy_id,
            patterns=pattern_report,
            edge=edge_report,
            trend=trend_report,
            market_memory=memory,
            strategy_health=health_report,
            historical_statistics=stats,
            knowledge_summary=knowledge_summary,
            insights=insight_report,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
