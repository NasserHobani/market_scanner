# -*- coding: utf-8 -*-
"""Point-in-time feature snapshots — Dataset V3 foundation."""
from .contract import (
    FEATURE_SCHEMA_VERSION_V3,
    SNAPSHOT_VERSION_V3,
    FeatureProvenance,
    PointInTimeSnapshot,
    SnapshotQualityStatus,
    SnapshotStatus,
)
from .config import DEFAULT_RUNTIME_CONFIG, RuntimeSnapshotConfig
from .runtime_audit import (
    analyze_feature_coverage,
    classify_runtime_quality,
    dataset_eligibility_report,
    full_runtime_report,
    make_recommendation_id,
)

from .service import PointInTimeSnapshotService

__all__ = [
    "DEFAULT_RUNTIME_CONFIG",
    "FEATURE_SCHEMA_VERSION_V3",
    "SNAPSHOT_VERSION_V3",
    "FeatureProvenance",
    "PointInTimeSnapshot",
    "PointInTimeSnapshotService",
    "RuntimeSnapshotConfig",
    "SnapshotQualityStatus",
    "SnapshotStatus",
    "analyze_feature_coverage",
    "classify_runtime_quality",
    "dataset_eligibility_report",
    "full_runtime_report",
    "make_recommendation_id",
]
