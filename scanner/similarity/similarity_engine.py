# -*- coding: utf-8 -*-
"""Similarity engine — orchestrates fingerprint, distance, retrieval, ranking."""
from __future__ import annotations

from typing import Any

from .feature_distance import DistanceConfig, FeatureDistance, FeatureDistanceCalculator
from .filters import RetrievalFilters
from .fingerprint import SituationalFingerprint, build_fingerprint, fingerprint_match_score
from .ranking import RankingEngine, RankingWeights
from .result import SimilarityMatch, SimilarityResult
from .retrieval import RetrievalEngine
from .similarity_score import ComponentWeights, SimilarityScore, SimilarityScorer


class SimilarityEngine:
    """Top-level similarity orchestrator."""

    def __init__(self, *,
                 retrieval: RetrievalEngine | None = None,
                 scorer: SimilarityScorer | None = None,
                 ranker: RankingEngine | None = None) -> None:
        self.scorer = scorer or SimilarityScorer()
        self.ranker = ranker or RankingEngine()
        self.retrieval = retrieval or RetrievalEngine(
            scorer=self.scorer, ranker=self.ranker,
        )

    def find_similar(self, query: dict[str, Any], *,
                     top_n: int = 10,
                     filters: RetrievalFilters | None = None) -> SimilarityResult:
        return self.retrieval.retrieve(query, top_n=top_n, filters=filters)

    def compare(self, query: dict[str, Any],
                candidate: dict[str, Any]) -> dict[str, Any]:
        q_fp = build_fingerprint(query)
        c_fp = build_fingerprint(candidate)
        score, distance = self.scorer.score(query, candidate)
        return {
            "query_fingerprint": q_fp.to_dict(),
            "candidate_fingerprint": c_fp.to_dict(),
            "fingerprint_match": round(fingerprint_match_score(q_fp, c_fp), 4),
            "similarity_score": score.to_dict(),
            "feature_distance": distance.to_dict(),
        }

    def fingerprint(self, source: dict[str, Any]) -> SituationalFingerprint:
        return build_fingerprint(source)
