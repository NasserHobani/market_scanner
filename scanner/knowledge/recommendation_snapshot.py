# -*- coding: utf-8 -*-
"""Recommendation snapshot — frozen plan at generation time."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .compat import upgrade_snapshot
from .data_quality import DataQualityReport
from .versioning import SchemaMetadata


@dataclass
class RecommendationSnapshot:
    snapshot_id: str
    event_id: str
    feature_snapshot_id: str
    symbol: str
    market: str
    timeframe: str
    direction: str
    action: str
    entry: float | None = None
    stop: float | None = None
    targets: list[float] = field(default_factory=list)
    risk_reward: float | None = None
    confidence: float = 0.0
    grade: str = "—"
    generated_at: datetime | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    vetoes: list[str] = field(default_factory=list)
    trigger: str = ""
    votes: float = 0.0
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    headline: str = ""
    invalidation: float | None = None
    valid_until: str = ""
    size: dict[str, Any] = field(default_factory=dict)
    analysis_summary: dict[str, Any] = field(default_factory=dict)
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    quality: DataQualityReport = field(default_factory=DataQualityReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "event_id": self.event_id,
            "feature_snapshot_id": self.feature_snapshot_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "action": self.action,
            "entry": self.entry,
            "stop": self.stop,
            "targets": list(self.targets),
            "risk_reward": self.risk_reward,
            "confidence": self.confidence,
            "grade": self.grade,
            "generated_at": (self.generated_at.isoformat()
                             if self.generated_at else None),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "vetoes": list(self.vetoes),
            "trigger": self.trigger,
            "votes": self.votes,
            "breakdown": list(self.breakdown),
            "headline": self.headline,
            "invalidation": self.invalidation,
            "valid_until": self.valid_until,
            "size": dict(self.size),
            "analysis_summary": dict(self.analysis_summary),
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
            "quality": self.quality.to_dict(),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> RecommendationSnapshot:
        row = upgrade_snapshot(row)
        gen = row.get("generated_at")
        return cls(
            snapshot_id=row["snapshot_id"],
            event_id=row["event_id"],
            feature_snapshot_id=row["feature_snapshot_id"],
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            direction=row.get("direction") or "—",
            action=row.get("action") or "none",
            entry=row.get("entry"),
            stop=row.get("stop"),
            targets=list(row.get("targets") or []),
            risk_reward=row.get("risk_reward"),
            confidence=float(row.get("confidence") or 0.0),
            grade=row.get("grade") or "—",
            generated_at=(datetime.fromisoformat(str(gen).replace("Z", "+00:00"))
                          if gen else None),
            reasons=list(row.get("reasons") or []),
            warnings=list(row.get("warnings") or []),
            vetoes=list(row.get("vetoes") or []),
            trigger=row.get("trigger") or "",
            votes=float(row.get("votes") or 0.0),
            breakdown=list(row.get("breakdown") or []),
            headline=row.get("headline") or "",
            invalidation=row.get("invalidation"),
            valid_until=row.get("valid_until") or "",
            size=dict(row.get("size") or {}),
            analysis_summary=dict(row.get("analysis_summary") or {}),
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            quality=DataQualityReport.from_dict(row.get("quality")),
        )
