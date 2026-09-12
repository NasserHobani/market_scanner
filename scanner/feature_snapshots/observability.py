# -*- coding: utf-8 -*-
"""Traceable snapshot lifecycle events."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENTS_PATH = Path("data/feature_snapshots/events.jsonl")
log = logging.getLogger("scanner.feature_snapshots")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, *, symbol: str = "", timeframe: str = "",
              recommendation_id: str = "", snapshot_id: str = "",
              timestamp: str = "", reason: str = "", extra: dict[str, Any] | None = None) -> None:
    row = {
        "event": event,
        "symbol": symbol,
        "timeframe": timeframe,
        "recommendation_id": recommendation_id,
        "snapshot_id": snapshot_id,
        "timestamp": timestamp or _now(),
        "reason": reason,
        **(extra or {}),
    }
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    log.info(
        "%s symbol=%s tf=%s snap=%s reason=%s",
        event, symbol, timeframe, snapshot_id, reason[:80] if reason else "",
    )


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    lines = [ln for ln in EVENTS_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    out = [json.loads(ln) for ln in lines[-limit:]]
    return out
