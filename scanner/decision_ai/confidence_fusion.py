# -*- coding: utf-8 -*-
"""Confidence fusion — combine all layer confidences with exposed weights."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Exposed weights — no hidden calculations
FUSION_WEIGHTS = {
    "reasoning": 0.30,
    "similarity": 0.20,
    "prediction": 0.20,
    "research": 0.15,
    "feature_intelligence": 0.15,
}


@dataclass
class FusedConfidence:
    """Overall decision confidence with component breakdown."""

    overall: float = 0.0
    components: dict[str, float | None] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    sources_available: list[str] = field(default_factory=list)
    sources_missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "overall_pct": round(self.overall * 100, 1),
            "components": {k: round(v, 4) if v is not None else None
                           for k, v in self.components.items()},
            "weights": dict(self.weights),
            "sources_available": list(self.sources_available),
            "sources_missing": list(self.sources_missing),
            "notes": list(self.notes),
        }


class ConfidenceFusion:
    """Fuse confidence from reasoning, similarity, prediction, research, features."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = dict(weights or FUSION_WEIGHTS)

    def fuse(self, context: dict[str, Any]) -> FusedConfidence:
        components: dict[str, float | None] = {
            "reasoning": self._reasoning_confidence(context.get("reasoning") or {}),
            "similarity": self._similarity_confidence(context.get("similarity") or {}),
            "prediction": self._prediction_confidence(context.get("prediction") or {}),
            "research": self._research_confidence(context.get("research") or {}),
            "feature_intelligence": self._feature_confidence(
                context.get("feature_intelligence") or {}),
        }

        available = [k for k, v in components.items() if v is not None]
        missing = [k for k, v in components.items() if v is None]
        notes: list[str] = []

        total = 0.0
        weight_sum = 0.0
        for key, val in components.items():
            w = self._weights.get(key, 0.0)
            if val is not None:
                total += val * w
                weight_sum += w
            else:
                notes.append(f"Missing confidence source: {key}")

        overall = round(total / weight_sum, 4) if weight_sum > 0 else 0.0
        if len(available) < 3:
            notes.append(f"Only {len(available)}/5 confidence sources available")

        return FusedConfidence(
            overall=overall,
            components=components,
            weights=dict(self._weights),
            sources_available=available,
            sources_missing=missing,
            notes=notes,
        )

    @staticmethod
    def _reasoning_confidence(reasoning: dict) -> float | None:
        conf = reasoning.get("confidence") or {}
        if isinstance(conf, dict) and conf.get("overall") is not None:
            return float(conf["overall"])
        if reasoning.get("engine_confidence") is not None:
            return float(reasoning["engine_confidence"])
        return None

    @staticmethod
    def _similarity_confidence(similarity: dict) -> float | None:
        if not similarity.get("available"):
            return None
        count = similarity.get("match_count") or 0
        if count == 0:
            return 0.0
        return min(1.0, count / 10.0)

    @staticmethod
    def _prediction_confidence(prediction: dict) -> float | None:
        if not prediction:
            return None
        if prediction.get("confidence") is not None:
            return float(prediction["confidence"])
        if prediction.get("probability") is not None:
            p = float(prediction["probability"])
            return max(p, 1 - p)
        return None

    @staticmethod
    def _research_confidence(research: dict) -> float | None:
        if not research:
            return None
        ds = research.get("dataset_summary") or {}
        n = ds.get("closed_count") or ds.get("count") or 0
        if n < 5:
            return 0.2
        if n < 20:
            return 0.5
        return 0.7

    @staticmethod
    def _feature_confidence(fi: dict) -> float | None:
        if not fi:
            return None
        ranking = fi.get("ranking") or []
        if ranking and isinstance(ranking, list) and isinstance(ranking[0], dict):
            return float(ranking[0].get("composite_score") or 0.5)
        return 0.5
