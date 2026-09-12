# -*- coding: utf-8 -*-
"""Default stage handlers — adapters to existing platform services."""
from __future__ import annotations

from typing import Any

from .execution_context import ExecutionContext


def load_market_handler(ctx: ExecutionContext) -> dict[str, Any]:
    source = dict(ctx.scan_source)
    return {
        "symbol": source.get("symbol") or ctx.symbol,
        "market": source.get("market") or ctx.market,
        "timeframe": source.get("timeframe") or ctx.timeframe,
        "scan_source": source,
        "loaded": True,
    }


def knowledge_handler(knowledge_service: Any | None = None):
    def _handler(ctx: ExecutionContext) -> dict[str, Any]:
        if knowledge_service is None:
            return {"knowledge_context": {}, "event_id": ctx.event_id}
        ids = knowledge_service.capture_scan(ctx.scan_source)
        event_id = ids.get("event_id") or ctx.event_id
        kctx = knowledge_service.get_context(event_id)
        return {"knowledge_context": kctx, "event_id": event_id, "knowledge_ids": ids}
    return _handler


def reasoning_handler(reasoning_service: Any | None = None):
    def _handler(ctx: ExecutionContext) -> dict[str, Any]:
        if reasoning_service is None or not ctx.knowledge:
            return {"reasoning": {}}
        review = reasoning_service.review_from_knowledge(ctx.knowledge)
        return {"reasoning": review.to_dict()}
    return _handler


def similarity_handler(similarity_service: Any | None = None):
    def _handler(ctx: ExecutionContext) -> dict[str, Any]:
        if similarity_service is None or not ctx.knowledge:
            return {"similarity": {"available": False}}
        query = {
            "event_id": ctx.event_id,
            "feature_snapshot": ctx.knowledge.get("feature_snapshot") or {},
            "market_snapshot": ctx.knowledge.get("market_snapshot") or {},
        }
        result = similarity_service.find_similar(query, top_n=10)
        stats = result.get("statistics") or {}
        return {
            "similarity": {
                "available": True,
                "match_count": stats.get("count") or len(result.get("matches") or []),
                "similarity_result": result,
                "average_win_rate": stats.get("win_rate"),
                "average_r": stats.get("avg_r"),
            },
        }
    return _handler


def research_handler(research_service: Any | None = None):
    def _handler(ctx: ExecutionContext) -> dict[str, Any]:
        if research_service is None or not ctx.trade_rows:
            return {"research": {}}
        rows = list(ctx.trade_rows)
        stats = research_service.statistics(rows)
        return {"research": {"statistics": stats, "row_count": len(rows)}}
    return _handler


def prediction_handler(predictive_service: Any | None = None, *,
                       model_id: str = "",
                       feature_columns: list[str] | None = None):
    def _handler(ctx: ExecutionContext) -> dict[str, Any]:
        if predictive_service is None or not model_id:
            return {"prediction": {}}
        fs = (ctx.knowledge.get("feature_snapshot") or {}).get("feature_registry") or {}
        feat_cols = feature_columns or list(fs.keys())[:10]
        vector = {k: (fs.get(k) or {}).get("value", 0.0) for k in feat_cols
                  if isinstance(fs.get(k), dict)}
        if not vector:
            return {"prediction": {}}
        result = predictive_service.predict(model_id, vector)
        return {"prediction": result.to_dict()}
    return _handler


def decision_ai_handler(decision_service: Any | None = None):
    def _handler(ctx: ExecutionContext) -> dict[str, Any]:
        if decision_service is None:
            return {"decision_review": {}}
        review = decision_service.review_trade(
            event_id=ctx.event_id or ctx.analysis_id,
            knowledge_context=ctx.knowledge,
            reasoning_review=ctx.reasoning,
            similarity_context=ctx.similarity,
            prediction=ctx.prediction or None,
            research_report=ctx.research or None,
            feature_analysis=ctx.feature_intelligence or None,
        )
        return {"decision_review": review.to_dict()}
    return _handler


def aggregation_handler(ctx: ExecutionContext) -> dict[str, Any]:
    return {"aggregated": True, "analysis_id": ctx.analysis_id}
