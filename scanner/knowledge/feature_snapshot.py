# -*- coding: utf-8 -*-
"""Feature snapshot — extensible feature store for AI and ML."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .compat import upgrade_snapshot
from .data_quality import DataQualityReport
from .feature_metadata import FeatureRegistry, FeatureValue
from .feature_vector import (
    components_to_vector,
    registry_to_dataframe,
    registry_to_dict,
    registry_to_vector,
)
from .versioning import SchemaMetadata


@dataclass
class FeatureGroups:
    """Grouped features — each bucket is open-ended for future expansion."""

    trend: dict[str, Any] = field(default_factory=dict)
    ema_alignment: dict[str, Any] = field(default_factory=dict)
    momentum: dict[str, Any] = field(default_factory=dict)
    volume: dict[str, Any] = field(default_factory=dict)
    market_structure: dict[str, Any] = field(default_factory=dict)
    liquidity: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    elliott: dict[str, Any] = field(default_factory=dict)
    support_resistance: dict[str, Any] = field(default_factory=dict)
    confluence: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any] | None) -> FeatureGroups:
        row = row or {}
        return cls(**{k: dict(row.get(k) or {})
                      for k in ("trend", "ema_alignment", "momentum", "volume",
                                "market_structure", "liquidity", "patterns",
                                "elliott", "support_resistance", "confluence",
                                "scoring", "extensions")})


@dataclass
class FeatureSnapshot:
    """Knowledge-layer feature store record with metadata and vector export."""

    snapshot_id: str
    event_id: str
    symbol: str
    market: str
    timeframe: str
    candle_time: datetime
    groups: FeatureGroups = field(default_factory=FeatureGroups)
    feature_registry: FeatureRegistry = field(default_factory=FeatureRegistry)
    raw_components: dict[str, int] = field(default_factory=dict)
    factor_labels: list[str] = field(default_factory=list)
    final_grade: str = "—"
    final_score: float | None = None
    linked_market_snapshot_id: str = ""
    schema: SchemaMetadata = field(default_factory=SchemaMetadata)
    audit: AuditTrail = field(default_factory=AuditTrail)
    quality: DataQualityReport = field(default_factory=DataQualityReport)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "event_id": self.event_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "candle_time": self.candle_time.isoformat(),
            "groups": self.groups.to_dict(),
            "feature_registry": self.feature_registry.to_dict(),
            "raw_components": dict(self.raw_components),
            "factor_labels": list(self.factor_labels),
            "final_grade": self.final_grade,
            "final_score": self.final_score,
            "linked_market_snapshot_id": self.linked_market_snapshot_id,
            "schema": self.schema.to_dict(),
            "audit": self.audit.to_dict(),
            "quality": self.quality.to_dict(),
        }

    def to_vector(self) -> list[float | None]:
        """Numeric feature vector from registry (no ML deps)."""
        return registry_to_vector(self.feature_registry)

    def to_dataframe(self) -> dict[str, Any]:
        """Tabular export: columns + rows (no pandas)."""
        return registry_to_dataframe(self.feature_registry)

    def to_feature_dict(self) -> dict[str, Any]:
        """Full export including groups and components."""
        return registry_to_dict(
            self.feature_registry,
            groups=self.groups.to_dict(),
            raw_components=self.raw_components,
            meta={
                "snapshot_id": self.snapshot_id,
                "final_grade": self.final_grade,
                "final_score": self.final_score,
            },
        )

    def component_vector(self) -> list[int]:
        return components_to_vector(self.raw_components)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> FeatureSnapshot:
        row = upgrade_snapshot(row)
        return cls(
            snapshot_id=row["snapshot_id"],
            event_id=row["event_id"],
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            candle_time=datetime.fromisoformat(
                str(row["candle_time"]).replace("Z", "+00:00")),
            groups=FeatureGroups.from_dict(row.get("groups")),
            feature_registry=FeatureRegistry.from_dict(row.get("feature_registry")),
            raw_components=dict(row.get("raw_components") or {}),
            factor_labels=list(row.get("factor_labels") or []),
            final_grade=row.get("final_grade") or "—",
            final_score=row.get("final_score"),
            linked_market_snapshot_id=row.get("linked_market_snapshot_id") or "",
            schema=SchemaMetadata.from_dict(row.get("schema")),
            audit=AuditTrail.from_dict(row.get("audit")),
            quality=DataQualityReport.from_dict(row.get("quality")),
        )

    def get_feature(self, name: str) -> FeatureValue | None:
        return self.feature_registry.get(name)
