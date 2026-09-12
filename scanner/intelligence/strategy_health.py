# -*- coding: utf-8 -*-
"""Strategy health scoring — transparent composite metrics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from scanner.tracking import summarize

from ._helpers import closed_trades
from .edge_monitor import EdgeMonitor


@dataclass
class StrategyHealthReport:
    overall_health_score: float = 0.0
    stability_score: float = 0.0
    consistency_score: float = 0.0
    confidence_score: float = 0.0
    sample_quality: float = 0.0
    data_quality: float = 0.0
    research_coverage: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    label: str = "unknown"
    closed_trades: int = 0
    reliable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_health_score": round(self.overall_health_score, 1),
            "stability_score": round(self.stability_score, 1),
            "consistency_score": round(self.consistency_score, 1),
            "confidence_score": round(self.confidence_score, 1),
            "sample_quality": round(self.sample_quality, 1),
            "data_quality": round(self.data_quality, 1),
            "research_coverage": round(self.research_coverage, 1),
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "label": self.label,
            "closed_trades": self.closed_trades,
            "reliable": self.reliable,
        }


def _clamp01(x: float) -> float:
    return max(0.0, min(100.0, x))


class StrategyHealthEngine:
    """Composite health from tracking stats + edge monitor — all components exposed."""

    def __init__(self, *, min_reliable: int = 20) -> None:
        self.min_reliable = min_reliable
        self.edge_monitor = EdgeMonitor()

    def assess(self, rows: Iterable[dict], *,
               pattern_count: int = 0,
               market_memory_count: int = 0) -> StrategyHealthReport:
        rows = list(rows)
        closed = closed_trades(rows)
        stats = summarize(rows)
        edge = self.edge_monitor.analyze(rows)
        n = len(closed)

        # Sample quality: 0-100 based on closed count
        sample_quality = _clamp01(n / self.min_reliable * 100) if n else 0.0

        # Data quality: fraction of closed rows with r_multiple + factors
        if closed:
            complete = sum(1 for r in closed
                           if r.get("r_multiple") is not None and r.get("factors") is not None)
            data_quality = _clamp01(complete / len(closed) * 100)
        else:
            data_quality = 0.0

        # Research coverage: patterns + memory buckets discovered
        research_coverage = _clamp01(min(100, (pattern_count + market_memory_count) * 10))

        exp = stats.get("expectancy") or 0.0
        pf = stats.get("profit_factor") or 0.0
        sharpe = stats.get("sharpe") or 0.0
        consistency = stats.get("consistency_score") or 0.0
        reliable = bool(stats.get("reliable"))

        stability = _clamp01((edge.edge_stability or 0.5) * 100)
        if edge.edge_decay is not None and edge.edge_decay < 0:
            stability = _clamp01(stability + edge.edge_decay * 100)

        consistency_score = _clamp01(float(consistency) if consistency else 50.0)

        confidence = _clamp01(
            sample_quality * 0.4
            + (50 + exp * 100) * 0.3
            + stability * 0.3
        )

        components = {
            "expectancy": _clamp01(50 + exp * 100),
            "profit_factor": _clamp01(min(100, (pf or 0) * 50)),
            "sharpe": _clamp01(min(100, (sharpe or 0) * 50 + 50)),
            "edge_stability": stability,
            "edge_decay_penalty": _clamp01(max(0, 100 + (edge.edge_decay or 0) * 100)),
            "sample_quality": sample_quality,
            "data_quality": data_quality,
        }

        overall = sum(components.values()) / len(components)

        if overall >= 70:
            label = "healthy"
        elif overall >= 45:
            label = "monitor"
        else:
            label = "weak"

        return StrategyHealthReport(
            overall_health_score=overall,
            stability_score=stability,
            consistency_score=consistency_score,
            confidence_score=confidence,
            sample_quality=sample_quality,
            data_quality=data_quality,
            research_coverage=research_coverage,
            components=components,
            label=label,
            closed_trades=n,
            reliable=reliable,
        )
