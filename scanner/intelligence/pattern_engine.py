# -*- coding: utf-8 -*-
"""Pattern discovery from historical trades — pure statistics."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Iterable

from scanner.tracking import summarize

from ._helpers import avg_r, closed_trades, combo_key, factor_set, win_rate


@dataclass
class PatternInsight:
    """Recurring factor combination with measured outcomes."""

    pattern_id: str
    factors: list[str]
    label: str
    trade_count: int
    win_rate: float | None
    success_rate: float | None
    expectancy: float | None
    avg_r: float | None
    profit_factor: float | None
    total_r: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "factors": list(self.factors),
            "label": self.label,
            "trade_count": self.trade_count,
            "win_rate": self.win_rate,
            "success_rate": self.success_rate,
            "expectancy": self.expectancy,
            "avg_r": self.avg_r,
            "profit_factor": self.profit_factor,
            "total_r": self.total_r,
        }


@dataclass
class PatternReport:
    patterns: list[PatternInsight] = field(default_factory=list)
    min_trades: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_trades": self.min_trades,
            "count": len(self.patterns),
            "patterns": [p.to_dict() for p in self.patterns],
        }

    def top(self, n: int = 10) -> list[PatternInsight]:
        return sorted(
            self.patterns,
            key=lambda p: (p.expectancy or -99, p.trade_count),
            reverse=True,
        )[:n]


_FACTOR_LABELS = {
    "htf": "Trend",
    "candles": "Candles",
    "pattern": "Pattern",
    "elliott": "Elliott",
    "confluence": "Confluence",
    "price_action": "PriceAction",
    "score": "Score",
    "sweep": "LiquiditySweep",
    "breakout": "Breakout",
}


def _human_label(factors: list[str]) -> str:
    return " + ".join(_FACTOR_LABELS.get(f, f) for f in factors)


class PatternEngine:
    """Discover recurring factor combinations — no prediction."""

    def __init__(self, *, min_trades: int = 3, max_combo_size: int = 3) -> None:
        self.min_trades = min_trades
        self.max_combo_size = max_combo_size

    def discover(self, rows: Iterable[dict]) -> PatternReport:
        closed = closed_trades(rows)
        if not closed:
            return PatternReport(min_trades=self.min_trades)

        all_factors: set[str] = set()
        for row in closed:
            all_factors.update(factor_set(row))

        buckets: dict[str, list[dict]] = {}
        for row in closed:
            fs = factor_set(row)
            if not fs:
                continue
            for size in range(1, min(self.max_combo_size, len(fs)) + 1):
                for combo in combinations(sorted(fs), size):
                    key = combo_key(frozenset(combo))
                    buckets.setdefault(key, []).append(row)

        patterns: list[PatternInsight] = []
        for key, bucket in buckets.items():
            if len(bucket) < self.min_trades:
                continue
            stats = summarize(bucket)
            factors = key.split("+") if key != "none" else []
            wr = win_rate(bucket)
            patterns.append(PatternInsight(
                pattern_id=f"pat_{key.replace('+', '_')}",
                factors=factors,
                label=_human_label(factors),
                trade_count=len(bucket),
                win_rate=wr,
                success_rate=wr,
                expectancy=stats.get("expectancy"),
                avg_r=avg_r(bucket),
                profit_factor=stats.get("profit_factor"),
                total_r=stats.get("total_r"),
            ))

        patterns.sort(key=lambda p: (p.expectancy or -99), reverse=True)
        return PatternReport(patterns=patterns, min_trades=self.min_trades)
