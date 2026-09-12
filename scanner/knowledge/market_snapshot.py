# -*- coding: utf-8 -*-
"""Market snapshot — state of a symbol at a closed candle."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .compat import upgrade_snapshot
from .data_quality import DataQualityReport
from .fingerprint import market_fingerprint
from .versioning import SchemaMetadata


@dataclass(frozen=True)
class OHLCV:
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


@dataclass
class MarketSnapshot:
    """Captures market state already computed by the platform."""

    snapshot_id: str
    event_id: str
    symbol: str
    exchange: str
    market: str
    timeframe: str
    timestamp: datetime
    ohlcv: OHLCV = field(default_factory=OHLCV)
    session: str = ""
    regime: str = ""
    regime_score: int | None = None
    trend_direction: str = ""
    htf_bias: int | None = None
    atr: float | None = None
    atr_pct: float | None = None
    liquidity_class: str = "unknown"
    quote_volume: float | None = None
    volatility: str = ""
    breadth_pct: float | None = None
    fingerprint: str = ""
    linked_environment_id: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    quality: DataQualityReport = field(default_factory=DataQualityReport)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["timestamp"] = self.timestamp.isoformat()
        row["ohlcv"] = asdict(self.ohlcv)
        row["schema"] = self.schema.to_dict()
        row["audit"] = self.audit.to_dict()
        row["quality"] = self.quality.to_dict()
        if not row.get("fingerprint"):
            row["fingerprint"] = market_fingerprint(row)
        return row

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> MarketSnapshot:
        row = upgrade_snapshot(row)
        ohlcv_raw = row.get("ohlcv") or {}
        fp = row.get("fingerprint") or market_fingerprint(row)
        return cls(
            snapshot_id=row["snapshot_id"],
            event_id=row["event_id"],
            symbol=row["symbol"],
            exchange=row.get("exchange") or "",
            market=row["market"],
            timeframe=row["timeframe"],
            timestamp=datetime.fromisoformat(
                str(row["timestamp"]).replace("Z", "+00:00")),
            ohlcv=OHLCV(**{k: ohlcv_raw.get(k) for k in
                           ("open", "high", "low", "close", "volume")}),
            session=row.get("session") or "",
            regime=row.get("regime") or "",
            regime_score=row.get("regime_score"),
            trend_direction=row.get("trend_direction") or "",
            htf_bias=row.get("htf_bias"),
            atr=row.get("atr"),
            atr_pct=row.get("atr_pct"),
            liquidity_class=row.get("liquidity_class") or "unknown",
            quote_volume=row.get("quote_volume"),
            volatility=row.get("volatility") or "",
            breadth_pct=row.get("breadth_pct"),
            fingerprint=fp,
            linked_environment_id=row.get("linked_environment_id") or "",
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            quality=DataQualityReport.from_dict(row.get("quality")),
            extensions=dict(row.get("extensions") or {}),
        )
