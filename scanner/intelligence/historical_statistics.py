# -*- coding: utf-8 -*-
"""Reusable historical statistics — rankings by dimension."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from scanner.tracking import summarize

from ._helpers import closed_trades, win_rate


@dataclass
class StatRow:
    key: str
    label: str
    trade_count: int
    win_rate: float | None
    expectancy: float | None
    profit_factor: float | None
    total_r: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "trade_count": self.trade_count,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "total_r": self.total_r,
        }


@dataclass
class HistoricalStatistics:
    top_patterns: list[StatRow] = field(default_factory=list)
    worst_patterns: list[StatRow] = field(default_factory=list)
    best_timeframes: list[StatRow] = field(default_factory=list)
    worst_timeframes: list[StatRow] = field(default_factory=list)
    best_markets: list[StatRow] = field(default_factory=list)
    worst_markets: list[StatRow] = field(default_factory=list)
    best_regimes: list[StatRow] = field(default_factory=list)
    worst_regimes: list[StatRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _rows(xs: list[StatRow]) -> list[dict]:
            return [x.to_dict() for x in xs]

        return {
            "top_patterns": _rows(self.top_patterns),
            "worst_patterns": _rows(self.worst_patterns),
            "best_timeframes": _rows(self.best_timeframes),
            "worst_timeframes": _rows(self.worst_timeframes),
            "best_markets": _rows(self.best_markets),
            "worst_markets": _rows(self.worst_markets),
            "best_regimes": _rows(self.best_regimes),
            "worst_regimes": _rows(self.worst_regimes),
        }


def _split_stats(rows: list[dict], key_fn: Callable[[dict], str],
                 *, min_n: int = 3) -> list[StatRow]:
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        k = key_fn(row) or "unknown"
        buckets.setdefault(k, []).append(row)

    out: list[StatRow] = []
    for key, bucket in buckets.items():
        if len(bucket) < min_n:
            continue
        stats = summarize(bucket)
        out.append(StatRow(
            key=key,
            label=key,
            trade_count=len(bucket),
            win_rate=win_rate(bucket),
            expectancy=stats.get("expectancy"),
            profit_factor=stats.get("profit_factor"),
            total_r=stats.get("total_r"),
        ))
    return out


def _rank(rows: list[StatRow], *, best: bool = True, limit: int = 5) -> list[StatRow]:
    return sorted(
        rows,
        key=lambda r: (r.expectancy if r.expectancy is not None else -99),
        reverse=best,
    )[:limit]


class HistoricalStatisticsEngine:
    """Generate reusable ranking statistics."""

    def __init__(self, *, min_trades: int = 3) -> None:
        self.min_trades = min_trades

    def generate(self, rows: Iterable[dict], *,
                 pattern_rows: list[StatRow] | None = None) -> HistoricalStatistics:
        closed = closed_trades(rows)

        patterns = pattern_rows or []
        if not patterns:
            from .pattern_engine import PatternEngine
            pat_report = PatternEngine(min_trades=self.min_trades).discover(closed)
            patterns = [
                StatRow(
                    key=p.pattern_id, label=p.label, trade_count=p.trade_count,
                    win_rate=p.win_rate, expectancy=p.expectancy,
                    profit_factor=p.profit_factor, total_r=p.total_r,
                )
                for p in pat_report.patterns
            ]

        tf_rows = _split_stats(closed, lambda r: r.get("timeframe") or "unknown",
                               min_n=self.min_trades)
        mkt_rows = _split_stats(closed, lambda r: r.get("market") or "unknown",
                                min_n=self.min_trades)
        regime_rows = _split_stats(
            closed,
            lambda r: f"{r.get('market','?')}:{r.get('grade','?')}",
            min_n=self.min_trades,
        )

        return HistoricalStatistics(
            top_patterns=_rank(patterns, best=True),
            worst_patterns=_rank(patterns, best=False),
            best_timeframes=_rank(tf_rows, best=True),
            worst_timeframes=_rank(tf_rows, best=False),
            best_markets=_rank(mkt_rows, best=True),
            worst_markets=_rank(mkt_rows, best=False),
            best_regimes=_rank(regime_rows, best=True),
            worst_regimes=_rank(regime_rows, best=False),
        )
