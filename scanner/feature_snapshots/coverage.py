# -*- coding: utf-8 -*-
"""Snapshot coverage — historical vs runtime reported separately."""
from __future__ import annotations

from typing import Any

from .contract import SNAPSHOT_VERSION_V3, SnapshotStatus
from .store import iter_snapshots, load_index


def runtime_snapshots() -> list[dict[str, Any]]:
    return [
        s.to_dict() for s in iter_snapshots()
        if s.snapshot_version == SNAPSHOT_VERSION_V3
        and s.status in (
            SnapshotStatus.CREATED.value,
            SnapshotStatus.PARTIAL.value,
            SnapshotStatus.HISTORICAL_RECONSTRUCTED.value,
        )
    ]


def coverage_report(*, closed_trades: list[dict[str, Any]],
                    deploy_marker: str = "") -> dict[str, Any]:
    """Measure historical reconstruction vs runtime capture separately."""
    idx = load_index()
    by_legacy = idx.get("by_legacy") or {}
    pit_all = iter_snapshots()

    historical_with_fs = 0
    historical_reconstructed = 0
    historical_unavailable = 0
    runtime_created = 0
    runtime_partial = 0
    runtime_failed = 0

    for trade in closed_trades:
        fs_id = trade.get("feature_snapshot_id") or ""
        pit_id = by_legacy.get(fs_id) if fs_id else ""
        if pit_id:
            historical_reconstructed += 1
        elif fs_id:
            historical_with_fs += 1
        else:
            historical_unavailable += 1

    for snap in pit_all:
        if snap.status == SnapshotStatus.HISTORICAL_RECONSTRUCTED.value:
            continue
        if deploy_marker and snap.created_at < deploy_marker:
            continue
        if snap.status == SnapshotStatus.CREATED.value:
            runtime_created += 1
        elif snap.status == SnapshotStatus.PARTIAL.value:
            runtime_partial += 1
        elif snap.status in (SnapshotStatus.FAILED.value, SnapshotStatus.REJECTED.value):
            runtime_failed += 1

    total_closed = len(closed_trades)
    hist_covered = historical_reconstructed + historical_with_fs
    runtime_total = runtime_created + runtime_partial + runtime_failed
    runtime_ok = runtime_created + runtime_partial

    return {
        "historical": {
            "total_closed_trades": total_closed,
            "with_legacy_fs_id": historical_with_fs,
            "reconstructed_pit": historical_reconstructed,
            "unavailable": historical_unavailable,
            "coverage_pct": round(hist_covered / total_closed * 100, 2) if total_closed else 0.0,
        },
        "runtime": {
            "created": runtime_created,
            "partial": runtime_partial,
            "failed": runtime_failed,
            "total_attempts": runtime_total,
            "coverage_pct": round(runtime_ok / runtime_total * 100, 2) if runtime_total else 0.0,
            "status": "WARNING" if runtime_total and runtime_ok / runtime_total < 0.8 else "OK",
        },
        "pit_snapshot_count": len(pit_all),
    }
