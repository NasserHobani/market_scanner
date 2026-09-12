# -*- coding: utf-8 -*-
"""Insight primitives — structured discoveries for future AI."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InsightImportance(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InsightCategory(str, Enum):
    PATTERN = "pattern"
    EDGE = "edge"
    HEALTH = "health"
    MARKET = "market"
    STATISTIC = "statistic"
    SUMMARY = "summary"


@dataclass
class Insight:
    """Structured intelligence output — no natural language generation."""

    insight_id: str
    title: str
    description: str
    category: str
    importance: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    affected_strategy: str = "default"
    supporting_statistics: dict[str, Any] = field(default_factory=dict)
    trace: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "importance": self.importance,
            "confidence": round(self.confidence, 4),
            "evidence": list(self.evidence),
            "affected_strategy": self.affected_strategy,
            "supporting_statistics": dict(self.supporting_statistics),
            "trace": self.trace,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Insight:
        return cls(
            insight_id=row["insight_id"],
            title=row["title"],
            description=row["description"],
            category=row.get("category") or InsightCategory.STATISTIC.value,
            importance=row.get("importance") or InsightImportance.MEDIUM.value,
            confidence=float(row.get("confidence") or 0.0),
            evidence=list(row.get("evidence") or []),
            affected_strategy=row.get("affected_strategy") or "default",
            supporting_statistics=dict(row.get("supporting_statistics") or {}),
            trace=row.get("trace") or "",
        )


@dataclass
class InsightReport:
    items: list[Insight] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.items),
            "generated_at": self.generated_at,
            "items": [i.to_dict() for i in self.items],
        }

    def by_category(self, category: str) -> list[Insight]:
        return [i for i in self.items if i.category == category]

    def by_importance(self, importance: str) -> list[Insight]:
        return [i for i in self.items if i.importance == importance]


# ── Insight Engine (Part 7) ──────────────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402

from .edge_monitor import EdgeMonitorReport  # noqa: E402
from .historical_statistics import HistoricalStatistics  # noqa: E402
from .knowledge_summary import KnowledgeSummary  # noqa: E402
from .pattern_engine import PatternReport  # noqa: E402
from .strategy_health import StrategyHealthReport  # noqa: E402


def _importance_rank(importance: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(importance, 0)


class InsightEngine:
    """Build Insight objects from intelligence artifacts — no NLG."""

    def build(self, *,
                patterns: PatternReport,
                edge: EdgeMonitorReport,
                health: StrategyHealthReport,
                statistics: HistoricalStatistics,
                summary: KnowledgeSummary,
                strategy_id: str = "default") -> InsightReport:
        items: list[Insight] = []
        items.extend(self._from_patterns(patterns, strategy_id))
        items.extend(self._from_edge(edge, strategy_id))
        items.extend(self._from_health(health, strategy_id))
        items.extend(self._from_statistics(statistics, strategy_id))
        items.extend(self._from_summary(summary, strategy_id))
        items.sort(key=lambda i: (_importance_rank(i.importance), i.confidence), reverse=True)
        return InsightReport(
            items=items,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _from_patterns(self, report: PatternReport,
                       strategy_id: str) -> list[Insight]:
        insights: list[Insight] = []
        for p in report.top(5):
            if p.expectancy is None or p.expectancy <= 0:
                continue
            wr = p.success_rate or 0
            insights.append(Insight(
                insight_id=f"ins_{p.pattern_id}",
                title=f"Pattern: {p.label}",
                description=f"Recurring combination with {wr}% success over {p.trade_count} trades",
                category=InsightCategory.PATTERN.value,
                importance=(InsightImportance.HIGH.value if wr >= 60
                            else InsightImportance.MEDIUM.value),
                confidence=min(0.95, 0.3 + p.trade_count / 50),
                evidence=[f"factors={'+'.join(p.factors)}", f"expectancy={p.expectancy}R"],
                affected_strategy=strategy_id,
                supporting_statistics=p.to_dict(),
                trace="pattern_engine.discover",
            ))
        return insights

    def _from_edge(self, report: EdgeMonitorReport,
                   strategy_id: str) -> list[Insight]:
        insights: list[Insight] = []
        for alert in report.alerts:
            insights.append(Insight(
                insight_id=f"ins_{alert.alert_id}",
                title=f"Edge Alert: {alert.metric}",
                description=alert.message,
                category=InsightCategory.EDGE.value,
                importance=alert.level if alert.level in ("critical", "high", "medium", "low")
                else InsightImportance.MEDIUM.value,
                confidence=0.75,
                evidence=[alert.trace],
                affected_strategy=strategy_id,
                supporting_statistics=alert.to_dict(),
                trace="edge_monitor.analyze",
            ))
        return insights

    def _from_health(self, health: StrategyHealthReport,
                     strategy_id: str) -> list[Insight]:
        if health.closed_trades == 0 or health.overall_health_score >= 70:
            return []
        return [Insight(
            insight_id="ins_strategy_health",
            title=f"Strategy Health: {health.label}",
            description=f"Overall health score {health.overall_health_score:.0f}/100",
            category=InsightCategory.HEALTH.value,
            importance=(InsightImportance.CRITICAL.value if health.overall_health_score < 45
                          else InsightImportance.HIGH.value),
            confidence=health.confidence_score / 100,
            evidence=[f"stability={health.stability_score}",
                      f"sample_quality={health.sample_quality}"],
            affected_strategy=strategy_id,
            supporting_statistics=health.to_dict(),
            trace="strategy_health.assess",
        )]

    def _from_statistics(self, stats: HistoricalStatistics,
                       strategy_id: str) -> list[Insight]:
        insights: list[Insight] = []
        if stats.best_timeframes:
            best = stats.best_timeframes[0]
            insights.append(Insight(
                insight_id="ins_best_timeframe",
                title=f"Best Timeframe: {best.label}",
                description=f"Expectancy {best.expectancy}R over {best.trade_count} trades",
                category=InsightCategory.STATISTIC.value,
                importance=InsightImportance.MEDIUM.value,
                confidence=min(0.9, 0.4 + best.trade_count / 40),
                evidence=[f"timeframe={best.key}"],
                affected_strategy=strategy_id,
                supporting_statistics=best.to_dict(),
                trace="historical_statistics.best_timeframes",
            ))
        if stats.worst_timeframes:
            worst = stats.worst_timeframes[0]
            if (worst.expectancy or 0) < 0:
                insights.append(Insight(
                    insight_id="ins_worst_timeframe",
                    title=f"Worst Timeframe: {worst.label}",
                    description=f"Expectancy {worst.expectancy}R over {worst.trade_count} trades",
                    category=InsightCategory.STATISTIC.value,
                    importance=InsightImportance.HIGH.value,
                    confidence=min(0.9, 0.4 + worst.trade_count / 40),
                    evidence=[f"timeframe={worst.key}"],
                    affected_strategy=strategy_id,
                    supporting_statistics=worst.to_dict(),
                    trace="historical_statistics.worst_timeframes",
                ))
        return insights

    def _from_summary(self, summary: KnowledgeSummary,
                      strategy_id: str) -> list[Insight]:
        if not summary.top_factor:
            return []
        top = next((f for f in summary.factor_importance if f.factor == summary.top_factor), None)
        if not top:
            return []
        return [Insight(
            insight_id="ins_top_factor",
            title=f"Dominant Factor: {top.label}",
            description=f"Highest importance score {top.importance_score:.3f} over {summary.closed_trades} trades",
            category=InsightCategory.SUMMARY.value,
            importance=InsightImportance.MEDIUM.value,
            confidence=min(0.85, 0.3 + summary.closed_trades / 60),
            evidence=[f"marginal_delta={top.marginal_delta}"],
            affected_strategy=strategy_id,
            supporting_statistics=summary.to_dict(),
            trace="knowledge_summary.summarize",
        )]
