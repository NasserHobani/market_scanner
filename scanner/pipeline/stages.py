# -*- coding: utf-8 -*-
"""Pipeline stage executors — independently runnable."""
from __future__ import annotations

from typing import Any

from .context import empty_similarity_context
from .similarity_integration import (
    build_similarity_context,
    build_similarity_summary,
    enrich_intelligence_report,
)
from .state import StageName
from .validation import (
    validate_intelligence_output,
    validate_knowledge_output,
    validate_reasoning_output,
    validate_scan_source,
    validate_trade_rows,
    validate_trade_source,
)


class KnowledgeStage:
    name = StageName.KNOWLEDGE.value

    def __init__(self, knowledge_service: Any) -> None:
        self._ks = knowledge_service

    def validate_input(self, context: dict[str, Any]) -> list[str]:
        mode = context.get("capture_mode", "scan")
        if mode == "scan":
            return validate_scan_source(context.get("scan_source") or {})
        if mode == "lifecycle":
            return validate_scan_source(context.get("scan_source") or {})
        if mode == "trade":
            return validate_trade_source(context.get("trade_source") or {})
        if mode == "outcome":
            if not context.get("outcome_source"):
                return ["outcome mode requires outcome_source"]
            return []
        return [f"unknown capture_mode: {mode}"]

    def validate_output(self, output: dict[str, Any]) -> list[str]:
        return validate_knowledge_output(output)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        mode = context.get("capture_mode", "scan")
        if mode == "scan":
            ids = self._ks.capture_scan(context["scan_source"])
        elif mode == "lifecycle":
            ids = self._ks.capture_lifecycle(
                scan_source=context["scan_source"],
                trade_source=context.get("trade_source"),
                outcome_source=context.get("outcome_source"),
            )
        elif mode == "trade":
            trade_source = {**context["trade_source"]}
            if context.get("knowledge_ids"):
                trade_source.setdefault(
                    "recommendation_snapshot_id",
                    context["knowledge_ids"].get("recommendation_snapshot_id"),
                )
                trade_source.setdefault("event_id", context["knowledge_ids"].get("event_id"))
            record_id = self._ks.capture_trade(trade_source)
            ids = {"trade_record_id": record_id, **context.get("knowledge_ids", {})}
            ids["event_id"] = trade_source.get("event_id") or ids.get("event_id", "")
        elif mode == "outcome":
            outcome_source = {**context["outcome_source"]}
            if context.get("knowledge_ids"):
                outcome_source.setdefault("event_id", context["knowledge_ids"].get("event_id"))
                outcome_source.setdefault(
                    "trade_snapshot_id",
                    context["knowledge_ids"].get("trade_snapshot_id"),
                )
            record_id = self._ks.capture_outcome(outcome_source)
            ids = {"outcome_record_id": record_id, **context.get("knowledge_ids", {})}
            ids["event_id"] = outcome_source.get("event_id") or ids.get("event_id", "")
        else:
            raise ValueError(f"unknown capture_mode: {mode}")

        return {
            "event_id": ids.get("event_id", ""),
            "knowledge_ids": ids,
        }


class SimilarityStage:
    """Optional stage — never fails the pipeline."""

    name = StageName.SIMILARITY.value
    optional = True

    def __init__(self, similarity_service: Any) -> None:
        self._ss = similarity_service

    def validate_input(self, context: dict[str, Any]) -> list[str]:
        return []

    def validate_output(self, output: dict[str, Any]) -> list[str]:
        return []

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        from scanner.similarity import RetrievalFilters

        event_id = context.get("event_id", "")
        query = context.get("scan_source") or {}
        top_n = context.get("similarity_top_n", 10)

        try:
            filters = RetrievalFilters(
                market=query.get("market"),
                timeframe=query.get("timeframe"),
                exclude_event_ids=[event_id] if event_id else [],
            )
            result = self._ss.find_similar(query, top_n=top_n, filters=filters)
            sim_ctx = build_similarity_context(result)
            summary = build_similarity_summary(result, event_id=event_id)
            return {
                "similarity_result": result,
                "similarity_context": sim_ctx.to_dict(),
                "similarity_summary": summary.to_dict(),
                "similarity_metrics": {
                    "candidate_count": result.get("total_candidates", 0),
                    "filtered_candidates": result.get("filtered_candidates", 0),
                    "retrieved_matches": result.get("count", 0),
                    "avg_similarity": summary.avg_similarity,
                },
            }
        except Exception as exc:
            sim_ctx = empty_similarity_context()
            return {
                "similarity_result": {},
                "similarity_context": sim_ctx.to_dict(),
                "similarity_summary": build_similarity_summary(None, event_id=event_id).to_dict(),
                "similarity_error": str(exc),
                "similarity_metrics": {"error": str(exc)},
            }


class ReasoningStage:
    name = StageName.REASONING.value

    def __init__(self, reasoning_service: Any, knowledge_service: Any) -> None:
        self._rs = reasoning_service
        self._ks = knowledge_service

    def validate_input(self, context: dict[str, Any]) -> list[str]:
        if not context.get("event_id"):
            return ["reasoning requires event_id from knowledge stage"]
        return []

    def validate_output(self, output: dict[str, Any]) -> list[str]:
        return validate_reasoning_output(output)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        event_id = context["event_id"]
        trade_rows = context.get("trade_rows") or []
        strategy_stats = None
        if trade_rows:
            strategy_stats = self._ks.strategy_stats_from_rows(trade_rows)
        kctx = self._ks.get_context(
            event_id,
            strategy_stats=strategy_stats,
            recent_performance=context.get("recent_performance"),
        )
        kctx["similarity_context"] = context.get("similarity_context") or {}
        review = self._rs.review_from_knowledge(kctx)
        return {"reasoning_review": review.to_dict()}


class IntelligenceStage:
    name = StageName.INTELLIGENCE.value

    def __init__(self, intelligence_service: Any) -> None:
        self._is = intelligence_service

    def validate_input(self, context: dict[str, Any]) -> list[str]:
        if context.get("skip_intelligence"):
            return []
        trade_rows = context.get("trade_rows")
        if not trade_rows:
            return ["intelligence requires trade_rows or skip_intelligence=true"]
        return validate_trade_rows(trade_rows)

    def validate_output(self, output: dict[str, Any]) -> list[str]:
        if output.get("skipped"):
            return []
        return validate_intelligence_output(output)

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        if context.get("skip_intelligence"):
            return {"skipped": True, "intelligence_report": None}
        report = self._is.analyze(
            context["trade_rows"],
            strategy_id=context.get("strategy_id", "default"),
            summary_window=context.get("summary_window"),
        )
        sim_ctx_dict = context.get("similarity_context") or {}
        if sim_ctx_dict:
            from .context import SimilarityContext
            sim_ctx = SimilarityContext(
                similarity_result=sim_ctx_dict.get("similarity_result", {}),
                similarity_statistics=sim_ctx_dict.get("similarity_statistics", {}),
                match_count=sim_ctx_dict.get("match_count", 0),
                average_win_rate=sim_ctx_dict.get("average_win_rate"),
                average_r=sim_ctx_dict.get("average_r"),
                historical_evidence=tuple(sim_ctx_dict.get("historical_evidence", ())),
                historical_warnings=tuple(sim_ctx_dict.get("historical_warnings", ())),
                available=sim_ctx_dict.get("available", False),
            )
            report = enrich_intelligence_report(report, sim_ctx)
        return {"intelligence_report": report}
