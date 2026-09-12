# -*- coding: utf-8 -*-
"""Canonical point-in-time snapshot contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SNAPSHOT_VERSION_V3 = "3.0.0"
FEATURE_SCHEMA_VERSION_V3 = "3.0.0"


class SnapshotStatus(str, Enum):
    CREATED = "SNAPSHOT_CREATED"
    PARTIAL = "SNAPSHOT_PARTIAL"
    FAILED = "SNAPSHOT_FAILED"
    REJECTED = "SNAPSHOT_REJECTED"
    HISTORICAL_RECONSTRUCTED = "HISTORICAL_RECONSTRUCTED"
    HISTORICAL_UNAVAILABLE = "HISTORICAL_SNAPSHOT_UNAVAILABLE"


class SnapshotQualityStatus(str, Enum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    POOR = "POOR"
    FAILED = "FAILED"


@dataclass
class FeatureProvenance:
    name: str
    value: float | int | str | bool | None
    source: str
    source_timestamp: str
    calculation_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "source": self.source,
            "source_timestamp": self.source_timestamp,
            "calculation_version": self.calculation_version,
        }


@dataclass
class PointInTimeSnapshot:
    snapshot_id: str
    symbol: str
    timeframe: str
    market: str = ""
    strategy_id: str = ""
    recommendation_id: str = ""
    decision_timestamp: str = ""
    feature_timestamp: str = ""
    snapshot_version: str = SNAPSHOT_VERSION_V3
    feature_schema_version: str = FEATURE_SCHEMA_VERSION_V3
    source_versions: dict[str, str] = field(default_factory=dict)
    features: dict[str, float] = field(default_factory=dict)
    provenance: list[FeatureProvenance] = field(default_factory=list)
    coverage: float = 0.0
    quality_status: str = SnapshotQualityStatus.PARTIAL.value
    status: str = SnapshotStatus.CREATED.value
    legacy_snapshot_id: str = ""
    event_id: str = ""
    failure_reason: str = ""
    created_at: str = ""
    missing_features: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    runtime_quality: str = ""
    capture_latency_ms: float = 0.0
    collection_latency_ms: float = 0.0
    content_hash: str = ""
    missing_by_category: dict[str, int] = field(default_factory=dict)
    missing_feature_reasons: dict[str, str] = field(default_factory=dict)
    enrichment_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market": self.market,
            "strategy_id": self.strategy_id,
            "recommendation_id": self.recommendation_id,
            "decision_timestamp": self.decision_timestamp,
            "feature_timestamp": self.feature_timestamp,
            "snapshot_version": self.snapshot_version,
            "feature_schema_version": self.feature_schema_version,
            "source_versions": dict(self.source_versions),
            "features": dict(self.features),
            "provenance": [p.to_dict() for p in self.provenance],
            "coverage": self.coverage,
            "quality_status": self.quality_status,
            "status": self.status,
            "legacy_snapshot_id": self.legacy_snapshot_id,
            "event_id": self.event_id,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
            "missing_features": list(self.missing_features),
            "failure_reasons": list(self.failure_reasons),
            "runtime_quality": self.runtime_quality,
            "capture_latency_ms": self.capture_latency_ms,
            "collection_latency_ms": self.collection_latency_ms,
            "content_hash": self.content_hash,
            "missing_by_category": dict(self.missing_by_category),
            "missing_feature_reasons": dict(self.missing_feature_reasons),
            "enrichment_meta": dict(self.enrichment_meta),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> PointInTimeSnapshot:
        prov = [
            FeatureProvenance(**p) if isinstance(p, dict) else p
            for p in (row.get("provenance") or [])
        ]
        return cls(
            snapshot_id=row.get("snapshot_id", ""),
            symbol=row.get("symbol", ""),
            timeframe=row.get("timeframe", ""),
            market=row.get("market", ""),
            strategy_id=row.get("strategy_id", ""),
            recommendation_id=row.get("recommendation_id", ""),
            decision_timestamp=row.get("decision_timestamp", ""),
            feature_timestamp=row.get("feature_timestamp", ""),
            snapshot_version=row.get("snapshot_version", SNAPSHOT_VERSION_V3),
            feature_schema_version=row.get("feature_schema_version", FEATURE_SCHEMA_VERSION_V3),
            source_versions=dict(row.get("source_versions") or {}),
            features={k: float(v) for k, v in (row.get("features") or {}).items()
                      if v is not None},
            provenance=prov,
            coverage=float(row.get("coverage") or 0),
            quality_status=row.get("quality_status", SnapshotQualityStatus.PARTIAL.value),
            status=row.get("status", SnapshotStatus.CREATED.value),
            legacy_snapshot_id=row.get("legacy_snapshot_id", ""),
            event_id=row.get("event_id", ""),
            failure_reason=row.get("failure_reason", ""),
            created_at=row.get("created_at", ""),
            missing_features=list(row.get("missing_features") or []),
            failure_reasons=list(row.get("failure_reasons") or []),
            runtime_quality=row.get("runtime_quality", ""),
            capture_latency_ms=float(row.get("capture_latency_ms") or 0),
            collection_latency_ms=float(row.get("collection_latency_ms") or 0),
            content_hash=row.get("content_hash", ""),
            missing_by_category=dict(row.get("missing_by_category") or {}),
            missing_feature_reasons=dict(row.get("missing_feature_reasons") or {}),
            enrichment_meta=dict(row.get("enrichment_meta") or {}),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
