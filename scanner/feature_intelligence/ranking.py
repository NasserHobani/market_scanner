# -*- coding: utf-8 -*-
"""Deterministic feature ranking — exposed weights, no hidden scores."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .feature_drift import DriftResult
from .feature_importance import ImportanceResult
from .feature_stability import StabilityResult


# Exposed weights — no hidden calculations
RANKING_WEIGHTS = {
    "importance": 0.30,
    "stability": 0.25,
    "coverage": 0.15,
    "drift": 0.15,       # inverted: lower drift = higher score
    "data_quality": 0.10,
    "research_confidence": 0.05,
}


@dataclass
class RankedFeature:
    feature: str
    rank: int
    composite_score: float
    importance_score: float | None = None
    stability_score: float | None = None
    coverage_score: float | None = None
    drift_score: float | None = None
    data_quality_score: float | None = None
    research_confidence_score: float | None = None
    components: dict[str, float | None] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "rank": self.rank,
            "composite_score": self.composite_score,
            "importance_score": self.importance_score,
            "stability_score": self.stability_score,
            "coverage_score": self.coverage_score,
            "drift_score": self.drift_score,
            "data_quality_score": self.data_quality_score,
            "research_confidence_score": self.research_confidence_score,
            "components": dict(self.components),
            "notes": list(self.notes),
            "weights": dict(RANKING_WEIGHTS),
        }


class FeatureRankingEngine:
    """Rank features using importance, stability, coverage, drift, quality."""

    def rank(self, *,
             importance: list[ImportanceResult],
             stability: list[StabilityResult],
             drift: list[DriftResult],
             rows: list[dict[str, Any]],
             research_confidence: dict[str, float] | None = None) -> list[RankedFeature]:
        imp_map = {r.feature: r for r in importance}
        stab_map = {r.feature: r for r in stability}
        drift_map = {r.feature: r for r in drift}
        features = sorted(set(imp_map) | set(stab_map) | set(drift_map))

        ranked: list[RankedFeature] = []
        for feat in features:
            imp = imp_map.get(feat)
            stab = stab_map.get(feat)
            dr = drift_map.get(feat)

            imp_score = imp.statistical_importance if imp else None
            stab_score = stab.overall_stability if stab else None
            cov_score = self._coverage(feat, rows)
            drift_raw = dr.drift_score if dr else 0.0
            drift_inv = round(1.0 - min(drift_raw or 0.0, 1.0), 4)
            dq_score = self._data_quality(feat, rows)
            rc_score = (research_confidence or {}).get(feat)

            components = {
                "importance": imp_score,
                "stability": stab_score,
                "coverage": cov_score,
                "drift_inverted": drift_inv,
                "data_quality": dq_score,
                "research_confidence": rc_score,
            }

            composite = self._composite(components)
            notes: list[str] = []
            if cov_score is not None and cov_score < 0.5:
                notes.append("Low coverage")
            if drift_raw and drift_raw > 0.5:
                notes.append("High drift detected")

            ranked.append(RankedFeature(
                feature=feat,
                rank=0,
                composite_score=composite,
                importance_score=imp_score,
                stability_score=stab_score,
                coverage_score=cov_score,
                drift_score=drift_raw,
                data_quality_score=dq_score,
                research_confidence_score=rc_score,
                components=components,
                notes=notes,
            ))

        ranked.sort(key=lambda r: r.composite_score, reverse=True)
        for i, r in enumerate(ranked, 1):
            r.rank = i
        return ranked

    def _composite(self, components: dict[str, float | None]) -> float:
        total = 0.0
        weight_sum = 0.0
        mapping = {
            "importance": "importance",
            "stability": "stability",
            "coverage": "coverage",
            "drift_inverted": "drift",
            "data_quality": "data_quality",
            "research_confidence": "research_confidence",
        }
        for comp_key, weight_key in mapping.items():
            val = components.get(comp_key)
            w = RANKING_WEIGHTS[weight_key]
            if val is not None:
                total += val * w
                weight_sum += w
        return round(total / weight_sum, 4) if weight_sum > 0 else 0.0

    @staticmethod
    def _coverage(feature: str, rows: list[dict]) -> float | None:
        if not rows:
            return None
        present = sum(1 for r in rows if _feature_val(r, feature) is not None)
        return round(present / len(rows), 4)

    @staticmethod
    def _data_quality(feature: str, rows: list[dict]) -> float | None:
        if not rows:
            return None
        missing = sum(1 for r in rows if _feature_val(r, feature) is None)
        missing_rate = missing / len(rows)
        return round(1.0 - missing_rate, 4)


def _feature_val(row: dict, feature: str) -> Any:
    if feature in row:
        return row[feature]
    return (row.get("features") or {}).get(feature)
