# -*- coding: utf-8 -*-
"""Aggregate stage outputs into MarketAnalysis."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .execution_context import ExecutionContext
from .result import AnalysisStatus, MarketAnalysis, StageExecutionResult


class MarketAnalysisAggregator:
    """Combine all stage outputs into one MarketAnalysis."""

    def aggregate(self, ctx: ExecutionContext, *,
                  trace: list[StageExecutionResult],
                  analysis_id: str,
                  status: str = AnalysisStatus.COMPLETED.value) -> MarketAnalysis:
        return MarketAnalysis(
            analysis_id=analysis_id,
            symbol=ctx.symbol,
            market=ctx.market,
            timeframe=ctx.timeframe,
            status=status,
            knowledge=dict(ctx.knowledge),
            reasoning=dict(ctx.reasoning),
            similarity=dict(ctx.similarity),
            research=dict(ctx.research),
            prediction=dict(ctx.prediction),
            decision_review=dict(ctx.decision_review),
            execution_trace=[t.to_dict() for t in trace],
            metadata={
                "event_id": ctx.event_id,
                "stage_count": len(trace),
                "failed_stages": [t.stage for t in trace
                                  if t.status == AnalysisStatus.FAILED.value],
                "skipped_stages": [t.stage for t in trace
                                   if t.status == AnalysisStatus.SKIPPED.value],
                "cached_stages": [t.stage for t in trace if t.cached],
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def summarize(self, analysis: MarketAnalysis) -> dict[str, Any]:
        """Compact summary of analysis."""
        return {
            "analysis_id": analysis.analysis_id,
            "symbol": analysis.symbol,
            "status": analysis.status,
            "has_knowledge": bool(analysis.knowledge),
            "has_reasoning": bool(analysis.reasoning),
            "has_similarity": bool(analysis.similarity),
            "has_research": bool(analysis.research),
            "has_prediction": bool(analysis.prediction),
            "has_decision_review": bool(analysis.decision_review),
            "stage_count": len(analysis.execution_trace),
        }
