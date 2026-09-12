# -*- coding: utf-8 -*-
"""Similarity scoring — 0–100 with exposed component breakdown."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .feature_distance import FeatureDistance, FeatureDistanceCalculator


@dataclass
class ComponentWeights:
    """Explicit weights for overall similarity — no hidden math."""

    trend: float = 0.20
    liquidity: float = 0.15
    structure: float = 0.15
    volume: float = 0.15
    pattern: float = 0.15
    environment: float = 0.20

    def to_dict(self) -> dict[str, float]:
        return {
            "trend": self.trend,
            "liquidity": self.liquidity,
            "structure": self.structure,
            "volume": self.volume,
            "pattern": self.pattern,
            "environment": self.environment,
        }


@dataclass
class SimilarityScore:
    """0–100 similarity with explainable components."""

    overall: float = 0.0
    trend_similarity: float = 0.0
    liquidity_similarity: float = 0.0
    structure_similarity: float = 0.0
    volume_similarity: float = 0.0
    pattern_similarity: float = 0.0
    environment_similarity: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)
    explanation: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 2),
            "trend_similarity": round(self.trend_similarity, 2),
            "liquidity_similarity": round(self.liquidity_similarity, 2),
            "structure_similarity": round(self.structure_similarity, 2),
            "volume_similarity": round(self.volume_similarity, 2),
            "pattern_similarity": round(self.pattern_similarity, 2),
            "environment_similarity": round(self.environment_similarity, 2),
            "weights": dict(self.weights),
            "explanation": list(self.explanation),
        }


def _to_pct(similarity: float) -> float:
    return round(max(0.0, min(100.0, similarity * 100)), 2)


def _group_similarity(distance: FeatureDistance, keys: list[str]) -> float:
    if not keys:
        return 0.0
    scores = []
    for key in keys:
        detail = distance.details.get(key)
        if detail:
            scores.append(1.0 - detail["distance"])
    return sum(scores) / len(scores) if scores else 0.0


class SimilarityScorer:
    """Compute 0–100 similarity from feature distance + domain groups."""

    TREND_KEYS = ["htf_bias", "c_trend", "trend_component"]
    LIQUIDITY_KEYS = ["liquidity_class", "sweep_count", "c_obv"]
    STRUCTURE_KEYS = ["bos", "choch", "c_fib"]
    VOLUME_KEYS = ["rvol", "c_vwap", "c_spike", "c_obv_macd"]
    PATTERN_KEYS = ["pattern_count", "candle_count", "c_div"]
    ENVIRONMENT_KEYS = ["regime", "regime_score", "atr_pct", "volatility", "breadth_pct"]

    def __init__(self, *,
                 calculator: FeatureDistanceCalculator | None = None,
                 weights: ComponentWeights | None = None) -> None:
        self.calculator = calculator or FeatureDistanceCalculator()
        self.weights = weights or ComponentWeights()

    def score(self, query: dict[str, Any],
              candidate: dict[str, Any]) -> tuple[SimilarityScore, FeatureDistance]:
        distance = self.calculator.compare(query, candidate)

        components = {
            "trend": _group_similarity(distance, self.TREND_KEYS),
            "liquidity": _group_similarity(distance, self.LIQUIDITY_KEYS),
            "structure": _group_similarity(distance, self.STRUCTURE_KEYS),
            "volume": _group_similarity(distance, self.VOLUME_KEYS),
            "pattern": _group_similarity(distance, self.PATTERN_KEYS),
            "environment": _group_similarity(distance, self.ENVIRONMENT_KEYS),
        }

        w = self.weights.to_dict()
        overall_sim = sum(components[k] * w[k] for k in components)
        if sum(w.values()) > 0:
            overall_sim /= sum(w.values())

        explanation = [
            f"trend={_to_pct(components['trend'])}% (weight={w['trend']})",
            f"liquidity={_to_pct(components['liquidity'])}% (weight={w['liquidity']})",
            f"structure={_to_pct(components['structure'])}% (weight={w['structure']})",
            f"volume={_to_pct(components['volume'])}% (weight={w['volume']})",
            f"pattern={_to_pct(components['pattern'])}% (weight={w['pattern']})",
            f"environment={_to_pct(components['environment'])}% (weight={w['environment']})",
            f"matched_features={len(distance.matched)}",
            f"different_features={len(distance.different)}",
        ]

        score = SimilarityScore(
            overall=_to_pct(overall_sim),
            trend_similarity=_to_pct(components["trend"]),
            liquidity_similarity=_to_pct(components["liquidity"]),
            structure_similarity=_to_pct(components["structure"]),
            volume_similarity=_to_pct(components["volume"]),
            pattern_similarity=_to_pct(components["pattern"]),
            environment_similarity=_to_pct(components["environment"]),
            weights=w,
            explanation=explanation,
        )
        return score, distance
