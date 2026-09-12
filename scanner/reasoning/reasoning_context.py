# -*- coding: utf-8 -*-
"""Unified reasoning context — input for all future AI systems."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReasoningContext:
    """Single object bridging Knowledge Layer and Reasoning Layer."""

    event_id: str
    symbol: str | None = None
    market: str | None = None
    timeframe: str | None = None
    market_snapshot: dict[str, Any] | None = None
    market_environment: dict[str, Any] | None = None
    feature_snapshot: dict[str, Any] | None = None
    recommendation_snapshot: dict[str, Any] | None = None
    trade_snapshot: dict[str, Any] | None = None
    outcome_snapshot: dict[str, Any] | None = None
    knowledge_graph: dict[str, Any] | None = None
    strategy_statistics: dict[str, Any] = field(default_factory=dict)
    recent_performance: dict[str, Any] = field(default_factory=dict)
    similarity_context: dict[str, Any] = field(default_factory=dict)
    knowledge_memory: dict[str, Any] | None = None
    schema_version: str | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_knowledge(cls, context: dict[str, Any]) -> ReasoningContext:
        """Build from KnowledgeService.get_context() output — read-only."""
        return cls(
            event_id=context.get("event_id") or "",
            symbol=context.get("symbol"),
            market=context.get("market"),
            timeframe=context.get("timeframe"),
            market_snapshot=context.get("market_snapshot"),
            market_environment=context.get("market_environment"),
            feature_snapshot=context.get("feature_snapshot"),
            recommendation_snapshot=context.get("recommendation_snapshot"),
            trade_snapshot=context.get("trade_snapshot"),
            outcome_snapshot=context.get("outcome_snapshot"),
            knowledge_graph=context.get("knowledge_graph"),
            strategy_statistics=dict(context.get("strategy_statistics") or {}),
            recent_performance=dict(context.get("recent_performance") or {}),
            similarity_context=dict(context.get("similarity_context") or {}),
            knowledge_memory=context.get("knowledge_memory"),
            schema_version=context.get("schema_version"),
            timeline=list(context.get("timeline") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "schema_version": self.schema_version,
            "market_snapshot": self.market_snapshot,
            "market_environment": self.market_environment,
            "feature_snapshot": self.feature_snapshot,
            "recommendation_snapshot": self.recommendation_snapshot,
            "trade_snapshot": self.trade_snapshot,
            "outcome_snapshot": self.outcome_snapshot,
            "knowledge_graph": self.knowledge_graph,
            "strategy_statistics": dict(self.strategy_statistics),
            "recent_performance": dict(self.recent_performance),
            "similarity_context": dict(self.similarity_context),
            "knowledge_memory": self.knowledge_memory,
            "timeline": list(self.timeline),
        }

    def as_knowledge_dict(self) -> dict[str, Any]:
        """Flatten back to knowledge-context shape for engines."""
        return self.to_dict()
