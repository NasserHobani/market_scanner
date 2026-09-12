# -*- coding: utf-8 -*-
"""Feature stability measurement — deterministic, no ML."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StabilityResult:
    feature: str
    overall_stability: float | None = None
    monthly_stability: float | None = None
    rolling_stability: float | None = None
    market_stability: float | None = None
    timeframe_stability: float | None = None
    version_stability: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "overall_stability": self.overall_stability,
            "monthly_stability": self.monthly_stability,
            "rolling_stability": self.rolling_stability,
            "market_stability": self.market_stability,
            "timeframe_stability": self.timeframe_stability,
            "version_stability": self.version_stability,
            "details": dict(self.details),
            "notes": list(self.notes),
        }


class FeatureStabilityEngine:
    """Measure feature stability across time, market, and version dimensions."""

    def compute(self, rows: list[dict[str, Any]], *,
                feature_names: list[str] | None = None,
                rolling_window: int = 10) -> list[StabilityResult]:
        if not rows:
            return []
        features = feature_names or _discover_features(rows)
        return [self._compute_one(f, rows, rolling_window) for f in features]

    def _compute_one(self, feature: str, rows: list[dict],
                     window: int) -> StabilityResult:
        vals = _numeric_values(feature, rows)
        notes: list[str] = []
        if len(vals) < 5:
            notes.append("Insufficient data for stability (n<5)")

        monthly = self._monthly_stability(feature, rows)
        rolling = self._rolling_stability(feature, rows, window)
        market = self._group_stability(feature, rows, "market")
        tf = self._group_stability(feature, rows, "timeframe")
        version = self._group_stability(feature, rows, "feature_version")

        scores = [s for s in (monthly, rolling, market, tf, version) if s is not None]
        overall = round(sum(scores) / len(scores), 4) if scores else None

        return StabilityResult(
            feature=feature,
            overall_stability=overall,
            monthly_stability=monthly,
            rolling_stability=rolling,
            market_stability=market,
            timeframe_stability=tf,
            version_stability=version,
            details={
                "sample_size": len(vals),
                "global_mean": round(sum(vals) / len(vals), 4) if vals else None,
                "global_stdev": _stdev(vals),
            },
            notes=notes,
        )

    def _monthly_stability(self, feature: str, rows: list[dict]) -> float | None:
        by_month: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            v = _feature_val(row, feature)
            if v is None:
                continue
            ts = _extract_timestamp(row)
            if ts:
                by_month[ts.strftime("%Y-%m")].append(float(v))
        if len(by_month) < 2:
            return None
        means = [sum(vs) / len(vs) for vs in by_month.values()]
        return _stability_from_means(means)

    def _rolling_stability(self, feature: str, rows: list[dict],
                           window: int) -> float | None:
        vals = _numeric_values(feature, rows)
        if len(vals) < window * 2:
            return None
        means: list[float] = []
        for i in range(0, len(vals) - window + 1):
            chunk = vals[i:i + window]
            means.append(sum(chunk) / len(chunk))
        return _stability_from_means(means)

    def _group_stability(self, feature: str, rows: list[dict],
                         group_key: str) -> float | None:
        groups: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            v = _feature_val(row, feature)
            if v is None:
                continue
            g = _meta_val(row, group_key) or "unknown"
            groups[str(g)].append(float(v))
        if len(groups) < 2:
            return None
        means = [sum(vs) / len(vs) for vs in groups.values()]
        return _stability_from_means(means)


def _stability_from_means(means: list[float]) -> float | None:
    """Higher score = more stable (lower coefficient of variation)."""
    if len(means) < 2:
        return None
    avg = sum(means) / len(means)
    if avg == 0:
        return 1.0 if all(m == 0 for m in means) else 0.0
    sd = _stdev(means)
    if sd is None:
        return 1.0
    cv = sd / abs(avg)
    return round(max(0.0, 1.0 - min(cv, 1.0)), 4)


def _stdev(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return round(math.sqrt(var), 4)


def _feature_val(row: dict, feature: str) -> Any:
    if feature in row:
        return row[feature]
    return (row.get("features") or {}).get(feature)


def _meta_val(row: dict, key: str) -> Any:
    meta = row.get("_meta") or row.get("meta") or {}
    return meta.get(key) or row.get(key)


def _extract_timestamp(row: dict) -> datetime | None:
    for key in ("closed_at", "signal_at", "candle_time", "created_at"):
        val = row.get(key) or (_meta_val(row, key))
        if val is None:
            continue
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
    return None


def _numeric_values(feature: str, rows: list[dict]) -> list[float]:
    out: list[float] = []
    for row in rows:
        v = _feature_val(row, feature)
        if v is not None and isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _discover_features(rows: list[dict]) -> list[str]:
    from .feature_importance import FeatureImportanceEngine
    return FeatureImportanceEngine._discover_features(rows)
