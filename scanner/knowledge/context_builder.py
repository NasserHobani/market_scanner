# -*- coding: utf-8 -*-
"""Assemble AI context — no analysis, only structured aggregation."""
from __future__ import annotations

from typing import Any

from .exceptions import SnapshotNotFoundError
from .memory import KnowledgeMemory
from .relationships import build_graph_from_history
from .repository import KnowledgeRepository
from .schemas import SnapshotKind, StrategyStatistics


class ContextBuilder:
    """Combines snapshots and statistics into one LLM-ready object."""

    def __init__(self, repository: KnowledgeRepository | None = None) -> None:
        self.repository = repository or KnowledgeRepository()

    def build_context(self, event_id: str, *,
                      strategy_stats: StrategyStatistics | None = None,
                      recent_performance: dict[str, Any] | None = None,
                      ) -> dict[str, Any]:
        history = self.repository.history(event_id)
        if not history:
            raise SnapshotNotFoundError(event_id)

        environment = self._latest_payload(history, SnapshotKind.ENVIRONMENT)
        market = self._latest_payload(history, SnapshotKind.MARKET)
        features = self._latest_payload(history, SnapshotKind.FEATURE)
        recommendation = self._latest_payload(history, SnapshotKind.RECOMMENDATION)
        trade = self._latest_payload(history, SnapshotKind.TRADE)
        outcome = self._latest_payload(history, SnapshotKind.OUTCOME)

        meta = history[0].payload
        graph = build_graph_from_history(event_id, history)
        memory = KnowledgeMemory(event_id=event_id)

        return {
            "event_id": event_id,
            "symbol": meta.get("symbol"),
            "market": meta.get("market"),
            "timeframe": meta.get("timeframe"),
            "schema_version": (market or {}).get("schema", {}).get("schema_version"),
            "market_environment": environment,
            "market_snapshot": market,
            "feature_snapshot": features,
            "recommendation_snapshot": recommendation,
            "trade_snapshot": trade,
            "outcome_snapshot": outcome,
            "knowledge_graph": graph.to_dict(),
            "knowledge_memory": memory.to_dict(),
            "strategy_statistics": (strategy_stats or StrategyStatistics()).to_dict(),
            "recent_performance": recent_performance or {},
            "timeline": [
                {"kind": rec.kind.value, "record_id": rec.record_id,
                 "created_at": rec.created_at.isoformat()}
                for rec in history
            ],
        }

    @staticmethod
    def _latest_payload(history: list, kind: SnapshotKind) -> dict[str, Any] | None:
        matches = [r for r in history if r.kind == kind]
        if not matches:
            return None
        return matches[-1].payload
