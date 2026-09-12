# -*- coding: utf-8 -*-
"""Stable market-state fingerprints for future similarity search."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def market_fingerprint(payload: dict[str, Any]) -> str:
    """Deterministic fingerprint for a market snapshot or environment.

    Uses only fields that describe market state — not IDs or timestamps.
    """
    ohlcv = payload.get("ohlcv") or {}
    core = {
        "symbol": payload.get("symbol"),
        "market": payload.get("market"),
        "timeframe": payload.get("timeframe"),
        "close": ohlcv.get("close") or payload.get("close"),
        "regime": payload.get("regime") or payload.get("market_regime"),
        "regime_score": payload.get("regime_score"),
        "trend_direction": payload.get("trend_direction") or payload.get("trend_state"),
        "htf_bias": payload.get("htf_bias"),
        "atr_pct": payload.get("atr_pct"),
        "liquidity_class": payload.get("liquidity_class"),
        "volatility": payload.get("volatility") or payload.get("volatility_class"),
        "breadth_pct": payload.get("breadth_pct") or payload.get("market_breadth"),
    }
    raw = json.dumps(_normalize(core), sort_keys=True, default=str).encode("utf-8")
    return f"mf_{hashlib.sha256(raw).hexdigest()[:24]}"
