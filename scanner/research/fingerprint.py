# -*- coding: utf-8 -*-
"""Deterministic dataset fingerprints for duplicate protection."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_dataset_fingerprint(rows: list[dict[str, Any]],
                                configuration: dict[str, Any] | None = None,
                                *, hypothesis_id: str = "") -> str:
    """Fingerprint from trade IDs, timestamps, strategy scope, and config."""
    trade_keys = []
    for r in rows:
        tid = r.get("trade_id") or r.get("event_id") or r.get("symbol", "")
        closed = str(r.get("closed_at") or "")
        trade_keys.append(f"{tid}:{closed}")
    trade_keys.sort()

    payload = {
        "trade_keys": trade_keys,
        "count": len(rows),
        "markets": sorted({str(r.get("market", "")) for r in rows if r.get("market")}),
        "timeframes": sorted({str(r.get("timeframe", "")) for r in rows if r.get("timeframe")}),
        "configuration": configuration or {},
        "hypothesis_id": hypothesis_id,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    return f"dsfp_{digest}"
