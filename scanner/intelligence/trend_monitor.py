# -*- coding: utf-8 -*-
"""Trend performance monitor — rolling outcome trends by category."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from scanner.tracking import summarize

from ._helpers import closed_trades, sort_by_time, win_rate


@dataclass
class TrendPoint:
    index: int
    trade_count: int
    expectancy: float | None
    win_rate: float | None
    total_r: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "trade_count": self.trade_count,
            "expectancy": self.expectancy,
            "win_rate": self.win_rate,
            "total_r": self.total_r,
        }


@dataclass
class TrendMonitorReport:
    bucket_size: int
    points: list[TrendPoint] = field(default_factory=list)
    direction: str = "flat"
    slope: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket_size": self.bucket_size,
            "direction": self.direction,
            "slope": self.slope,
            "points": [p.to_dict() for p in self.points],
        }


class TrendMonitor:
    """Track how strategy performance trends over sequential trade buckets."""

    def __init__(self, *, bucket_size: int = 10) -> None:
        self.bucket_size = bucket_size

    def analyze(self, rows: Iterable[dict]) -> TrendMonitorReport:
        closed = sort_by_time(closed_trades(rows))
        report = TrendMonitorReport(bucket_size=self.bucket_size)

        for i, start in enumerate(range(0, len(closed), self.bucket_size)):
            chunk = closed[start:start + self.bucket_size]
            if not chunk:
                continue
            stats = summarize(chunk)
            report.points.append(TrendPoint(
                index=i + 1,
                trade_count=len(chunk),
                expectancy=stats.get("expectancy"),
                win_rate=win_rate(chunk),
                total_r=stats.get("total_r"),
            ))

        exps = [p.expectancy for p in report.points if p.expectancy is not None]
        if len(exps) >= 2:
            report.slope = round(exps[-1] - exps[0], 4)
            if report.slope > 0.05:
                report.direction = "improving"
            elif report.slope < -0.05:
                report.direction = "degrading"
            else:
                report.direction = "flat"

        return report
