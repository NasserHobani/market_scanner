# -*- coding: utf-8 -*-
"""Public feature intelligence service API."""
from __future__ import annotations

from typing import Any

from .feature_intelligence_engine import (
    AnalysisHistoryStore,
    AnalysisResult,
    FeatureIntelligenceEngine,
)
from .ranking import RankedFeature, RANKING_WEIGHTS


class FeatureIntelligenceService:
    """Public facade for feature analytics.

    No model training. No ML-based importance. Feature analytics only.
    """

    def __init__(self, engine: FeatureIntelligenceEngine | None = None,
                 store: AnalysisHistoryStore | None = None) -> None:
        self._store = store or AnalysisHistoryStore()
        self._engine = engine or FeatureIntelligenceEngine(store=self._store)

    def analyze(self, rows: list[dict[str, Any]], *,
                feature_names: list[str] | None = None,
                research_confidence: dict[str, float] | None = None) -> AnalysisResult:
        """Run full feature intelligence analysis."""
        return self._engine.analyze(
            rows,
            feature_names=feature_names,
            research_confidence=research_confidence,
            persist=True,
        )

    def rank(self, rows: list[dict[str, Any]], **kwargs: Any) -> list[RankedFeature]:
        """Rank features by composite score."""
        return self._engine.rank(rows, **kwargs)

    def history(self, *, limit: int = 50) -> list[AnalysisResult]:
        """Return analysis history."""
        return self._engine.history(limit=limit)

    def report(self, analysis_id: str) -> dict[str, Any]:
        """Retrieve structured report for an analysis."""
        return self._engine.report(analysis_id)

    def drift(self, rows: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        """Detect feature drift only."""
        return self._engine.drift(rows, **kwargs)

    def ranking_weights(self) -> dict[str, float]:
        """Expose ranking weights — no hidden calculations."""
        return dict(RANKING_WEIGHTS)
