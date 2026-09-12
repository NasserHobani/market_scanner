# -*- coding: utf-8 -*-
"""Edge monitoring — rolling metrics and degradation detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from scanner.tracking import summarize

from ._helpers import closed_trades, sort_by_time, win_rate


@dataclass
class EdgeAlert:
    alert_id: str
    level: str
    metric: str
    message: str
    current_value: float | None
    baseline_value: float | None
    window: int
    trace: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "level": self.level,
            "metric": self.metric,
            "message": self.message,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "window": self.window,
            "trace": self.trace,
        }


@dataclass
class EdgeSnapshot:
    window: int
    trade_count: int
    expectancy: float | None
    profit_factor: float | None
    win_rate: float | None
    max_drawdown_r: float | None
    total_r: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "trade_count": self.trade_count,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "win_rate": self.win_rate,
            "max_drawdown_r": self.max_drawdown_r,
            "total_r": self.total_r,
        }


@dataclass
class EdgeMonitorReport:
    snapshots: list[EdgeSnapshot] = field(default_factory=list)
    edge_stability: float | None = None
    edge_decay: float | None = None
    alerts: list[EdgeAlert] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "edge_stability": self.edge_stability,
            "edge_decay": self.edge_decay,
            "alerts": [a.to_dict() for a in self.alerts],
        }


class EdgeMonitor:
    """Monitor strategy edge over rolling windows."""

    def __init__(self, *, windows: list[int] | None = None) -> None:
        self.windows = windows or [10, 20, 30, 50]

    def analyze(self, rows: Iterable[dict]) -> EdgeMonitorReport:
        closed = sort_by_time(closed_trades(rows))
        report = EdgeMonitorReport()

        for w in self.windows:
            if len(closed) < w:
                continue
            chunk = closed[-w:]
            stats = summarize(chunk)
            report.snapshots.append(EdgeSnapshot(
                window=w,
                trade_count=len(chunk),
                expectancy=stats.get("expectancy"),
                profit_factor=stats.get("profit_factor"),
                win_rate=win_rate(chunk),
                max_drawdown_r=stats.get("max_drawdown_r"),
                total_r=stats.get("total_r"),
            ))

        if len(report.snapshots) >= 2:
            recent = report.snapshots[-1]
            baseline = report.snapshots[0]
            r_exp = recent.expectancy
            b_exp = baseline.expectancy
            if r_exp is not None and b_exp is not None and b_exp != 0:
                report.edge_decay = round((r_exp - b_exp) / abs(b_exp), 4)
            pos = sum(1 for s in report.snapshots if (s.expectancy or 0) > 0)
            report.edge_stability = round(pos / len(report.snapshots), 4)

        report.alerts = self._alerts(closed, report)
        return report

    def _alerts(self, closed: list[dict], report: EdgeMonitorReport) -> list[EdgeAlert]:
        alerts: list[EdgeAlert] = []
        if not report.snapshots:
            return alerts

        latest = report.snapshots[-1]
        if latest.expectancy is not None and latest.expectancy < 0:
            alerts.append(EdgeAlert(
                alert_id="edge_neg_expectancy",
                level="critical",
                metric="expectancy",
                message="Rolling expectancy is negative",
                current_value=latest.expectancy,
                baseline_value=report.snapshots[0].expectancy if report.snapshots else None,
                window=latest.window,
                trace=f"last_{latest.window}_trades",
            ))

        if report.edge_decay is not None and report.edge_decay < -0.25:
            alerts.append(EdgeAlert(
                alert_id="edge_decay",
                level="high",
                metric="edge_decay",
                message="Edge decay detected — recent window underperforming baseline",
                current_value=report.edge_decay,
                baseline_value=0.0,
                window=latest.window,
                trace="snapshots[-1].expectancy vs snapshots[0].expectancy",
            ))

        if latest.win_rate is not None and latest.win_rate < 40:
            alerts.append(EdgeAlert(
                alert_id="edge_low_winrate",
                level="medium",
                metric="win_rate",
                message="Rolling win rate below 40%",
                current_value=latest.win_rate,
                baseline_value=None,
                window=latest.window,
                trace=f"win_rate last_{latest.window}",
            ))

        if latest.max_drawdown_r is not None and latest.max_drawdown_r > 15:
            alerts.append(EdgeAlert(
                alert_id="edge_high_drawdown",
                level="high",
                metric="max_drawdown_r",
                message="Rolling max drawdown exceeds 15R",
                current_value=latest.max_drawdown_r,
                baseline_value=None,
                window=latest.window,
                trace=f"max_drawdown_r last_{latest.window}",
            ))

        if report.edge_stability is not None and report.edge_stability < 0.5:
            alerts.append(EdgeAlert(
                alert_id="edge_unstable",
                level="medium",
                metric="edge_stability",
                message="Edge stability below 50% of windows positive",
                current_value=report.edge_stability,
                baseline_value=1.0,
                window=0,
                trace="positive_expectancy_windows / total_windows",
            ))

        return alerts
