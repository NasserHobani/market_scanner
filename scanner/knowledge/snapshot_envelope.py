# -*- coding: utf-8 -*-
"""Shared envelope helpers for schema, audit, and quality."""
from __future__ import annotations

from typing import Any

from .audit import AuditTrail
from .data_quality import DataQualityReport, assess_completeness
from .versioning import GENERATOR_VERSION, SchemaMetadata


def default_audit(*, creator: str = "knowledge_builder",
                  source: str = "platform",
                  pipeline_stage: str = "capture") -> AuditTrail:
    return AuditTrail(
        creator=creator,
        version=GENERATOR_VERSION,
        source=source,
        pipeline_stage=pipeline_stage,
    )


def envelope_dict(*, schema: SchemaMetadata | None = None,
                  audit: AuditTrail | None = None,
                  quality: DataQualityReport | None = None,
                  extra: dict[str, Any] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "schema": (schema or SchemaMetadata()).to_dict(),
        "audit": (audit or default_audit()).to_dict(),
        "quality": (quality or DataQualityReport()).to_dict(),
    }
    if extra:
        row.update(extra)
    return row


def load_envelope(row: dict[str, Any]) -> tuple[SchemaMetadata, AuditTrail, DataQualityReport]:
    return (
        SchemaMetadata.from_dict(row.get("schema")),
        AuditTrail.from_dict(row.get("audit")),
        DataQualityReport.from_dict(row.get("quality")),
    )


def quality_for_market(payload: dict[str, Any]) -> DataQualityReport:
    return assess_completeness(
        payload,
        required=["symbol", "market", "timeframe", "timestamp"],
        optional=["atr_pct", "regime", "liquidity_class", "trend_direction"],
    )


def quality_for_features(payload: dict[str, Any]) -> DataQualityReport:
    registry = payload.get("feature_registry") or {}
    report = assess_completeness(
        payload,
        required=["symbol", "market", "timeframe", "candle_time"],
        optional=["final_score", "final_grade"],
    )
    if not registry:
        report.warnings.append("feature_registry empty — legacy groups-only snapshot")
    return report
