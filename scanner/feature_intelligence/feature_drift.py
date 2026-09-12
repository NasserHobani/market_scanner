# -*- coding: utf-8 -*-
"""Feature drift detection — distribution, range, missing, category changes."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DriftResult:
    feature: str
    drift_score: float | None = None
    distribution_shift: float | None = None
    range_shift: float | None = None
    missing_rate_baseline: float | None = None
    missing_rate_current: float | None = None
    missing_rate_increase: float | None = None
    category_changes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "drift_score": self.drift_score,
            "distribution_shift": self.distribution_shift,
            "range_shift": self.range_shift,
            "missing_rate_baseline": self.missing_rate_baseline,
            "missing_rate_current": self.missing_rate_current,
            "missing_rate_increase": self.missing_rate_increase,
            "category_changes": list(self.category_changes),
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
        }


class FeatureDriftEngine:
    """Detect feature drift between baseline and current periods."""

    def compute(self, rows: list[dict[str, Any]], *,
                feature_names: list[str] | None = None,
                split_index: int | None = None) -> list[DriftResult]:
        if not rows:
            return []
        features = feature_names or _discover_features(rows)
        split = split_index if split_index is not None else len(rows) // 2
        baseline = rows[:split]
        current = rows[split:]
        if not baseline or not current:
            return [DriftResult(feature=f, warnings=["Cannot split into baseline/current"])
                    for f in features]
        return [self._compute_one(f, baseline, current) for f in features]

    def _compute_one(self, feature: str, baseline: list[dict],
                     current: list[dict]) -> DriftResult:
        evidence: list[str] = []
        warnings: list[str] = []

        b_vals = _numeric_values(feature, baseline)
        c_vals = _numeric_values(feature, current)

        dist_shift = _distribution_shift(b_vals, c_vals)
        if dist_shift is not None and dist_shift > 0.3:
            evidence.append(f"Distribution shift: {dist_shift:.3f}")
            warnings.append("Significant distribution change detected")

        range_shift = _range_shift(b_vals, c_vals)
        if range_shift is not None and range_shift > 0.2:
            evidence.append(f"Range shift: {range_shift:.3f}")

        miss_b = _missing_rate(feature, baseline)
        miss_c = _missing_rate(feature, current)
        miss_inc = round(miss_c - miss_b, 4) if miss_b is not None and miss_c is not None else None
        if miss_inc is not None and miss_inc > 0.1:
            evidence.append(f"Missing rate increased by {miss_inc:.1%}")
            warnings.append("Missing value rate increased significantly")

        cat_changes = _category_changes(feature, baseline, current)
        if cat_changes:
            evidence.append(f"New categories: {', '.join(cat_changes)}")
            warnings.append("Category distribution changed")

        parts = [p for p in (dist_shift, range_shift,
                              abs(miss_inc) if miss_inc else None) if p is not None]
        drift_score = round(sum(parts) / len(parts), 4) if parts else 0.0

        return DriftResult(
            feature=feature,
            drift_score=drift_score,
            distribution_shift=dist_shift,
            range_shift=range_shift,
            missing_rate_baseline=miss_b,
            missing_rate_current=miss_c,
            missing_rate_increase=miss_inc,
            category_changes=cat_changes,
            evidence=evidence,
            warnings=warnings,
        )


def _distribution_shift(baseline: list[float], current: list[float]) -> float | None:
    if len(baseline) < 3 or len(current) < 3:
        return None
    mean_b = sum(baseline) / len(baseline)
    mean_c = sum(current) / len(current)
    std_b = _stdev(baseline) or 1.0
    return round(min(abs(mean_c - mean_b) / std_b, 1.0), 4)


def _range_shift(baseline: list[float], current: list[float]) -> float | None:
    if not baseline or not current:
        return None
    range_b = max(baseline) - min(baseline)
    range_c = max(current) - min(current)
    if range_b == 0:
        return 0.0 if range_c == 0 else 1.0
    return round(min(abs(range_c - range_b) / range_b, 1.0), 4)


def _missing_rate(feature: str, rows: list[dict]) -> float | None:
    if not rows:
        return None
    missing = sum(1 for r in rows if _feature_val(r, feature) is None)
    return round(missing / len(rows), 4)


def _category_changes(feature: str, baseline: list[dict],
                      current: list[dict]) -> list[str]:
    b_cats = {str(_feature_val(r, feature)) for r in baseline
              if _feature_val(r, feature) is not None}
    c_cats = {str(_feature_val(r, feature)) for r in current
              if _feature_val(r, feature) is not None}
    new = c_cats - b_cats
    return sorted(new)


def _stdev(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))


def _feature_val(row: dict, feature: str) -> Any:
    if feature in row:
        return row[feature]
    return (row.get("features") or {}).get(feature)


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
