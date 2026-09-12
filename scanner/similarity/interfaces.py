# -*- coding: utf-8 -*-
"""Similarity layer interfaces."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .feature_distance import FeatureDistance
from .result import SimilarityMatch, SimilarityResult


@runtime_checkable
class DistanceProvider(Protocol):
    def compare(self, query: dict[str, Any],
                candidate: dict[str, Any]) -> FeatureDistance: ...


@runtime_checkable
class RetrievalProvider(Protocol):
    def retrieve(self, query: dict[str, Any], *,
                 top_n: int = 10, **kwargs: Any) -> SimilarityResult: ...


@runtime_checkable
class RankingProvider(Protocol):
    def rank(self, matches: list[SimilarityMatch], **kwargs: Any) -> list[SimilarityMatch]: ...


@runtime_checkable
class SimilarityProvider(Protocol):
    def find_similar(self, query: dict[str, Any], **kwargs: Any) -> SimilarityResult: ...

    def compare(self, query: dict[str, Any],
                candidate: dict[str, Any]) -> dict[str, Any]: ...
