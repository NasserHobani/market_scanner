# -*- coding: utf-8 -*-
"""Shared schemas, enums, and identifiers for the knowledge layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SnapshotKind(str, Enum):
    MARKET = "market"
    ENVIRONMENT = "environment"
    FEATURE = "feature"
    RECOMMENDATION = "recommendation"
    TRADE = "trade"
    OUTCOME = "outcome"
    EXPERIMENT = "experiment"
    MODEL = "model"
    MEMORY = "memory"
    RELATIONSHIP = "relationship"


class TradeLifecycle(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    RUNNING = "running"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OutcomeClass(str, Enum):
    WINNER = "winner"
    LOSER = "loser"
    BREAK_EVEN = "break_even"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class KnowledgeRef:
    """Cross-snapshot correlation handle."""

    event_id: str
    symbol: str
    market: str
    timeframe: str
    candle_time: datetime | None = None


@dataclass
class KnowledgeRecord:
    """Envelope stored by the repository."""

    record_id: str
    kind: SnapshotKind
    event_id: str
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "kind": self.kind.value,
            "event_id": self.event_id,
            "created_at": self.created_at.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> KnowledgeRecord:
        return cls(
            record_id=row["record_id"],
            kind=SnapshotKind(row["kind"]),
            event_id=row["event_id"],
            created_at=datetime.fromisoformat(
                str(row["created_at"]).replace("Z", "+00:00")),
            payload=dict(row.get("payload") or {}),
        )


@dataclass
class StrategyStatistics:
    """Aggregate performance context for AI — no new calculations."""

    closed_trades: int = 0
    win_rate: float | None = None
    expectancy: float | None = None
    profit_factor: float | None = None
    max_drawdown_r: float | None = None
    sharpe: float | None = None
    recent_expectancy_30: float | None = None
    reliable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "closed_trades": self.closed_trades,
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "max_drawdown_r": self.max_drawdown_r,
            "sharpe": self.sharpe,
            "recent_expectancy_30": self.recent_expectancy_30,
            "reliable": self.reliable,
        }
