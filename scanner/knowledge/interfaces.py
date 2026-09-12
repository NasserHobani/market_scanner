# -*- coding: utf-8 -*-
"""Abstract interfaces — AI components depend on these, not concrete stores."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .schemas import KnowledgeRecord, SnapshotKind, StrategyStatistics


@runtime_checkable
class SnapshotProvider(Protocol):
    """Builds typed snapshots from platform-native data."""

    def build_market(self, source: dict[str, Any]) -> dict[str, Any]: ...

    def build_environment(self, source: dict[str, Any]) -> dict[str, Any]: ...

    def build_features(self, source: dict[str, Any]) -> dict[str, Any]: ...

    def build_recommendation(self, source: dict[str, Any]) -> dict[str, Any]: ...

    def build_trade(self, source: dict[str, Any]) -> dict[str, Any]: ...

    def build_outcome(self, source: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Persistence and retrieval of knowledge records."""

    def save(self, record: KnowledgeRecord) -> str: ...

    def load(self, record_id: str) -> KnowledgeRecord: ...

    def search(self, *, kind: SnapshotKind | None = None,
               event_id: str | None = None,
               symbol: str | None = None,
               market: str | None = None,
               timeframe: str | None = None,
               limit: int = 100) -> list[KnowledgeRecord]: ...

    def history(self, event_id: str) -> list[KnowledgeRecord]: ...

    def statistics(self, *, market: str | None = None,
                   timeframe: str | None = None) -> dict[str, Any]: ...


@runtime_checkable
class ContextProvider(Protocol):
    """Assembles AI-ready context from stored knowledge."""

    def build_context(self, event_id: str, *,
                      strategy_stats: StrategyStatistics | None = None,
                      recent_performance: dict[str, Any] | None = None,
                      ) -> dict[str, Any]: ...


@runtime_checkable
class FeatureVectorProvider(Protocol):
    """Feature export for ML pipelines — no ML library dependency."""

    def to_dict(self) -> dict[str, Any]: ...

    def to_vector(self) -> list[float | None]: ...

    def to_dataframe(self) -> dict[str, Any]: ...
