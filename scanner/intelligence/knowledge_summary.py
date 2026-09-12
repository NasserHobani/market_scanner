# -*- coding: utf-8 -*-
"""Structured knowledge summaries — no natural language."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from scanner.tracking import WON, summarize

from ._helpers import closed_trades, factor_set


@dataclass
class FactorImportance:
    factor: str
    label: str
    trade_count: int
    expectancy: float | None
    marginal_delta: float | None
    importance_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "label": self.label,
            "trade_count": self.trade_count,
            "expectancy": self.expectancy,
            "marginal_delta": self.marginal_delta,
            "importance_score": round(self.importance_score, 4),
        }


@dataclass
class KnowledgeSummary:
    sample_size: int
    closed_trades: int
    overall_expectancy: float | None
    overall_win_rate: float | None
    factor_importance: list[FactorImportance] = field(default_factory=list)
    top_factor: str = ""
    trend_importance: float = 0.0
    liquidity_importance: float = 0.0
    volume_importance: float = 0.0
    order_block_importance: float = 0.0
    pattern_importance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "closed_trades": self.closed_trades,
            "overall_expectancy": self.overall_expectancy,
            "overall_win_rate": self.overall_win_rate,
            "factor_importance": [f.to_dict() for f in self.factor_importance],
            "top_factor": self.top_factor,
            "trend_importance": round(self.trend_importance, 4),
            "liquidity_importance": round(self.liquidity_importance, 4),
            "volume_importance": round(self.volume_importance, 4),
            "order_block_importance": round(self.order_block_importance, 4),
            "pattern_importance": round(self.pattern_importance, 4),
        }


_LABELS = {
    "htf": "Trend",
    "sweep": "Liquidity",
    "breakout": "Volume",
    "price_action": "OrderBlock",
    "pattern": "Pattern",
    "candles": "Candles",
    "confluence": "Confluence",
    "elliott": "Elliott",
    "score": "Score",
}


class KnowledgeSummaryEngine:
    """Summarize last N trades with factor importance — structured only."""

    def __init__(self, *, default_window: int = 500, min_factor_n: int = 3) -> None:
        self.default_window = default_window
        self.min_factor_n = min_factor_n

    def summarize(self, rows: Iterable[dict], *,
                  window: int | None = None) -> KnowledgeSummary:
        rows = list(rows)
        window = window or self.default_window
        sample = rows[-window:] if len(rows) > window else rows
        closed = closed_trades(sample)
        overall = summarize(sample)

        factors: set[str] = set()
        for row in closed:
            factors.update(factor_set(row))

        importances: list[FactorImportance] = []
        baseline_exp = overall.get("expectancy") or 0.0

        for factor in sorted(factors):
            with_rows = [r for r in closed if factor in factor_set(r)]
            without_rows = [r for r in closed if factor not in factor_set(r)]
            if len(with_rows) < self.min_factor_n:
                continue
            sw = summarize(with_rows)
            s_wo = summarize(without_rows) if without_rows else {"expectancy": baseline_exp}
            exp_with = sw.get("expectancy") or 0.0
            exp_without = s_wo.get("expectancy") if s_wo.get("expectancy") is not None else baseline_exp
            delta = round(exp_with - exp_without, 3)
            score = abs(delta) * (len(with_rows) / max(len(closed), 1))
            importances.append(FactorImportance(
                factor=factor,
                label=_LABELS.get(factor, factor),
                trade_count=len(with_rows),
                expectancy=sw.get("expectancy"),
                marginal_delta=delta,
                importance_score=score,
            ))

        importances.sort(key=lambda x: x.importance_score, reverse=True)
        top = importances[0].factor if importances else ""

        def _imp(*keys: str) -> float:
            total = sum(f.importance_score for f in importances if f.factor in keys)
            return total

        wins = sum(1 for r in closed if r.get("status") == WON)
        wr = round(wins / len(closed) * 100, 2) if closed else None

        return KnowledgeSummary(
            sample_size=len(sample),
            closed_trades=len(closed),
            overall_expectancy=overall.get("expectancy"),
            overall_win_rate=wr,
            factor_importance=importances,
            top_factor=top,
            trend_importance=_imp("htf"),
            liquidity_importance=_imp("sweep", "confluence"),
            volume_importance=_imp("breakout"),
            order_block_importance=_imp("price_action"),
            pattern_importance=_imp("pattern", "candles"),
        )
