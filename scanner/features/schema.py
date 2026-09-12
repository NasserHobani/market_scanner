"""Feature snapshot schema."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FeatureSnapshot:
    snapshot_id: str
    symbol: str
    market: str
    timeframe: str
    candle_time: datetime
    score: float
    confluence: int
    htf: int
    liquidity: str
    quote_volume: float | None
    action: str
    grade: str
    confidence: float
    rr: float | None
    factors: list[str]
    features: dict[str, Any]
