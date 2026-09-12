# -*- coding: utf-8 -*-
"""Similarity service — public API."""
from __future__ import annotations

from typing import Any

from scanner.knowledge import KnowledgeRepository, KnowledgeService

from .feature_distance import DistanceConfig, FeatureDistanceCalculator
from .filters import RetrievalFilters
from .fingerprint import build_fingerprint
from .ranking import RankingEngine, RankingWeights
from .result import SimilarityResult
from .retrieval import RetrievalEngine
from .similarity_engine import SimilarityEngine
from .similarity_score import ComponentWeights, SimilarityScorer


class SimilarityService:
    """Deterministic historical knowledge retrieval."""

    def __init__(self, *,
                 knowledge_service: KnowledgeService | None = None,
                 repository: KnowledgeRepository | None = None,
                 distance_config: DistanceConfig | None = None,
                 component_weights: ComponentWeights | None = None,
                 ranking_weights: RankingWeights | None = None) -> None:
        self.knowledge = knowledge_service or KnowledgeService(
            repository=repository or KnowledgeRepository(),
        )
        self.repository = self.knowledge.repository
        calculator = FeatureDistanceCalculator(distance_config)
        scorer = SimilarityScorer(calculator=calculator, weights=component_weights)
        ranker = RankingEngine(ranking_weights)
        self.engine = SimilarityEngine(
            retrieval=RetrievalEngine(
                repository=self.repository,
                scorer=scorer,
                ranker=ranker,
            ),
            scorer=scorer,
            ranker=ranker,
        )

    def find_similar(self, query: dict[str, Any], *,
                     top_n: int = 10,
                     filters: RetrievalFilters | None = None) -> dict[str, Any]:
        """Find top-N similar historical situations."""
        result = self.engine.find_similar(query, top_n=top_n, filters=filters)
        return result.to_dict()

    def find_best_matches(self, query: dict[str, Any], *,
                          top_n: int = 5,
                          filters: RetrievalFilters | None = None) -> dict[str, Any]:
        """Return highest-ranked matches only."""
        result = self.engine.find_similar(query, top_n=top_n, filters=filters)
        return {
            "count": len(result.matches),
            "matches": [m.to_dict() for m in result.matches],
            "statistics": result.statistics,
        }

    def compare(self, query: dict[str, Any],
                candidate: dict[str, Any]) -> dict[str, Any]:
        """Compare two situations directly."""
        return self.engine.compare(query, candidate)

    def compare_events(self, event_id_a: str,
                       event_id_b: str) -> dict[str, Any]:
        """Compare two knowledge events by event_id."""
        query = self._load_feature_payload(event_id_a)
        candidate = self._load_feature_payload(event_id_b)
        return self.compare(query, candidate)

    def fingerprint(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_fingerprint(source).to_dict()

    def statistics(self, query: dict[str, Any], *,
                   top_n: int = 25,
                   filters: RetrievalFilters | None = None) -> dict[str, Any]:
        """Aggregate statistics over similar historical situations."""
        result = self.engine.find_similar(query, top_n=top_n, filters=filters)
        return result.statistics

    def _load_feature_payload(self, event_id: str) -> dict[str, Any]:
        records = self.repository.history(event_id)
        features = [r for r in records if r.kind.value == "feature"]
        if not features:
            raise KeyError(f"no feature snapshot for event: {event_id}")
        return features[-1].payload
