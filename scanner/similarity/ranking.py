# -*- coding: utf-8 -*-
"""Deterministic ranking of similarity matches."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .result import SimilarityMatch


@dataclass
class RankingWeights:
    """Explicit ranking weights — fully transparent."""

    similarity: float = 0.50
    data_quality: float = 0.20
    knowledge_confidence: float = 0.15
    recency: float = 0.15

    def to_dict(self) -> dict[str, float]:
        return {
            "similarity": self.similarity,
            "data_quality": self.data_quality,
            "knowledge_confidence": self.knowledge_confidence,
            "recency": self.recency,
        }


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _recency_score(candle_time: str, *,
                   reference: datetime | None = None) -> float:
    ts = _parse_ts(candle_time)
    if not ts:
        return 0.5
    ref = reference or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days = max(0, (ref - ts).days)
    return max(0.0, min(1.0, 1.0 - days / 365))


class RankingEngine:
    """Rank matches by composite deterministic score."""

    def __init__(self, weights: RankingWeights | None = None) -> None:
        self.weights = weights or RankingWeights()

    def rank(self, matches: list[SimilarityMatch], *,
             reference_time: datetime | None = None) -> list[SimilarityMatch]:
        w = self.weights.to_dict()
        for match in matches:
            match.recency_score = _recency_score(
                match.candle_time, reference=reference_time,
            )
            match.rank_score = (
                (match.similarity_score.overall / 100) * w["similarity"]
                + match.data_quality * w["data_quality"]
                + match.knowledge_confidence * w["knowledge_confidence"]
                + match.recency_score * w["recency"]
            )
        return sorted(matches, key=lambda m: m.rank_score, reverse=True)
