# -*- coding: utf-8 -*-
"""Reasoning service — high-level API for the platform."""
from __future__ import annotations

from typing import Any

from .reasoning_context import ReasoningContext
from .reasoning_engine import ReasoningEngine
from .recommendation_review import RecommendationReview


class ReasoningService:
    """Entry point: knowledge context in → recommendation review out."""

    def __init__(self, *, engine: ReasoningEngine | None = None) -> None:
        self.engine = engine or ReasoningEngine()

    def review_from_knowledge(self, knowledge_context: dict[str, Any]) -> RecommendationReview:
        ctx = ReasoningContext.from_knowledge(knowledge_context)
        return self.engine.run(ctx)

    def review_event(self, event_id: str, *,
                     knowledge_service: Any | None = None,
                     strategy_stats: Any | None = None,
                     recent_performance: dict[str, Any] | None = None,
                     ) -> RecommendationReview:
        """Load knowledge by event_id via KnowledgeService (optional integration)."""
        if knowledge_service is None:
            from scanner.knowledge import KnowledgeService
            knowledge_service = KnowledgeService()
        kctx = knowledge_service.get_context(
            event_id,
            strategy_stats=strategy_stats,
            recent_performance=recent_performance,
        )
        return self.review_from_knowledge(kctx)

    def explain(self, knowledge_context: dict[str, Any]) -> dict[str, Any]:
        ctx = ReasoningContext.from_knowledge(knowledge_context)
        return self.engine.run_partial(ctx)
