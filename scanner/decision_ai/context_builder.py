# -*- coding: utf-8 -*-
"""Immutable AI decision context — aggregates all platform layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DECISION_AI_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DecisionAIContext:
    """Immutable structured context for AI decision support.

    Aggregates knowledge, reasoning, similarity, research,
    feature intelligence, and prediction — never mutates source layers.
    """

    event_id: str
    symbol: str = ""
    market: str = ""
    timeframe: str = ""
    knowledge: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)
    similarity: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    feature_intelligence: dict[str, Any] = field(default_factory=dict)
    prediction: dict[str, Any] = field(default_factory=dict)
    intelligence: dict[str, Any] = field(default_factory=dict)
    strategy_statistics: dict[str, Any] = field(default_factory=dict)
    memory_gaps: tuple[str, ...] = ()
    schema_version: str = DECISION_AI_VERSION
    built_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "knowledge": dict(self.knowledge),
            "reasoning": dict(self.reasoning),
            "similarity": dict(self.similarity),
            "research": dict(self.research),
            "feature_intelligence": dict(self.feature_intelligence),
            "prediction": dict(self.prediction),
            "intelligence": dict(self.intelligence),
            "strategy_statistics": dict(self.strategy_statistics),
            "memory_gaps": list(self.memory_gaps),
            "schema_version": self.schema_version,
            "built_at": self.built_at or _now(),
        }


class ContextBuilder:
    """Collect information from all layers into one immutable context."""

    def build(self, *,
              event_id: str,
              knowledge_context: dict[str, Any] | None = None,
              reasoning_review: dict[str, Any] | None = None,
              similarity_context: dict[str, Any] | None = None,
              research_report: dict[str, Any] | None = None,
              feature_analysis: dict[str, Any] | None = None,
              prediction: dict[str, Any] | None = None,
              intelligence_report: dict[str, Any] | None = None,
              strategy_statistics: dict[str, Any] | None = None,
              memory_gaps: list[str] | None = None) -> DecisionAIContext:
        kctx = knowledge_context or {}
        reco = kctx.get("recommendation_snapshot") or {}
        market = kctx.get("market_snapshot") or {}

        symbol = (
            kctx.get("symbol")
            or market.get("symbol")
            or reco.get("symbol")
            or ""
        )
        mkt = kctx.get("market") or market.get("market") or ""
        tf = kctx.get("timeframe") or market.get("timeframe") or ""

        reasoning = self._build_reasoning(reasoning_review)
        stats = strategy_statistics or kctx.get("strategy_statistics") or {}

        return DecisionAIContext(
            event_id=event_id,
            symbol=str(symbol),
            market=str(mkt),
            timeframe=str(tf),
            knowledge=self._sanitize_knowledge(kctx),
            reasoning=reasoning,
            similarity=dict(similarity_context or {}),
            research=dict(research_report or {}),
            feature_intelligence=dict(feature_analysis or {}),
            prediction=dict(prediction or {}),
            intelligence=dict(intelligence_report or {}),
            strategy_statistics=dict(stats),
            memory_gaps=tuple(memory_gaps or []),
            built_at=_now(),
        )

    @staticmethod
    def _build_reasoning(review: dict[str, Any] | None) -> dict[str, Any]:
        if not review:
            return {}
        return {
            "verdict": review.get("verdict"),
            "agreement_score": review.get("agreement_score"),
            "engine_confidence": review.get("engine_confidence"),
            "recommendation_confidence": review.get("recommendation_confidence"),
            "evidence": review.get("evidence") or {},
            "contradictions": review.get("contradictions") or {},
            "confidence": review.get("confidence") or {},
            "explanation": review.get("explanation") or {},
            "decision_tree": review.get("decision_tree") or {},
            "warnings": list(review.get("warnings") or []),
            "missing_information": list(review.get("missing_information") or []),
            "action": review.get("action"),
            "direction": review.get("direction"),
        }

    @staticmethod
    def _sanitize_knowledge(kctx: dict[str, Any]) -> dict[str, Any]:
        """Include knowledge references without duplicating full raw storage."""
        return {
            "event_id": kctx.get("event_id"),
            "market_snapshot": kctx.get("market_snapshot") or {},
            "market_environment": kctx.get("market_environment") or {},
            "feature_snapshot": kctx.get("feature_snapshot") or {},
            "recommendation_snapshot": kctx.get("recommendation_snapshot") or {},
            "trade_snapshot": kctx.get("trade_snapshot"),
            "outcome_snapshot": kctx.get("outcome_snapshot"),
            "knowledge_graph": kctx.get("knowledge_graph") or {},
            "knowledge_memory": kctx.get("knowledge_memory") or {},
            "timeline": kctx.get("timeline") or [],
            "schema_version": kctx.get("schema_version"),
        }
