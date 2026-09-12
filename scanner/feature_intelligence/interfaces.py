# -*- coding: utf-8 -*-
"""Feature intelligence protocols."""
from __future__ import annotations

from typing import Any, Protocol

from .feature_intelligence_engine import AnalysisResult
from .ranking import RankedFeature


class FeatureImportanceProtocol(Protocol):
    def compute(self, rows: list[dict[str, Any]], **kwargs: Any) -> list: ...


class FeatureStabilityProtocol(Protocol):
    def compute(self, rows: list[dict[str, Any]], **kwargs: Any) -> list: ...


class FeatureDriftProtocol(Protocol):
    def compute(self, rows: list[dict[str, Any]], **kwargs: Any) -> list: ...


class FeatureIntelligenceEngineProtocol(Protocol):
    def analyze(self, rows: list[dict[str, Any]], **kwargs: Any) -> AnalysisResult: ...
    def rank(self, rows: list[dict[str, Any]], **kwargs: Any) -> list[RankedFeature]: ...
    def drift(self, rows: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]: ...
    def report(self, analysis_id: str) -> dict[str, Any]: ...
    def history(self, *, limit: int = 50) -> list[AnalysisResult]: ...
