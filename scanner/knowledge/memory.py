# -*- coding: utf-8 -*-
"""AI memory foundation — containers for future AI-generated summaries."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .audit import AuditTrail
from .versioning import SchemaMetadata


@dataclass
class KnowledgeSummary:
    """Top-level memory slot for an event or session."""

    summary_id: str
    event_id: str
    content: str = ""
    key_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    generated_by: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "event_id": self.event_id,
            "content": self.content,
            "key_points": list(self.key_points),
            "tags": list(self.tags),
            "generated_by": self.generated_by,
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
            "extensions": dict(self.extensions),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> KnowledgeSummary:
        return cls(
            summary_id=row["summary_id"],
            event_id=row["event_id"],
            content=row.get("content") or "",
            key_points=list(row.get("key_points") or []),
            tags=list(row.get("tags") or []),
            generated_by=row.get("generated_by") or "",
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            extensions=dict(row.get("extensions") or {}),
        )


@dataclass
class MarketSummary:
    """Memory slot for market-level narrative (AI-generated later)."""

    summary_id: str
    market: str
    timeframe: str
    content: str = ""
    regime: str = ""
    highlights: list[str] = field(default_factory=list)
    fingerprint: str = ""
    generated_by: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "market": self.market,
            "timeframe": self.timeframe,
            "content": self.content,
            "regime": self.regime,
            "highlights": list(self.highlights),
            "fingerprint": self.fingerprint,
            "generated_by": self.generated_by,
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
        }


@dataclass
class StrategySummary:
    """Memory slot for strategy behaviour narrative."""

    summary_id: str
    strategy_id: str = "default"
    content: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    generated_by: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "strategy_id": self.strategy_id,
            "content": self.content,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "generated_by": self.generated_by,
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
        }


@dataclass
class PerformanceSummary:
    """Memory slot for performance narrative."""

    summary_id: str
    period: str = ""
    content: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    generated_by: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "period": self.period,
            "content": self.content,
            "metrics": dict(self.metrics),
            "generated_by": self.generated_by,
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
        }


@dataclass
class KnowledgeMemory:
    """Bundle of memory slots for one event — populated by AI in future sprints."""

    event_id: str
    knowledge: KnowledgeSummary | None = None
    market: MarketSummary | None = None
    strategy: StrategySummary | None = None
    performance: PerformanceSummary | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "knowledge": self.knowledge.to_dict() if self.knowledge else None,
            "market": self.market.to_dict() if self.market else None,
            "strategy": self.strategy.to_dict() if self.strategy else None,
            "performance": self.performance.to_dict() if self.performance else None,
            "updated_at": self.updated_at.isoformat(),
        }

    def empty_slots(self) -> list[str]:
        slots = []
        if not self.knowledge or not self.knowledge.content:
            slots.append("knowledge")
        if not self.market or not self.market.content:
            slots.append("market")
        if not self.strategy or not self.strategy.content:
            slots.append("strategy")
        if not self.performance or not self.performance.content:
            slots.append("performance")
        return slots
