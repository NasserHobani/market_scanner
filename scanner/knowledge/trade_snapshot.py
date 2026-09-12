# -*- coding: utf-8 -*-
"""Trade snapshot — lifecycle tracking for paper and live trades."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .compat import upgrade_snapshot
from .data_quality import DataQualityReport
from .versioning import SchemaMetadata


@dataclass
class TradeSnapshot:
    snapshot_id: str
    event_id: str
    recommendation_snapshot_id: str
    feature_snapshot_id: str
    trade_id: str | int | None
    symbol: str
    market: str
    timeframe: str
    side: str
    source: str
    status: str
    lifecycle: str
    planned_entry: float | None = None
    planned_stop: float | None = None
    planned_target: float | None = None
    planned_rr: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    current_r: float | None = None
    unrealized_r: float | None = None
    grade: str = "—"
    score: float | None = None
    confidence: float = 0.0
    factors: list[str] = field(default_factory=list)
    signal_at: datetime | None = None
    candle_time: datetime | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    duration_seconds: float | None = None
    bars_held: int = 0
    resolution_note: str = ""
    extensions: dict[str, Any] = field(default_factory=dict)
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    quality: DataQualityReport = field(default_factory=DataQualityReport)

    def to_dict(self) -> dict[str, Any]:
        def _iso(v: datetime | None) -> str | None:
            return v.isoformat() if v else None

        return {
            "snapshot_id": self.snapshot_id,
            "event_id": self.event_id,
            "recommendation_snapshot_id": self.recommendation_snapshot_id,
            "feature_snapshot_id": self.feature_snapshot_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "side": self.side,
            "source": self.source,
            "status": self.status,
            "lifecycle": self.lifecycle,
            "planned_entry": self.planned_entry,
            "planned_stop": self.planned_stop,
            "planned_target": self.planned_target,
            "planned_rr": self.planned_rr,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "current_r": self.current_r,
            "unrealized_r": self.unrealized_r,
            "grade": self.grade,
            "score": self.score,
            "confidence": self.confidence,
            "factors": list(self.factors),
            "signal_at": _iso(self.signal_at),
            "candle_time": _iso(self.candle_time),
            "opened_at": _iso(self.opened_at),
            "closed_at": _iso(self.closed_at),
            "duration_seconds": self.duration_seconds,
            "bars_held": self.bars_held,
            "resolution_note": self.resolution_note,
            "extensions": dict(self.extensions),
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
            "quality": self.quality.to_dict(),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> TradeSnapshot:
        row = upgrade_snapshot(row)
        def _parse(v) -> datetime | None:
            if not v:
                return None
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))

        return cls(
            snapshot_id=row["snapshot_id"],
            event_id=row["event_id"],
            recommendation_snapshot_id=row.get("recommendation_snapshot_id") or "",
            feature_snapshot_id=row.get("feature_snapshot_id") or "",
            trade_id=row.get("trade_id"),
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            side=row.get("side") or "buy",
            source=row.get("source") or "auto",
            status=row.get("status") or "pending",
            lifecycle=row.get("lifecycle") or row.get("status") or "pending",
            planned_entry=row.get("planned_entry"),
            planned_stop=row.get("planned_stop"),
            planned_target=row.get("planned_target"),
            planned_rr=row.get("planned_rr"),
            entry_price=row.get("entry_price"),
            exit_price=row.get("exit_price"),
            current_r=row.get("current_r"),
            unrealized_r=row.get("unrealized_r"),
            grade=row.get("grade") or "—",
            score=row.get("score"),
            confidence=float(row.get("confidence") or 0.0),
            factors=list(row.get("factors") or []),
            signal_at=_parse(row.get("signal_at")),
            candle_time=_parse(row.get("candle_time")),
            opened_at=_parse(row.get("opened_at")),
            closed_at=_parse(row.get("closed_at")),
            duration_seconds=row.get("duration_seconds"),
            bars_held=int(row.get("bars_held") or 0),
            resolution_note=row.get("resolution_note") or "",
            extensions=dict(row.get("extensions") or {}),
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            quality=DataQualityReport.from_dict(row.get("quality")),
        )
