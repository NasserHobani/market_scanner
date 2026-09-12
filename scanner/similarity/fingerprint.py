# -*- coding: utf-8 -*-
"""Deterministic situational fingerprints — explainable, stable, comparable."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def _bucket_atr(atr_pct: float | None) -> str:
    if atr_pct is None:
        return "unknown"
    if atr_pct < 1.5:
        return "low"
    if atr_pct < 3.0:
        return "normal"
    if atr_pct < 5.0:
        return "elevated"
    return "high"


def _bucket_score(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 50:
        return "weak"
    if score < 65:
        return "moderate"
    if score < 80:
        return "strong"
    return "elite"


@dataclass
class SituationalFingerprint:
    """Explainable fingerprint — components are human-readable."""

    fingerprint_id: str
    components: dict[str, Any] = field(default_factory=dict)
    comparison_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint_id": self.fingerprint_id,
            "components": dict(self.components),
            "comparison_key": self.comparison_key,
        }


def build_fingerprint(source: dict[str, Any]) -> SituationalFingerprint:
    """Build explainable fingerprint from scan source or snapshot payload."""
    market_ctx = source.get("market_context") or {}
    ctx = source.get("context") or source.get("score_context") or {}
    groups = source.get("groups") or {}
    trend = groups.get("trend") or {}
    liquidity = groups.get("liquidity") or {}
    structure = groups.get("market_structure") or {}
    volume = groups.get("volume") or {}
    patterns = groups.get("patterns") or {}
    reco = source.get("recommendation") or {}

    components = {
        "symbol": source.get("symbol"),
        "market": source.get("market"),
        "timeframe": source.get("timeframe"),
        "regime": source.get("regime") or market_ctx.get("regime"),
        "regime_score": source.get("regime_score") or market_ctx.get("regime_score"),
        "trend_direction": (
            source.get("trend_direction")
            or trend.get("price_action_trend")
            or trend.get("htf_text")
        ),
        "htf_bias": source.get("htf_bias") or source.get("htf") or trend.get("htf_bias"),
        "atr_bucket": _bucket_atr(
            source.get("atr_pct") or ctx.get("atr_pct")
        ),
        "liquidity_class": (
            source.get("liquidity_class")
            or source.get("liquidity")
            or liquidity.get("class")
        ),
        "volatility": (
            source.get("volatility")
            or market_ctx.get("volatility")
        ),
        "breadth_bucket": _bucket_score(market_ctx.get("breadth_pct")),
        "structure_bos": bool(structure.get("bos")),
        "structure_choch": bool(structure.get("choch")),
        "sweep_count": len(liquidity.get("sweeps") or []),
        "pattern_count": len(patterns.get("chart_patterns") or patterns.get("candlestick") or []),
        "candle_count": len(patterns.get("candlestick") or reco.get("analysis", {}).get("candles") or []),
        "rvol_bucket": _bucket_score(ctx.get("rvol")),
        "grade": source.get("final_grade") or source.get("grade") or reco.get("grade"),
        "side": reco.get("side") or source.get("side"),
    }

    comparison_key = "|".join(
        f"{k}={components[k]}" for k in sorted(components.keys())
        if components[k] is not None
    )
    raw = json.dumps(_normalize(components), sort_keys=True, default=str).encode("utf-8")
    fp_id = f"sf_{hashlib.sha256(raw).hexdigest()[:24]}"

    return SituationalFingerprint(
        fingerprint_id=fp_id,
        components=components,
        comparison_key=comparison_key,
    )


def fingerprint_match_score(a: SituationalFingerprint,
                            b: SituationalFingerprint) -> float:
    """Quick component-match score 0–1 for pre-filtering."""
    if a.comparison_key == b.comparison_key:
        return 1.0
    keys = set(a.components) | set(b.components)
    if not keys:
        return 0.0
    matches = sum(
        1 for k in keys
        if a.components.get(k) == b.components.get(k)
        and a.components.get(k) is not None
    )
    return matches / len(keys)
