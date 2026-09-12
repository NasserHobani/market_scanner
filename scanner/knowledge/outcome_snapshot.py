# -*- coding: utf-8 -*-
"""Outcome snapshot — closed trade results for learning."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .compat import upgrade_snapshot
from .data_quality import DataQualityReport
from .schemas import OutcomeClass
from .versioning import SchemaMetadata


@dataclass
class OutcomeSnapshot:
    snapshot_id: str
    event_id: str
    trade_snapshot_id: str
    trade_id: str | int | None
    symbol: str
    market: str
    timeframe: str
    outcome_class: str
    status: str
    profit: bool = False
    loss: bool = False
    break_even: bool = False
    r_multiple: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    holding_time_seconds: float | None = None
    bars_held: int = 0
    exit_reason: str = ""
    entry_price: float | None = None
    exit_price: float | None = None
    fees: float | None = None
    slippage: float | None = None
    closed_at: datetime | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    quality: DataQualityReport = field(default_factory=DataQualityReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "event_id": self.event_id,
            "trade_snapshot_id": self.trade_snapshot_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "outcome_class": self.outcome_class,
            "status": self.status,
            "profit": self.profit,
            "loss": self.loss,
            "break_even": self.break_even,
            "r_multiple": self.r_multiple,
            "mfe_r": self.mfe_r,
            "mae_r": self.mae_r,
            "holding_time_seconds": self.holding_time_seconds,
            "bars_held": self.bars_held,
            "exit_reason": self.exit_reason,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "fees": self.fees,
            "slippage": self.slippage,
            "closed_at": (self.closed_at.isoformat() if self.closed_at else None),
            "extensions": dict(self.extensions),
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
            "quality": self.quality.to_dict(),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> OutcomeSnapshot:
        row = upgrade_snapshot(row)
        closed = row.get("closed_at")
        return cls(
            snapshot_id=row["snapshot_id"],
            event_id=row["event_id"],
            trade_snapshot_id=row.get("trade_snapshot_id") or "",
            trade_id=row.get("trade_id"),
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            outcome_class=row.get("outcome_class") or OutcomeClass.UNKNOWN.value,
            status=row.get("status") or "",
            profit=bool(row.get("profit")),
            loss=bool(row.get("loss")),
            break_even=bool(row.get("break_even")),
            r_multiple=row.get("r_multiple"),
            mfe_r=row.get("mfe_r"),
            mae_r=row.get("mae_r"),
            holding_time_seconds=row.get("holding_time_seconds"),
            bars_held=int(row.get("bars_held") or 0),
            exit_reason=row.get("exit_reason") or "",
            entry_price=row.get("entry_price"),
            exit_price=row.get("exit_price"),
            fees=row.get("fees"),
            slippage=row.get("slippage"),
            closed_at=(datetime.fromisoformat(str(closed).replace("Z", "+00:00"))
                       if closed else None),
            extensions=dict(row.get("extensions") or {}),
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            quality=DataQualityReport.from_dict(row.get("quality")),
        )
