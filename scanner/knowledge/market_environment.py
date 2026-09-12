# -*- coding: utf-8 -*-
"""Market environment — overall conditions, separate from per-symbol features."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .data_quality import DataQualityReport
from .versioning import SchemaMetadata


@dataclass
class MarketEnvironment:
    """Macro market context — primary AI input alongside symbol snapshots."""

    environment_id: str
    event_id: str
    market: str
    timeframe: str
    timestamp: datetime
    market_regime: str = ""
    trend_state: str = ""
    volatility_class: str = ""
    liquidity_class: str = ""
    trading_session: str = ""
    dominance: float | None = None
    fear_greed: float | None = None
    market_breadth: float | None = None
    sector_strength: dict[str, Any] = field(default_factory=dict)
    correlation_summary: dict[str, Any] = field(default_factory=dict)
    linked_market_snapshot_id: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    quality: DataQualityReport = field(default_factory=DataQualityReport)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "event_id": self.event_id,
            "market": self.market,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "market_regime": self.market_regime,
            "trend_state": self.trend_state,
            "volatility_class": self.volatility_class,
            "liquidity_class": self.liquidity_class,
            "trading_session": self.trading_session,
            "dominance": self.dominance,
            "fear_greed": self.fear_greed,
            "market_breadth": self.market_breadth,
            "sector_strength": dict(self.sector_strength),
            "correlation_summary": dict(self.correlation_summary),
            "linked_market_snapshot_id": self.linked_market_snapshot_id,
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
            "quality": self.quality.to_dict(),
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> MarketEnvironment:
        return cls(
            environment_id=row["environment_id"],
            event_id=row["event_id"],
            market=row["market"],
            timeframe=row["timeframe"],
            timestamp=datetime.fromisoformat(
                str(row["timestamp"]).replace("Z", "+00:00")),
            market_regime=row.get("market_regime") or "",
            trend_state=row.get("trend_state") or "",
            volatility_class=row.get("volatility_class") or "",
            liquidity_class=row.get("liquidity_class") or "",
            trading_session=row.get("trading_session") or "",
            dominance=row.get("dominance"),
            fear_greed=row.get("fear_greed"),
            market_breadth=row.get("market_breadth"),
            sector_strength=dict(row.get("sector_strength") or {}),
            correlation_summary=dict(row.get("correlation_summary") or {}),
            linked_market_snapshot_id=row.get("linked_market_snapshot_id") or "",
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            quality=DataQualityReport.from_dict(row.get("quality")),
            extensions=dict(row.get("extensions") or {}),
        )
