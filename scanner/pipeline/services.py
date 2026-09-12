# -*- coding: utf-8 -*-
"""Public pipeline service — production integration API."""
from __future__ import annotations

from typing import Any

from scanner.intelligence import IntelligenceService
from scanner.knowledge import KnowledgeRepository, KnowledgeService
from scanner.reasoning import ReasoningService
from scanner.similarity import SimilarityService

from .coordinator import PipelineCoordinatorImpl
from .event_bus import EventBus
from .metrics import MetricsCollector
from .persistence import PipelineStore
from .similarity_integration import build_similarity_context, build_similarity_summary
from .state import PipelineExecution, PipelineStatus, PipelineType, StageName, StageResult


class PipelineService:
    """Connect Knowledge → Similarity → Reasoning → Intelligence."""

    def __init__(self, *,
                 knowledge_service: KnowledgeService | None = None,
                 reasoning_service: ReasoningService | None = None,
                 intelligence_service: IntelligenceService | None = None,
                 similarity_service: SimilarityService | None = None,
                 store: PipelineStore | None = None,
                 event_bus: EventBus | None = None) -> None:
        self.knowledge = knowledge_service or KnowledgeService()
        self.reasoning = reasoning_service or ReasoningService()
        self.intelligence = intelligence_service or IntelligenceService()
        self.similarity = similarity_service or SimilarityService(
            knowledge_service=self.knowledge,
        )
        self.store = store or PipelineStore()
        self.event_bus = event_bus or EventBus()
        self.coordinator = PipelineCoordinatorImpl(
            knowledge_service=self.knowledge,
            reasoning_service=self.reasoning,
            intelligence_service=self.intelligence,
            similarity_service=self.similarity,
            store=self.store,
            event_bus=self.event_bus,
        )
        self._metrics = MetricsCollector()

    def run_scan_pipeline(self, scan_source: dict[str, Any], *,
                          trade_rows: list[dict] | None = None,
                          strategy_id: str = "default",
                          recent_performance: dict[str, Any] | None = None,
                          summary_window: int | None = None,
                          similarity_top_n: int = 10) -> dict[str, Any]:
        """Scan → knowledge → similarity → reasoning → intelligence → persist."""
        context = {
            "capture_mode": "scan",
            "scan_source": scan_source,
            "trade_rows": trade_rows,
            "strategy_id": strategy_id,
            "recent_performance": recent_performance,
            "summary_window": summary_window,
            "similarity_top_n": similarity_top_n,
            "metadata": {
                "capture_mode": "scan",
                "scan_source": scan_source,
                "trade_rows": trade_rows,
            },
        }
        execution = self.coordinator.execute(PipelineType.SCAN.value, context)
        return execution.to_dict()

    def run_trade_pipeline(self, *,
                           scan_source: dict[str, Any] | None = None,
                           trade_source: dict[str, Any] | None = None,
                           outcome_source: dict[str, Any] | None = None,
                           trade_rows: list[dict] | None = None,
                           strategy_id: str = "default",
                           summary_window: int | None = None,
                           similarity_top_n: int = 10) -> dict[str, Any]:
        """Trade lifecycle → knowledge → similarity → reasoning → intelligence."""
        if scan_source and trade_source:
            capture_mode = "lifecycle"
        elif outcome_source:
            capture_mode = "outcome"
        elif trade_source:
            capture_mode = "trade"
        else:
            raise ValueError("trade pipeline requires trade_source or outcome_source")

        context = {
            "capture_mode": capture_mode,
            "scan_source": scan_source,
            "trade_source": trade_source,
            "outcome_source": outcome_source,
            "trade_rows": trade_rows,
            "strategy_id": strategy_id,
            "summary_window": summary_window,
            "similarity_top_n": similarity_top_n,
            "metadata": {
                "capture_mode": capture_mode,
                "scan_source": scan_source,
                "trade_source": trade_source,
                "outcome_source": outcome_source,
                "trade_rows": trade_rows,
            },
        }
        execution = self.coordinator.execute(PipelineType.TRADE.value, context)
        return execution.to_dict()

    def run_similarity(self, query: dict[str, Any], *,
                       event_id: str | None = None,
                       top_n: int = 10) -> dict[str, Any]:
        """Run similarity retrieval standalone."""
        from scanner.similarity import RetrievalFilters

        filters = RetrievalFilters(
            market=query.get("market"),
            timeframe=query.get("timeframe"),
            exclude_event_ids=[event_id] if event_id else [],
        )
        result = self.similarity.find_similar(query, top_n=top_n, filters=filters)
        sim_ctx = build_similarity_context(result)
        summary = build_similarity_summary(result, event_id=event_id or "")
        return {
            "similarity_result": result,
            "similarity_context": sim_ctx.to_dict(),
            "similarity_summary": summary.to_dict(),
        }

    def rebuild_similarity(self, event_id: str, *,
                           scan_source: dict[str, Any] | None = None,
                           top_n: int = 10) -> dict[str, Any]:
        """Re-run similarity for an existing knowledge event."""
        query = scan_source or self._load_scan_query(event_id)
        return self.run_similarity(query, event_id=event_id, top_n=top_n)

    def similarity_status(self, execution_id: str | None = None, *,
                          event_id: str | None = None) -> dict[str, Any]:
        """Return similarity summary from a pipeline execution."""
        if execution_id:
            execution = self.coordinator.status(execution_id)
        elif event_id:
            rows = self.coordinator.history(event_id=event_id, limit=1)
            if not rows:
                return {"status": "not_found", "event_id": event_id}
            execution = rows[0]
        else:
            raise ValueError("execution_id or event_id required")

        return {
            "execution_id": execution.execution_id,
            "event_id": execution.event_id,
            "status": execution.status,
            "similarity_summary": execution.similarity_summary,
            "similarity_context": execution.metadata.get("similarity_context"),
            "similarity_metrics": execution.metrics.get("similarity"),
        }

    def rebuild_trade(self, event_id: str, *,
                      trade_rows: list[dict] | None = None,
                      strategy_id: str = "default",
                      scan_source: dict[str, Any] | None = None) -> dict[str, Any]:
        """Re-run similarity + reasoning + intelligence for existing event."""
        context = {
            "capture_mode": "scan",
            "skip_knowledge": True,
            "event_id": event_id,
            "knowledge_ids": {"event_id": event_id},
            "scan_source": scan_source,
            "trade_rows": trade_rows,
            "strategy_id": strategy_id,
            "metadata": {"event_id": event_id, "trade_rows": trade_rows, "rebuild": True},
        }
        execution = self._execute_rebuild(PipelineType.REBUILD_TRADE.value, context)
        self.store.save(execution)
        return execution.to_dict()

    def rebuild_market(self, market: str, timeframe: str, *,
                       trade_rows: list[dict] | None = None,
                       strategy_id: str = "default",
                       limit: int = 50) -> list[dict[str, Any]]:
        """Re-run pipeline for all events in a market/timeframe."""
        repo: KnowledgeRepository = self.knowledge.repository
        records = repo.search(market=market, timeframe=timeframe, limit=limit * 10)
        event_ids = sorted({r.event_id for r in records if r.event_id})[:limit]
        results: list[dict[str, Any]] = []
        for eid in event_ids:
            result = self.rebuild_trade(eid, trade_rows=trade_rows,
                                        strategy_id=strategy_id)
            results.append(result)
        return results

    def status(self, execution_id: str) -> dict[str, Any]:
        execution = self.coordinator.status(execution_id)
        return execution.to_dict()

    def history(self, *, limit: int = 50,
                pipeline_type: str | None = None,
                event_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.coordinator.history(
            limit=limit, pipeline_type=pipeline_type, event_id=event_id,
        )
        return [r.to_dict() for r in rows]

    def get_metrics(self, *, limit: int = 100) -> dict[str, Any]:
        executions = self.coordinator.history(limit=limit)
        return self._metrics.aggregate(executions).to_dict()

    def _load_scan_query(self, event_id: str) -> dict[str, Any]:
        records = self.knowledge.repository.history(event_id)
        features = [r for r in records if r.kind.value == "feature"]
        if features:
            return features[-1].payload
        markets = [r for r in records if r.kind.value == "market"]
        if markets:
            return markets[-1].payload
        raise KeyError(f"no query source for event: {event_id}")

    def _execute_rebuild(self, pipeline_type: str,
                         context: dict[str, Any]) -> PipelineExecution:
        """Rebuild skips knowledge, runs similarity + reasoning + intelligence."""
        from .state import PIPELINE_VERSION
        from datetime import datetime, timezone
        import time
        import uuid

        def _now() -> str:
            return datetime.now(timezone.utc).isoformat()

        execution = PipelineExecution(
            execution_id=f"pex_{uuid.uuid4().hex[:16]}",
            pipeline_type=pipeline_type,
            pipeline_version=PIPELINE_VERSION,
            status=PipelineStatus.RUNNING.value,
            event_id=context.get("event_id", ""),
            strategy_id=context.get("strategy_id", "default"),
            started_at=_now(),
            metadata=dict(context.get("metadata") or {}),
        )
        start = time.perf_counter()
        pipeline_context = dict(context)

        execution.stages.append(StageResult(
            stage=StageName.KNOWLEDGE.value,
            status=PipelineStatus.SKIPPED.value,
            started_at=_now(),
            completed_at=_now(),
        ))

        rebuild_stages = []
        if self.coordinator._similarity:
            rebuild_stages.append(self.coordinator._similarity)
        rebuild_stages.extend([
            self.coordinator._reasoning,
            self.coordinator._intelligence,
        ])

        for stage in rebuild_stages:
            if stage.name == StageName.INTELLIGENCE.value and not pipeline_context.get("trade_rows"):
                execution.stages.append(StageResult(
                    stage=stage.name,
                    status=PipelineStatus.SKIPPED.value,
                    started_at=_now(),
                    completed_at=_now(),
                ))
                continue
            if stage.name == StageName.SIMILARITY.value and not pipeline_context.get("scan_source"):
                try:
                    pipeline_context["scan_source"] = self._load_scan_query(
                        pipeline_context["event_id"],
                    )
                except KeyError:
                    execution.stages.append(StageResult(
                        stage=stage.name,
                        status=PipelineStatus.SKIPPED.value,
                        started_at=_now(),
                        completed_at=_now(),
                    ))
                    continue

            result = self.coordinator._run_stage(stage, pipeline_context, execution)
            execution.stages.append(result)
            if result.status == PipelineStatus.FAILED.value and not getattr(stage, "optional", False):
                execution.status = PipelineStatus.FAILED.value
                execution.errors.append(result.error or f"{stage.name} failed")
                execution.duration_ms = (time.perf_counter() - start) * 1000
                execution.completed_at = _now()
                execution.metrics = self._metrics.from_execution(execution)
                return execution

            if stage.name == StageName.SIMILARITY.value:
                execution.similarity_summary = pipeline_context.get("similarity_summary")
                execution.metadata["similarity_context"] = pipeline_context.get("similarity_context")
            elif stage.name == StageName.REASONING.value:
                execution.reasoning_review = pipeline_context.get("reasoning_review")
            elif stage.name == StageName.INTELLIGENCE.value:
                execution.intelligence_report = pipeline_context.get("intelligence_report")

        execution.duration_ms = (time.perf_counter() - start) * 1000
        execution.completed_at = _now()
        execution.status = PipelineStatus.COMPLETED.value
        execution.metrics = self._metrics.from_execution(execution)
        return execution
