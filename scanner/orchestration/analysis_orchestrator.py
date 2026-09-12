# -*- coding: utf-8 -*-
"""Market analysis orchestrator — coordinates all platform components."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .aggregator import MarketAnalysisAggregator
from .cache import StageCache
from .execution_context import ExecutionContext
from .result import AnalysisStatus, MarketAnalysis, StageExecutionResult
from .retry import RetryHandler, RetryPolicy
from .stage import HandlerStage, Stage, StageRunner
from .stage_handlers import (
    aggregation_handler,
    decision_ai_handler,
    knowledge_handler,
    load_market_handler,
    prediction_handler,
    reasoning_handler,
    research_handler,
    similarity_handler,
)
from .timeout import TimeoutHandler, TimeoutPolicy
from .workflow import OPTIONAL_STAGES, WorkflowDefinition, WorkflowStage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AnalysisOrchestrator:
    """Production orchestration layer — execution order, retries, timeouts, caching."""

    def __init__(self, *,
                 workflow: WorkflowDefinition | None = None,
                 stages: dict[str, Stage] | None = None,
                 retry: RetryHandler | None = None,
                 timeout: TimeoutHandler | None = None,
                 cache: StageCache | None = None,
                 aggregator: MarketAnalysisAggregator | None = None,
                 knowledge_service: Any | None = None,
                 reasoning_service: Any | None = None,
                 similarity_service: Any | None = None,
                 research_service: Any | None = None,
                 predictive_service: Any | None = None,
                 decision_service: Any | None = None,
                 model_id: str = "",
                 feature_columns: list[str] | None = None) -> None:
        self._workflow = workflow or WorkflowDefinition()
        self._retry = retry or RetryHandler()
        self._timeout = timeout or TimeoutHandler()
        self._cache = cache or StageCache()
        self._aggregator = aggregator or MarketAnalysisAggregator()
        self._runner = StageRunner()
        self._stages = stages or self._default_stages(
            knowledge_service, reasoning_service, similarity_service,
            research_service, predictive_service, decision_service,
            model_id, feature_columns,
        )
        self._executions: dict[str, MarketAnalysis] = {}

    def _default_stages(self, ks, rs, ss, res, pred, dec, model_id, feat_cols) -> dict[str, Stage]:
        return {
            WorkflowStage.LOAD_MARKET.value: HandlerStage(
                WorkflowStage.LOAD_MARKET.value, load_market_handler),
            WorkflowStage.KNOWLEDGE.value: HandlerStage(
                WorkflowStage.KNOWLEDGE.value, knowledge_handler(ks), cacheable=True),
            WorkflowStage.REASONING.value: HandlerStage(
                WorkflowStage.REASONING.value, reasoning_handler(rs)),
            WorkflowStage.SIMILARITY.value: HandlerStage(
                WorkflowStage.SIMILARITY.value, similarity_handler(ss),
                optional=True, cacheable=True),
            WorkflowStage.RESEARCH.value: HandlerStage(
                WorkflowStage.RESEARCH.value, research_handler(res),
                optional=True, cacheable=True),
            WorkflowStage.PREDICTION.value: HandlerStage(
                WorkflowStage.PREDICTION.value,
                prediction_handler(pred, model_id=model_id, feature_columns=feat_cols),
                optional=True),
            WorkflowStage.DECISION_AI.value: HandlerStage(
                WorkflowStage.DECISION_AI.value, decision_ai_handler(dec),
                optional=True),
            WorkflowStage.AGGREGATION.value: HandlerStage(
                WorkflowStage.AGGREGATION.value, aggregation_handler, optional=True),
        }

    def run(self, *,
            symbol: str,
            market: str = "crypto",
            timeframe: str = "4h",
            scan_source: dict[str, Any] | None = None,
            trade_rows: list[dict] | None = None,
            analysis_id: str | None = None) -> MarketAnalysis:
        aid = analysis_id or f"ana_{uuid.uuid4().hex[:16]}"
        ctx = ExecutionContext(
            analysis_id=aid,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            scan_source=dict(scan_source or {"symbol": symbol, "market": market,
                                             "timeframe": timeframe}),
            trade_rows=tuple(trade_rows or ()),
        )

        trace: list[StageExecutionResult] = []
        workflow_start = time.perf_counter()
        failed = False
        status = AnalysisStatus.COMPLETED.value

        for stage_name in self._workflow.stages:
            elapsed_ms = (time.perf_counter() - workflow_start) * 1000
            if elapsed_ms > self._timeout.policy.workflow_timeout_ms:
                status = AnalysisStatus.TIMEOUT.value
                break

            stage = self._stages.get(stage_name)
            if stage is None:
                continue

            cached = self._try_cache(stage, ctx)
            if cached is not None:
                ctx, result = self._runner.run(stage, ctx, cached_output=cached)
                trace.append(result)
                continue

            try:
                ctx, result = self._run_stage_with_retry(stage, ctx)
            except Exception as exc:
                result = StageExecutionResult(
                    stage=stage_name,
                    status=AnalysisStatus.FAILED.value,
                    error=str(exc),
                )
                ctx = ctx

            trace.append(result)

            if result.status == AnalysisStatus.COMPLETED.value and stage.cacheable:
                output = ctx.stage_outputs.get(stage_name, {})
                ckey = StageCache.context_key({
                    "symbol": ctx.symbol, "market": ctx.market,
                    "timeframe": ctx.timeframe, "stage": stage_name,
                })
                model_ver = output.get("model_version", "") if stage_name == "prediction" else ""
                self._cache.put(stage_name, ckey, output, model_version=model_ver)

            if result.status == AnalysisStatus.FAILED.value:
                if stage_name not in OPTIONAL_STAGES:
                    failed = True
                    status = AnalysisStatus.FAILED.value
                    break
                status = AnalysisStatus.PARTIAL.value

        if status == AnalysisStatus.COMPLETED.value and any(
            t.status == AnalysisStatus.SKIPPED.value for t in trace
        ):
            status = AnalysisStatus.PARTIAL.value

        analysis = self._aggregator.aggregate(
            ctx, trace=trace, analysis_id=aid, status=status,
        )
        self._executions[aid] = analysis
        return analysis

    def _run_stage_with_retry(self, stage: Stage,
                              ctx: ExecutionContext) -> tuple[ExecutionContext, StageExecutionResult]:
        def run_once() -> tuple[ExecutionContext, StageExecutionResult]:
            return self._timeout.run_with_timeout(
                lambda: self._runner.run(stage, ctx),
                timeout_ms=self._timeout.policy.stage_timeout_ms,
            )

        result_pair, retries = self._retry.execute(run_once, stage_name=stage.name)
        ctx_out, stage_result = result_pair
        stage_result.retry_count = retries
        return ctx_out, stage_result

    def _try_cache(self, stage: Stage, ctx: ExecutionContext) -> dict[str, Any] | None:
        if not stage.cacheable:
            return None
        ckey = StageCache.context_key({
            "symbol": ctx.symbol, "market": ctx.market,
            "timeframe": ctx.timeframe, "stage": stage.name,
        })
        return self._cache.get(stage.name, ckey)

    def status(self, analysis_id: str) -> dict[str, Any] | None:
        analysis = self._executions.get(analysis_id)
        if not analysis:
            return None
        return self._aggregator.summarize(analysis)

    def get_analysis(self, analysis_id: str) -> MarketAnalysis | None:
        return self._executions.get(analysis_id)
