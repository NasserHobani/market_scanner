# -*- coding: utf-8 -*-
"""Honest historical snapshot reconstruction from legacy flat snapshots."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .builder import build_snapshot
from .contract import SnapshotStatus
from .store import get_by_legacy, save
from .observability import log_event

log = logging.getLogger("scanner.feature_snapshots.historical")
LEGACY_STORE = Path("data/features/snapshots.jsonl")


def _load_legacy(fs_id: str) -> dict[str, Any] | None:
    if not LEGACY_STORE.exists():
        return None
    for line in LEGACY_STORE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("snapshot_id") == fs_id:
            return row
    return None


def legacy_to_source(row: dict[str, Any]) -> dict[str, Any]:
    feats = row.get("features") or {}
    decision_ts = str(row.get("candle_time") or row.get("written_at") or "")
    return {
        "symbol": row.get("symbol", ""),
        "market": row.get("market", ""),
        "timeframe": row.get("timeframe", ""),
        "decision_timestamp": decision_ts,
        "feature_timestamp": decision_ts,
        "candle_time": decision_ts,
        "score": row.get("score"),
        "htf": row.get("htf"),
        "recommendation": {
            "action": row.get("action"),
            "grade": row.get("grade"),
            "confidence": row.get("confidence"),
            "rr": row.get("rr"),
            "side": "buy" if str(row.get("action", "")).lower() in ("buy", "long") else "sell",
        },
        "features": feats,
        "rsi": feats.get("rsi"),
        "rvol": feats.get("rvol"),
        "atr_pct": feats.get("atr_pct"),
    }


def reconstruct_from_trade(trade: dict[str, Any]) -> dict[str, Any]:
    """Return status dict — never fabricate when data missing."""
    fs_id = trade.get("feature_snapshot_id") or ""
    if not fs_id:
        return {
            "trade_id": trade.get("trade_id", ""),
            "status": SnapshotStatus.HISTORICAL_UNAVAILABLE.value,
            "reason": "no legacy snapshot id",
        }

    existing = get_by_legacy(fs_id)
    if existing:
        return {
            "trade_id": trade.get("trade_id", ""),
            "status": existing.status,
            "snapshot_id": existing.snapshot_id,
            "reused": True,
        }

    legacy = _load_legacy(fs_id)
    if not legacy:
        log_event(
            "SNAPSHOT_REJECTED",
            symbol=str(trade.get("symbol", "")),
            timeframe=str(trade.get("timeframe", "")),
            recommendation_id=fs_id,
            reason="legacy snapshot not found",
        )
        return {
            "trade_id": trade.get("trade_id", ""),
            "status": SnapshotStatus.HISTORICAL_UNAVAILABLE.value,
            "reason": "legacy snapshot not found",
        }

    source = legacy_to_source(legacy)
    snap = build_snapshot(
        source,
        legacy_snapshot_id=fs_id,
        status=SnapshotStatus.HISTORICAL_RECONSTRUCTED.value,
    )
    if snap.snapshot_id and snap.status != SnapshotStatus.REJECTED.value:
        save(snap)
        log_event(
            "SNAPSHOT_CREATED",
            symbol=snap.symbol,
            timeframe=snap.timeframe,
            snapshot_id=snap.snapshot_id,
            recommendation_id=fs_id,
            extra={"historical": True},
        )
    return {
        "trade_id": trade.get("trade_id", ""),
        "status": snap.status,
        "snapshot_id": snap.snapshot_id,
        "coverage": snap.coverage,
    }


def batch_reconstruct(trades: list[dict[str, Any]]) -> dict[str, Any]:
    results = [reconstruct_from_trade(t) for t in trades]
    original = sum(1 for t in trades if t.get("feature_snapshot_id"))
    reconstructed = sum(
        1 for r in results
        if r.get("snapshot_id") and r.get("status") != SnapshotStatus.HISTORICAL_UNAVAILABLE.value
    )
    unavailable = sum(
        1 for r in results if r.get("status") == SnapshotStatus.HISTORICAL_UNAVAILABLE.value
    )
    return {
        "original_snapshot_count": original,
        "reconstructed_snapshot_count": reconstructed,
        "unavailable_count": unavailable,
        "results": results[:50],
    }
