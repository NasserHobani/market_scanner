# -*- coding: utf-8 -*-
"""Shared pipeline execution context — immutable downstream contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


NO_HISTORICAL_EVIDENCE = "No Historical Evidence"


@dataclass(frozen=True)
class SimilarityContext:
    """Similarity data passed to Reasoning and Intelligence stages."""

    similarity_result: dict[str, Any] = field(default_factory=dict)
    similarity_statistics: dict[str, Any] = field(default_factory=dict)
    match_count: int = 0
    average_win_rate: float | None = None
    average_r: float | None = None
    historical_evidence: tuple[str, ...] = ()
    historical_warnings: tuple[str, ...] = ()
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "similarity_result": dict(self.similarity_result),
            "similarity_statistics": dict(self.similarity_statistics),
            "match_count": self.match_count,
            "average_win_rate": self.average_win_rate,
            "average_r": self.average_r,
            "historical_evidence": list(self.historical_evidence),
            "historical_warnings": list(self.historical_warnings),
            "available": self.available,
        }


@dataclass(frozen=True)
class SimilaritySummary:
    """Persisted similarity references — no full historical records."""

    match_count: int = 0
    avg_similarity: float | None = None
    avg_r: float | None = None
    win_rate: float | None = None
    query_fingerprint_id: str = ""
    top_matches: tuple[dict[str, Any], ...] = ()
    event_id: str = ""
    knowledge_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_count": self.match_count,
            "avg_similarity": self.avg_similarity,
            "avg_r": self.avg_r,
            "win_rate": self.win_rate,
            "query_fingerprint_id": self.query_fingerprint_id,
            "top_matches": [dict(m) for m in self.top_matches],
            "event_id": self.event_id,
            "knowledge_event_id": self.knowledge_event_id,
        }


def empty_similarity_context() -> SimilarityContext:
    return SimilarityContext(
        historical_evidence=(NO_HISTORICAL_EVIDENCE,),
        available=False,
    )
