# -*- coding: utf-8 -*-
"""Configurable thresholds for runtime PIT snapshot validation (AIA-10.5)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSnapshotConfig:
    """Runtime quality gates — configurable, not model quality gates."""

    good_coverage_min: float = 0.90
    partial_coverage_min: float = 0.70
    runtime_coverage_target: float = 0.80
    latency_target_ms: float = 100.0
    v3_smoke_min_rows: int = 20
    v3_train_min_rows: int = 100
    v3_preferred_rows: int = 200
    # After a completed V3 evaluation, require this many new eligible rows
    v3_retrain_delta: int = 20
    total_v3_features: int = 36


DEFAULT_RUNTIME_CONFIG = RuntimeSnapshotConfig()
