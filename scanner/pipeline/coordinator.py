# -*- coding: utf-8 -*-
"""Pipeline coordinator — execution, retry, validation, timing."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .event_bus import EventBus
from .events import (
    DomainEvent,
    intelligence_completed,
    knowledge_captured,
    pipeline_completed,
    pipeline_failed,
    reasoning_completed,
    similarity_completed,
    stage_completed,
    stage_failed,
    stage_started,
)
from .metrics import MetricsCollector
from .persistence import PipelineStore
from .stages import IntelligenceStage, KnowledgeStage, ReasoningStage, SimilarityStage
from .state import PIPELINE_VERSION, PipelineExecution, PipelineStatus, StageName, StageResult
from .validation import ValidationError, raise_if_errors


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineCoordinatorImpl:
    """Orchestrate pipeline stages with validation, timing, and failure isolation."""

    def __init__(self, *,
                 knowledge_service: Any,
                 reasoning_service: Any,
                 intelligence_service: Any,
                 similarity_service: Any | None = None,
                 store: PipelineStore | None = None,
                 event_bus: EventBus | None = None,
                 max_retries: int = 2) -> None:
        self.store = store or PipelineStore()
        self.event_bus = event_bus or EventBus()
        self.metrics = MetricsCollector()
        self.max_retries = max_retries

        self._knowledge = KnowledgeStage(knowledge_service)
        self._similarity = SimilarityStage(similarity_service) if similarity_service else None
        self._reasoning = ReasoningStage(reasoning_service, knowledge_service)
        self._intelligence = IntelligenceStage(intelligence_service)

        self._stages = [self._knowledge]
        if self._similarity:
            self._stages.append(self._similarity)
        self._stages.extend([self._reasoning, self._intelligence])

    def execute(self, pipeline_type: str, context: dict[str, Any]) -> PipelineExecution:
        execution = PipelineExecution(
            execution_id=f"pex_{uuid.uuid4().hex[:16]}",
            pipeline_type=pipeline_type,
            pipeline_version=PIPELINE_VERSION,
            status=PipelineStatus.RUNNING.value,
            strategy_id=context.get("strategy_id", "default"),
            started_at=_now(),
            metadata=dict(context.get("metadata") or {}),
        )
        pipeline_context: dict[str, Any] = dict(context)
        start = time.perf_counter()
        failed = False

        for stage in self._stages:
            if stage.name == StageName.INTELLIGENCE.value and not pipeline_context.get("trade_rows"):
                execution.stages.append(StageResult(
                    stage=stage.name,
                    status=PipelineStatus.SKIPPED.value,
                    started_at=_now(),
                    completed_at=_now(),
                ))
                continue

            result = self._run_stage(stage, pipeline_context, execution)
            execution.stages.append(result)

            if result.status == PipelineStatus.FAILED.value:
                if getattr(stage, "optional", False):
                    pipeline_context.setdefault("similarity_context", {})
                    continue
                failed = True
                execution.errors.append(result.error or f"{stage.name} failed")
                self._publish(pipeline_failed(
                    execution_id=execution.execution_id,
                    event_id=execution.event_id,
                    payload={"stage": stage.name, "error": result.error},
                ))
                break

            if stage.name == StageName.KNOWLEDGE.value:
                pipeline_context.update({
                    "event_id": pipeline_context.get("event_id"),
                    "knowledge_ids": pipeline_context.get("knowledge_ids"),
                })
                execution.event_id = pipeline_context.get("event_id", "")
                execution.knowledge_ids = pipeline_context.get("knowledge_ids", {})
                self._publish(knowledge_captured(
                    execution_id=execution.execution_id,
                    event_id=execution.event_id,
                    payload={"knowledge_ids": execution.knowledge_ids},
                ))
            elif stage.name == StageName.SIMILARITY.value:
                execution.similarity_summary = pipeline_context.get("similarity_summary")
                execution.metadata["similarity_context"] = pipeline_context.get("similarity_context")
                sim_metrics = pipeline_context.get("similarity_metrics") or {}
                execution.metrics.setdefault("similarity", sim_metrics)
                self._publish(similarity_completed(
                    execution_id=execution.execution_id,
                    event_id=execution.event_id,
                    payload={
                        "match_count": (execution.similarity_summary or {}).get("match_count", 0),
                        "avg_similarity": (execution.similarity_summary or {}).get("avg_similarity"),
                    },
                ))
            elif stage.name == StageName.REASONING.value:
                execution.reasoning_review = pipeline_context.get("reasoning_review")
                self._publish(reasoning_completed(
                    execution_id=execution.execution_id,
                    event_id=execution.event_id,
                    payload={"verdict": (execution.reasoning_review or {}).get("verdict")},
                ))
            elif stage.name == StageName.INTELLIGENCE.value:
                execution.intelligence_report = pipeline_context.get("intelligence_report")
                self._publish(intelligence_completed(
                    execution_id=execution.execution_id,
                    event_id=execution.event_id,
                    payload={"insight_count": (
                        (execution.intelligence_report or {}).get("insights", {}).get("count", 0)
                    )},
                ))

        execution.duration_ms = (time.perf_counter() - start) * 1000
        execution.completed_at = _now()
        execution.status = (
            PipelineStatus.FAILED.value if failed else PipelineStatus.COMPLETED.value
        )
        execution.metrics = self.metrics.from_execution(execution)
        execution.metrics["records_processed"] = len(pipeline_context.get("trade_rows") or [])

        if not failed:
            self._publish(pipeline_completed(
                execution_id=execution.execution_id,
                event_id=execution.event_id,
                payload={"pipeline_type": pipeline_type, "duration_ms": execution.duration_ms},
            ))

        self.store.save(execution)
        return execution

    def retry(self, execution_id: str, *,
              stage: str | None = None) -> PipelineExecution:
        prior = self.store.load(execution_id)
        context: dict[str, Any] = {
            "strategy_id": prior.strategy_id,
            "event_id": prior.event_id,
            "knowledge_ids": prior.knowledge_ids,
            "similarity_context": prior.metadata.get("similarity_context"),
            "similarity_summary": prior.similarity_summary,
            "trade_rows": prior.metadata.get("trade_rows"),
            "scan_source": prior.metadata.get("scan_source"),
            "trade_source": prior.metadata.get("trade_source"),
            "outcome_source": prior.metadata.get("outcome_source"),
            "capture_mode": prior.metadata.get("capture_mode", "scan"),
            "metadata": prior.metadata,
        }
        retry_stage = stage or self._first_failed_stage(prior)
        if not retry_stage:
            return prior

        execution = PipelineExecution(
            execution_id=f"pex_{uuid.uuid4().hex[:16]}",
            pipeline_type=prior.pipeline_type,
            pipeline_version=PIPELINE_VERSION,
            status=PipelineStatus.RUNNING.value,
            event_id=prior.event_id,
            strategy_id=prior.strategy_id,
            started_at=_now(),
            metadata=dict(prior.metadata),
        )
        start = time.perf_counter()
        failed = False
        retry_started = False

        for st in self._stages:
            if st.name != retry_stage and not retry_started:
                prior_stage = next((s for s in prior.stages if s.stage == st.name), None)
                if prior_stage and prior_stage.status == PipelineStatus.COMPLETED.value:
                    execution.stages.append(prior_stage)
                    continue
                execution.stages.append(StageResult(
                    stage=st.name,
                    status=PipelineStatus.SKIPPED.value,
                    started_at=_now(),
                    completed_at=_now(),
                ))
                continue

            retry_started = True
            pipeline_context = context

            result = self._run_stage(st, pipeline_context, execution, force_retry=True)
            execution.stages.append(result)
            if result.status == PipelineStatus.FAILED.value:
                failed = True
                execution.errors.append(result.error or f"{st.name} retry failed")
                break
            context.update(pipeline_context)

            if st.name == StageName.KNOWLEDGE.value:
                execution.knowledge_ids = context.get("knowledge_ids", {})
                execution.event_id = context.get("event_id", execution.event_id)
            elif st.name == StageName.SIMILARITY.value:
                execution.similarity_summary = context.get("similarity_summary")
            elif st.name == StageName.REASONING.value:
                execution.reasoning_review = context.get("reasoning_review")
            elif st.name == StageName.INTELLIGENCE.value:
                execution.intelligence_report = context.get("intelligence_report")

        execution.duration_ms = (time.perf_counter() - start) * 1000
        execution.completed_at = _now()
        execution.status = (
            PipelineStatus.FAILED.value if failed else PipelineStatus.COMPLETED.value
        )
        execution.metrics = self.metrics.from_execution(execution)
        self.store.save(execution)
        return execution

    def status(self, execution_id: str) -> PipelineExecution:
        return self.store.load(execution_id)

    def history(self, **kwargs: Any) -> list[PipelineExecution]:
        return self.store.history(**kwargs)

    def _run_stage(self, stage: Any, context: dict[str, Any],
                   execution: PipelineExecution,
                   *, force_retry: bool = False) -> StageResult:
        started = _now()
        t0 = time.perf_counter()
        retries = 0
        last_error: str | None = None

        self._publish(stage_started(
            execution_id=execution.execution_id,
            event_id=context.get("event_id", ""),
            payload={"stage": stage.name},
        ))

        input_errors = stage.validate_input(context)
        if input_errors and not (stage.name == StageName.INTELLIGENCE.value
                                  and context.get("skip_intelligence")):
            if stage.name == StageName.INTELLIGENCE.value and not context.get("trade_rows"):
                return StageResult(
                    stage=stage.name,
                    status=PipelineStatus.SKIPPED.value,
                    started_at=started,
                    completed_at=_now(),
                )
            last_error = "; ".join(input_errors)
            result = StageResult(
                stage=stage.name,
                status=PipelineStatus.FAILED.value,
                started_at=started,
                completed_at=_now(),
                duration_ms=(time.perf_counter() - t0) * 1000,
                error=last_error,
            )
            self._publish(stage_failed(
                execution_id=execution.execution_id,
                event_id=context.get("event_id", ""),
                payload={"stage": stage.name, "error": last_error},
            ))
            return result

        max_attempts = self.max_retries + 1 if force_retry else 1
        for attempt in range(max_attempts):
            try:
                output = stage.execute(context)
                output_errors = stage.validate_output(output)
                raise_if_errors(output_errors, stage=stage.name)
                context.update(output)
                completed = _now()
                result = StageResult(
                    stage=stage.name,
                    status=PipelineStatus.COMPLETED.value,
                    started_at=started,
                    completed_at=completed,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    retry_count=retries,
                    output_keys=list(output.keys()),
                )
                self._publish(stage_completed(
                    execution_id=execution.execution_id,
                    event_id=context.get("event_id", ""),
                    payload={"stage": stage.name, "duration_ms": result.duration_ms},
                ))
                return result
            except (ValidationError, Exception) as exc:
                last_error = str(exc)
                retries += 1
                if getattr(stage, "optional", False):
                    from .similarity_integration import build_similarity_summary
                    from .context import empty_similarity_context
                    context.setdefault("similarity_context", {})
                    context["similarity_context"] = empty_similarity_context().to_dict()
                    context["similarity_summary"] = build_similarity_summary(
                        None, event_id=context.get("event_id", ""),
                    ).to_dict()
                    return StageResult(
                        stage=stage.name,
                        status=PipelineStatus.COMPLETED.value,
                        started_at=started,
                        completed_at=_now(),
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        retry_count=retries,
                        error=last_error,
                        output_keys=["similarity_context"],
                    )
                if attempt < max_attempts - 1:
                    continue

        result = StageResult(
            stage=stage.name,
            status=PipelineStatus.FAILED.value,
            started_at=started,
            completed_at=_now(),
            duration_ms=(time.perf_counter() - t0) * 1000,
            retry_count=retries,
            error=last_error,
        )
        self._publish(stage_failed(
            execution_id=execution.execution_id,
            event_id=context.get("event_id", ""),
            payload={"stage": stage.name, "error": last_error},
        ))
        return result

    def _first_failed_stage(self, execution: PipelineExecution) -> str | None:
        for stage in execution.stages:
            if stage.status == PipelineStatus.FAILED.value:
                return stage.stage
        return None

    def _publish(self, event: DomainEvent) -> None:
        self.event_bus.publish(event)
