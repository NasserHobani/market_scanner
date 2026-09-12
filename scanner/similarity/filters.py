# -*- coding: utf-8 -*-
"""Retrieval filters for historical knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RetrievalFilters:
    """Filter criteria for similarity retrieval."""

    market: str | None = None
    timeframe: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    outcome: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_quality: float = 0.0
    require_outcome: bool = False
    exclude_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "timeframe": self.timeframe,
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "outcome": self.outcome,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "min_quality": self.min_quality,
            "require_outcome": self.require_outcome,
            "exclude_event_ids": list(self.exclude_event_ids),
        }


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def apply_filters(candidate: dict[str, Any],
                  filters: RetrievalFilters) -> bool:
    """Return True if candidate passes all filters."""
    if filters.market and candidate.get("market") != filters.market:
        return False
    if filters.timeframe and candidate.get("timeframe") != filters.timeframe:
        return False
    if filters.symbol and candidate.get("symbol") != filters.symbol:
        return False
    if filters.exclude_event_ids and candidate.get("event_id") in filters.exclude_event_ids:
        return False

    quality = candidate.get("quality_score", 1.0)
    if quality < filters.min_quality:
        return False

    if filters.require_outcome and not candidate.get("has_outcome"):
        return False

    if filters.outcome:
        oc = candidate.get("outcome_class") or ""
        if filters.outcome == "winner" and oc != "winner":
            return False
        if filters.outcome == "loser" and oc != "loser":
            return False
        if filters.outcome == "won" and candidate.get("status") not in ("won", "winner"):
            if oc != "winner":
                return False
        if filters.outcome == "lost" and candidate.get("status") not in ("lost", "loser"):
            if oc != "loser":
                return False

    ts = _parse_ts(
        candidate.get("candle_time")
        or candidate.get("timestamp")
        or candidate.get("closed_at")
    )
    if ts and filters.date_from and ts < filters.date_from:
        return False
    if ts and filters.date_to and ts > filters.date_to:
        return False

    return True
