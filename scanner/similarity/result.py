# -*- coding: utf-8 -*-
"""Structured similarity result objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fingerprint import SituationalFingerprint
from .feature_distance import FeatureDistance
from .similarity_score import SimilarityScore


@dataclass
class SimilarityMatch:
    """Single matched historical situation."""

    event_id: str
    symbol: str
    market: str
    timeframe: str
    similarity_score: SimilarityScore
    feature_distance: FeatureDistance
    fingerprint: SituationalFingerprint
    matched_features: list[str] = field(default_factory=list)
    different_features: list[str] = field(default_factory=list)
    historical_outcome: str = ""
    expected_r: float | None = None
    win_rate: float | None = None
    trade_count: int = 0
    supporting_evidence: list[str] = field(default_factory=list)
    rank_score: float = 0.0
    data_quality: float = 1.0
    knowledge_confidence: float = 1.0
    recency_score: float = 0.0
    candle_time: str = ""
    outcome_class: str = ""
    r_multiple: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "similarity_score": self.similarity_score.to_dict(),
            "feature_distance": self.feature_distance.to_dict(),
            "fingerprint": self.fingerprint.to_dict(),
            "matched_features": list(self.matched_features),
            "different_features": list(self.different_features),
            "historical_outcome": self.historical_outcome,
            "expected_r": self.expected_r,
            "win_rate": self.win_rate,
            "trade_count": self.trade_count,
            "supporting_evidence": list(self.supporting_evidence),
            "rank_score": round(self.rank_score, 4),
            "data_quality": round(self.data_quality, 4),
            "knowledge_confidence": round(self.knowledge_confidence, 4),
            "recency_score": round(self.recency_score, 4),
            "candle_time": self.candle_time,
            "outcome_class": self.outcome_class,
            "r_multiple": self.r_multiple,
        }


@dataclass
class SimilarityResult:
    """Full retrieval result."""

    query_event_id: str = ""
    query_fingerprint: SituationalFingerprint | None = None
    matches: list[SimilarityMatch] = field(default_factory=list)
    total_candidates: int = 0
    filtered_candidates: int = 0
    top_n: int = 10
    filters_applied: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_event_id": self.query_event_id,
            "query_fingerprint": (self.query_fingerprint.to_dict()
                                  if self.query_fingerprint else None),
            "count": len(self.matches),
            "total_candidates": self.total_candidates,
            "filtered_candidates": self.filtered_candidates,
            "top_n": self.top_n,
            "filters_applied": dict(self.filters_applied),
            "statistics": dict(self.statistics),
            "matches": [m.to_dict() for m in self.matches],
        }

    def top(self, n: int = 5) -> list[SimilarityMatch]:
        return self.matches[:n]
