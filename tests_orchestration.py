# -*- coding: utf-8 -*-
"""Unit tests for scanner.orchestration — run: python tests_orchestration.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.orchestration import (
    AnalysisOrchestrator,
    AnalysisService,
    AnalysisStatus,
    ExecutionContext,
    HandlerStage,
    MarketAnalysisAggregator,
    RetryHandler,
    RetryPolicy,
    StageCache,
    StageRunner,
    TimeoutHandler,
    TimeoutPolicy,
    WorkflowDefinition,
    WorkflowStage,
)
from scanner.orchestration.scheduler import AnalysisScheduler
from scanner.orchestration.stage_handlers import load_market_handler
from scanner.orchestration.timeout import TimeoutError as OrchestrationTimeoutError

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


SCAN = {
    "symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h",
    "close": 65000.0, "score": 72.0, "htf": 1,
    "candle_time": "2025-06-01T12:00:00+00:00",
    "components": {"trend": 1, "rsi": 1},
    "context": {"rsi": 55.0, "atr_pct": 2.1},
    "recommendation": {"action": "now", "side": "buy", "confidence": 0.75},
}

# ── Mock handlers ────────────────────────────────────────────────────────────

def mock_knowledge(ctx):
    return {"knowledge_context": {"event_id": "evt_001", "symbol": ctx.symbol},
            "event_id": "evt_001"}

def mock_reasoning(ctx):
    return {"reasoning": {"verdict": "aligned", "engine_confidence": 0.8,
                          "evidence": {"items": [{"evidence_id": "ev1", "label": "Trend",
                                                   "direction": "supports", "confidence": 0.8,
                                                   "category": "trend", "source": "test"}]}}}

def mock_similarity(ctx):
    return {"similarity": {"available": True, "match_count": 5, "average_win_rate": 60.0}}

def mock_research(ctx):
    return {"research": {"statistics": {"win_rate": 65.0}, "row_count": 30}}

def mock_prediction(ctx):
    return {"prediction": {"prediction": 1.0, "probability": 0.7, "confidence": 0.7,
                           "model_id": "mdl_test", "model_version": "1.0.0"}}

def mock_decision(ctx):
    return {"decision_review": {"review_id": "airev_test", "review_type": "trade_review",
                                "llm_invoked": False}}

def mock_aggregation(ctx):
    return {"aggregated": True}


def build_mock_orchestrator(**kwargs):
    stages = {
        WorkflowStage.LOAD_MARKET.value: HandlerStage(
            WorkflowStage.LOAD_MARKET.value, load_market_handler),
        WorkflowStage.KNOWLEDGE.value: HandlerStage(
            WorkflowStage.KNOWLEDGE.value, mock_knowledge, cacheable=True),
        WorkflowStage.REASONING.value: HandlerStage(
            WorkflowStage.REASONING.value, mock_reasoning),
        WorkflowStage.SIMILARITY.value: HandlerStage(
            WorkflowStage.SIMILARITY.value, mock_similarity,
            optional=True, cacheable=True),
        WorkflowStage.RESEARCH.value: HandlerStage(
            WorkflowStage.RESEARCH.value, mock_research,
            optional=True, cacheable=True),
        WorkflowStage.PREDICTION.value: HandlerStage(
            WorkflowStage.PREDICTION.value, mock_prediction, optional=True),
        WorkflowStage.DECISION_AI.value: HandlerStage(
            WorkflowStage.DECISION_AI.value, mock_decision, optional=True),
        WorkflowStage.AGGREGATION.value: HandlerStage(
            WorkflowStage.AGGREGATION.value, mock_aggregation, optional=True),
    }
    return AnalysisOrchestrator(
        stages=stages,
        retry=RetryHandler(RetryPolicy(max_retries=1, backoff_ms=10)),
        timeout=TimeoutHandler(TimeoutPolicy(stage_timeout_ms=5000, workflow_timeout_ms=30000)),
        cache=StageCache(ttl_seconds=60),
        **kwargs,
    )

# ── Execution Context ────────────────────────────────────────────────────────

ctx = ExecutionContext(analysis_id="ana_test", symbol="BTCUSDT", market="crypto", timeframe="4h")
check("Context immutable symbol", ctx.symbol == "BTCUSDT")
updated = ctx.with_updates(symbol="ETHUSDT")
check("Context with_updates", updated.symbol == "ETHUSDT" and ctx.symbol == "BTCUSDT")
check("Context to_dict", "analysis_id" in ctx.to_dict())

# ── Stage Runner ─────────────────────────────────────────────────────────────

stage = HandlerStage("load_market", load_market_handler)
runner = StageRunner()
ctx2 = ExecutionContext(analysis_id="ana_1", scan_source=SCAN)
ctx3, result = runner.run(stage, ctx2)
check("StageRunner load_market", result.status == AnalysisStatus.COMPLETED.value)
check("StageRunner symbol set", ctx3.symbol == "BTCUSDT")

# ── Retry ────────────────────────────────────────────────────────────────────

calls = {"n": 0}
def flaky():
    calls["n"] += 1
    if calls["n"] < 2:
        raise ValueError("transient")
    return "ok"

val, retries = RetryHandler(RetryPolicy(max_retries=2, backoff_ms=10)).execute(flaky)
check("Retry succeeds", val == "ok" and retries == 1)

# ── Timeout ────────────────────────────────────────────────────────────────

fast = TimeoutHandler().run_with_timeout(lambda: 42, timeout_ms=1000)
check("Timeout fast op", fast == 42)

# ── Cache ──────────────────────────────────────────────────────────────────

cache = StageCache()
cache.put("knowledge", "key1", {"data": 1})
cached = cache.get("knowledge", "key1")
check("Cache hit", cached == {"data": 1})
check("Cache miss", cache.get("knowledge", "key_missing") is None)
check("Cache invalidate", cache.invalidate("knowledge") == 1)

# ── Aggregator ─────────────────────────────────────────────────────────────

agg = MarketAnalysisAggregator()
from scanner.orchestration.result import StageExecutionResult
trace = [StageExecutionResult(stage="knowledge", status="completed")]
analysis = agg.aggregate(ctx3, trace=trace, analysis_id="ana_agg")
check("Aggregator analysis_id", analysis.analysis_id == "ana_agg")
check("Aggregator trace", len(analysis.execution_trace) == 1)
check("Aggregator to_dict", "version" in analysis.to_dict())

# ── Full Orchestrator ──────────────────────────────────────────────────────

orch = build_mock_orchestrator()
result_analysis = orch.run(symbol="BTCUSDT", market="crypto", timeframe="4h", scan_source=SCAN)
check("Orchestrator completed", result_analysis.status in (
    AnalysisStatus.COMPLETED.value, AnalysisStatus.PARTIAL.value), result_analysis.status)
check("Orchestrator analysis_id", result_analysis.analysis_id.startswith("ana_"))
check("Orchestrator has knowledge", bool(result_analysis.knowledge))
check("Orchestrator has reasoning", bool(result_analysis.reasoning))
check("Orchestrator has similarity", bool(result_analysis.similarity))
check("Orchestrator has prediction", bool(result_analysis.prediction))
check("Orchestrator has decision", bool(result_analysis.decision_review))
check("Orchestrator trace", len(result_analysis.execution_trace) >= 5,
      str(len(result_analysis.execution_trace)))

status = orch.status(result_analysis.analysis_id)
check("Orchestrator status", status is not None and status["symbol"] == "BTCUSDT")

# ── Cache hit on second run ──────────────────────────────────────────────────

orch2 = build_mock_orchestrator()
a1 = orch2.run(symbol="BTCUSDT", market="crypto", timeframe="4h", scan_source=SCAN)
a2 = orch2.run(symbol="BTCUSDT", market="crypto", timeframe="4h", scan_source=SCAN)
cached_stages = [t for t in a2.execution_trace if t.get("cached")]
check("Cache used on rerun", len(cached_stages) >= 1, str(len(cached_stages)))

# ── Optional stage failure ─────────────────────────────────────────────────

def failing_similarity(ctx):
    raise RuntimeError("similarity unavailable")

stages_fail = {
    WorkflowStage.LOAD_MARKET.value: HandlerStage(
        WorkflowStage.LOAD_MARKET.value, load_market_handler),
    WorkflowStage.KNOWLEDGE.value: HandlerStage(
        WorkflowStage.KNOWLEDGE.value, mock_knowledge),
    WorkflowStage.REASONING.value: HandlerStage(
        WorkflowStage.REASONING.value, mock_reasoning),
    WorkflowStage.SIMILARITY.value: HandlerStage(
        WorkflowStage.SIMILARITY.value, failing_similarity, optional=True),
    WorkflowStage.AGGREGATION.value: HandlerStage(
        WorkflowStage.AGGREGATION.value, mock_aggregation, optional=True),
}
orch_partial = AnalysisOrchestrator(stages=stages_fail)
partial = orch_partial.run(symbol="BTCUSDT", scan_source=SCAN)
check("Partial on optional fail", partial.status in (
    AnalysisStatus.PARTIAL.value, AnalysisStatus.COMPLETED.value), partial.status)

# ── Required stage failure ───────────────────────────────────────────────────

def failing_knowledge(ctx):
    raise RuntimeError("knowledge down")

stages_req_fail = {
    WorkflowStage.LOAD_MARKET.value: HandlerStage(
        WorkflowStage.LOAD_MARKET.value, load_market_handler),
    WorkflowStage.KNOWLEDGE.value: HandlerStage(
        WorkflowStage.KNOWLEDGE.value, failing_knowledge),
    WorkflowStage.AGGREGATION.value: HandlerStage(
        WorkflowStage.AGGREGATION.value, mock_aggregation, optional=True),
}
orch_fail = AnalysisOrchestrator(
    stages=stages_req_fail,
    retry=RetryHandler(RetryPolicy(max_retries=0)),
)
failed = orch_fail.run(symbol="BTCUSDT", scan_source=SCAN)
check("Failed on required stage", failed.status == AnalysisStatus.FAILED.value)

# ── AnalysisService ──────────────────────────────────────────────────────────

svc = AnalysisService(orchestrator=build_mock_orchestrator())
svc_result = svc.analyze_market(symbol="BTCUSDT", market="crypto", timeframe="4h", scan_source=SCAN)
check("Service analyze_market", svc_result.symbol == "BTCUSDT")

svc_symbol = svc.analyze_symbol("ETHUSDT", market="crypto", timeframe="1h")
check("Service analyze_symbol", svc_symbol.symbol == "ETHUSDT")

svc_strategy = svc.analyze_strategy("default", symbol="BTCUSDT", scan_source=SCAN)
check("Service analyze_strategy", svc_strategy.symbol == "BTCUSDT")

svc_status = svc.status(svc_result.analysis_id)
check("Service status", svc_status is not None)

job = svc.enqueue("BTCUSDT", market="crypto", scan_source=SCAN)
check("Service enqueue", job["status"] == "queued")

ran = svc.run_queued()
check("Service run_queued", ran is not None and ran["status"] == "completed")

# ── Scheduler ──────────────────────────────────────────────────────────────

sched = AnalysisScheduler()
j1 = sched.enqueue("BTCUSDT")
j2 = sched.enqueue("ETHUSDT")
check("Scheduler enqueue", len(sched.list_jobs()) == 2)
check("Scheduler job id", j1.job_id.startswith("job_"))

# ── Workflow ───────────────────────────────────────────────────────────────

wf = WorkflowDefinition()
check("Workflow stages", len(wf.stages) == 8)
check("Workflow first stage", wf.stages[0] == "load_market")
check("Workflow last stage", wf.stages[-1] == "aggregation")

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Orchestration Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
