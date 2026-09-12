# -*- coding: utf-8 -*-
"""Confidence built from weighted evidence — reproducible, no magic."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evidence import EvidenceBundle, EvidenceCategory, EvidenceDirection


DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    EvidenceCategory.TREND.value: 0.30,
    EvidenceCategory.LIQUIDITY.value: 0.20,
    EvidenceCategory.VOLUME.value: 0.15,
    EvidenceCategory.STRUCTURE.value: 0.20,
    EvidenceCategory.HISTORY.value: 0.15,
}

# Regime and momentum fold into breakdown but use sub-weights of trend/volume pools
_AUX_WEIGHTS: dict[str, float] = {
    EvidenceCategory.REGIME.value: 0.10,
    EvidenceCategory.MOMENTUM.value: 0.10,
    EvidenceCategory.CONFLUENCE.value: 0.10,
    EvidenceCategory.RISK.value: 0.10,
}


@dataclass
class ConfidenceBreakdown:
    """Per-category contribution to overall confidence."""

    overall: float = 0.0
    categories: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    supporting_ratio: float = 0.0
    contradiction_penalty: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 4),
            "overall_pct": round(self.overall * 100, 1),
            "categories": {k: round(v, 4) for k, v in self.categories.items()},
            "weights": dict(self.weights),
            "supporting_ratio": round(self.supporting_ratio, 4),
            "contradiction_penalty": round(self.contradiction_penalty, 4),
        }


class ConfidenceEngine:
    """Aggregates evidence into a transparent confidence score."""

    def __init__(self, *, weights: dict[str, float] | None = None) -> None:
        self.weights = dict(weights or DEFAULT_CATEGORY_WEIGHTS)

    def compute(self, bundle: EvidenceBundle, *,
                contradiction_count: int = 0) -> ConfidenceBreakdown:
        categories: dict[str, float] = {}
        used_weights: dict[str, float] = {}

        all_weights = {**self.weights, **_AUX_WEIGHTS}
        for cat, weight in all_weights.items():
            items = bundle.by_category(cat)
            if not items:
                categories[cat] = 0.0
                used_weights[cat] = weight
                continue
            # Category score = avg(confidence * direction_sign)
            scores = []
            for e in items:
                sign = 1.0 if e.direction == EvidenceDirection.SUPPORTS.value else (
                    -0.5 if e.direction == EvidenceDirection.CONTRADICTS.value else 0.0)
                scores.append(e.confidence * sign)
            cat_score = sum(scores) / len(scores) if scores else 0.0
            cat_score = max(0.0, min(1.0, (cat_score + 1) / 2))
            categories[cat] = cat_score
            used_weights[cat] = weight

        total_w = sum(used_weights.values()) or 1.0
        weighted = sum(categories.get(c, 0) * used_weights.get(c, 0) for c in used_weights)
        overall = weighted / total_w

        sup = len(bundle.supporting())
        con = len(bundle.contradicting())
        total = sup + con + len(bundle.neutral()) or 1
        supporting_ratio = sup / total

        penalty = min(0.35, contradiction_count * 0.08 + con * 0.04)
        overall = max(0.0, min(1.0, overall - penalty))

        return ConfidenceBreakdown(
            overall=overall,
            categories=categories,
            weights=used_weights,
            supporting_ratio=supporting_ratio,
            contradiction_penalty=penalty,
        )


class ConfidenceProvider(ConfidenceEngine):
    """Protocol-facing alias."""

    pass
