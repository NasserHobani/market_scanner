# -*- coding: utf-8 -*-
"""Long-term market memory — historical regime buckets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from scanner.tracking import summarize

from ._helpers import avg_r, closed_trades, win_rate


@dataclass
class MarketMemoryRecord:
    memory_id: str
    bucket: str
    market: str
    timeframe: str
    regime_label: str
    trade_count: int
    win_rate: float | None
    expectancy: float | None
    avg_r: float | None
    total_r: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "bucket": self.bucket,
            "market": self.market,
            "timeframe": self.timeframe,
            "regime_label": self.regime_label,
            "trade_count": self.trade_count,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "avg_r": self.avg_r,
            "total_r": self.total_r,
        }


@dataclass
class MarketMemory:
    records: list[MarketMemoryRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.records),
            "records": [r.to_dict() for r in self.records],
        }


def _regime_label(row: dict) -> str:
    """Infer regime bucket from row metadata — no new indicators."""
    grade = row.get("grade") or ""
    market = row.get("market") or "unknown"
    tf = row.get("timeframe") or "unknown"
    factors = row.get("factors") or []
    if "htf" in factors:
        trend = "trending"
    elif "confluence" in factors:
        trend = "range"
    else:
        trend = "mixed"
    vol = "high_vol" if row.get("atr_pct") and float(row["atr_pct"]) > 3 else "normal_vol"
    return f"{market}:{tf}:{trend}:{vol}"


class MarketMemoryEngine:
    """Aggregate historical outcomes by market regime buckets."""

    def __init__(self, *, min_trades: int = 3) -> None:
        self.min_trades = min_trades

    def build(self, rows: Iterable[dict]) -> MarketMemory:
        closed = closed_trades(rows)
        buckets: dict[str, list[dict]] = {}
        for row in closed:
            label = _regime_label(row)
            buckets.setdefault(label, []).append(row)

        records: list[MarketMemoryRecord] = []
        for label, bucket in sorted(buckets.items()):
            if len(bucket) < self.min_trades:
                continue
            parts = label.split(":")
            market = parts[0] if parts else "unknown"
            tf = parts[1] if len(parts) > 1 else "unknown"
            stats = summarize(bucket)
            records.append(MarketMemoryRecord(
                memory_id=f"mem_{label.replace(':', '_')}",
                bucket=label,
                market=market,
                timeframe=tf,
                regime_label=label,
                trade_count=len(bucket),
                win_rate=win_rate(bucket),
                expectancy=stats.get("expectancy"),
                avg_r=avg_r(bucket),
                total_r=stats.get("total_r"),
            ))

        records.sort(key=lambda r: (r.expectancy or -99), reverse=True)
        return MarketMemory(records=records)
