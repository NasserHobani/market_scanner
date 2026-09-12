# -*- coding: utf-8 -*-
"""Shared metadata types for ML foundation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

ML_FOUNDATION_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
FEATURE_VERSION = "1.0.0"
LABEL_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DatasetMetadata:
    """Traceable metadata for every exported dataset."""

    dataset_id: str
    schema_version: str = SCHEMA_VERSION
    feature_version: str = FEATURE_VERSION
    label_version: str = LABEL_VERSION
    research_experiment_id: str = ""
    created_at: str = ""
    row_count: int = 0
    feature_count: int = 0
    label_columns: list[str] = field(default_factory=list)
    filters_applied: list[str] = field(default_factory=list)
    fingerprint: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "schema_version": self.schema_version,
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "research_experiment_id": self.research_experiment_id,
            "created_at": self.created_at or _now(),
            "row_count": self.row_count,
            "feature_count": self.feature_count,
            "label_columns": list(self.label_columns),
            "filters_applied": list(self.filters_applied),
            "fingerprint": self.fingerprint,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> DatasetMetadata:
        return cls(
            dataset_id=row["dataset_id"],
            schema_version=row.get("schema_version") or SCHEMA_VERSION,
            feature_version=row.get("feature_version") or FEATURE_VERSION,
            label_version=row.get("label_version") or LABEL_VERSION,
            research_experiment_id=row.get("research_experiment_id") or "",
            created_at=row.get("created_at") or "",
            row_count=int(row.get("row_count") or 0),
            feature_count=int(row.get("feature_count") or 0),
            label_columns=list(row.get("label_columns") or []),
            filters_applied=list(row.get("filters_applied") or []),
            fingerprint=row.get("fingerprint") or "",
            extra=dict(row.get("extra") or {}),
        )


@dataclass
class ExportMetadata:
    """Metadata attached to every export file."""

    dataset_id: str
    format: str
    exported_at: str = ""
    schema_version: str = SCHEMA_VERSION
    feature_version: str = FEATURE_VERSION
    label_version: str = LABEL_VERSION
    column_order: list[str] = field(default_factory=list)
    row_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "format": self.format,
            "exported_at": self.exported_at or _now(),
            "schema_version": self.schema_version,
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "column_order": list(self.column_order),
            "row_count": self.row_count,
        }
