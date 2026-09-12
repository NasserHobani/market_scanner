# -*- coding: utf-8 -*-
"""Unit tests for scanner.pipeline — run: python tests_pipeline.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.knowledge import KnowledgeRepository, KnowledgeService
from scanner.pipeline import (
    EventBus,
    PipelineService,
    PipelineStatus,
    PipelineStore,
    ValidationError,
)
from scanner.pipeline.coordinator import PipelineCoordinatorImpl
from scanner.pipeline.validation import (
    validate_knowledge_output,
    validate_scan_source,
)
from scanner.reasoning import ReasoningService
from scanner.intelligence import IntelligenceService
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


CANDLE = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)

SCAN_SOURCE = {
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "candle_time": CANDLE,
    "close": 65000.0,
    "open": 64500.0,
    "high": 65200.0,
    "low": 64400.0,
    "volume": 1200.0,
    "score": 72.0,
    "decision": "buy",
    "htf": 1,
    "liquidity": "high",
    "components": {"trend": 1, "rsi": 1},
    "context": {"rsi": 58.2, "atr_pct": 2.1},
    "market_context": {"regime": "bullish", "regime_score": 1},
    "recommendation": {
        "action": "now", "side": "buy", "entry": 65000, "stop": 64000,
        "targets": [67000], "rr": 2.0, "confidence": 0.75,
        "grade": "A", "reasons": ["score 72"],
        "analysis": {
            "candles": [{"name": "hammer"}],
            "price_action": {"trend": "up", "sweeps": [{"side": "buy"}]},
        },
    },
}

TRADE_SOURCE = {
    "trade_id": 1,
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "side": "buy",
    "status": "won",
    "entry": 65000,
    "stop": 64000,
    "target1": 67000,
    "r_multiple": 2.0,
    "signal_at": CANDLE,
    "closed_at": datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc),
    "grade": "A",
    "factors": ["htf", "confluence"],
}

OUTCOME_SOURCE = {
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "status": "won",
    "r_multiple": 2.0,
    "outcome_class": "winner",
    "signal_at": CANDLE,
    "closed_at": datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc),
}


def _trade_rows(n: int = 10) -> list[dict]:
    rows = []
    for i in range(n):
        won = i % 3 != 0
        rows.append({
            "status": WON if won else LOST,
            "r_multiple": 1.5 if won else -1.0,
            "factors": ["htf", "confluence"],
            "market": "crypto",
            "timeframe": "4h",
            "grade": "A",
            "closed_at": datetime(2025, 1, 1 + i, 12, 0, tzinfo=timezone.utc),
        })
    return rows


# ── Validation ───────────────────────────────────────────────────────────────

check("validate scan source ok", len(validate_scan_source(SCAN_SOURCE)) == 0)
check("validate scan missing symbol",
      "symbol" in str(validate_scan_source({"market": "crypto", "timeframe": "4h"})))
check("validate knowledge output",
      len(validate_knowledge_output({"event_id": "ke_abc", "knowledge_ids": {}})) == 0)

# ── Setup temp stores ────────────────────────────────────────────────────────

tmpdir = tempfile.mkdtemp()
knowledge_repo = KnowledgeRepository(path=Path(tmpdir) / "knowledge.jsonl")
pipeline_store = PipelineStore(path=Path(tmpdir) / "pipeline.jsonl")
knowledge = KnowledgeService(repository=knowledge_repo)
event_bus = EventBus()
events_received: list[str] = []
event_bus.subscribe("*", lambda e: events_received.append(e.event_type))

svc = PipelineService(
    knowledge_service=knowledge,
    store=pipeline_store,
    event_bus=event_bus,
)

# ── Scan Pipeline ────────────────────────────────────────────────────────────

scan_result = svc.run_scan_pipeline(SCAN_SOURCE, trade_rows=_trade_rows())
check("scan pipeline completed", scan_result["status"] == PipelineStatus.COMPLETED.value,
      scan_result["status"])
check("scan pipeline has event_id", scan_result["event_id"].startswith("ke_"),
      scan_result["event_id"])
check("scan pipeline knowledge_ids", bool(scan_result["knowledge_ids"]))
check("scan pipeline reasoning", scan_result["reasoning_review"] is not None)
check("scan pipeline reasoning verdict",
      scan_result["reasoning_review"].get("verdict") in ("aligned", "caution", "misaligned"))
check("scan pipeline intelligence", scan_result["intelligence_report"] is not None)
check("scan pipeline stages", len(scan_result["stages"]) >= 4,
      str(len(scan_result["stages"])))
check("scan pipeline version", scan_result["pipeline_version"] == "2.1.0")
check("scan pipeline duration", scan_result["duration_ms"] > 0)

# ── Scan without trade rows (intelligence skipped) ───────────────────────────

scan_no_intel = svc.run_scan_pipeline(SCAN_SOURCE)
intel_stages = [s for s in scan_no_intel["stages"] if s["stage"] == "intelligence"]
check("intelligence skipped without trade_rows",
      intel_stages and intel_stages[0]["status"] == PipelineStatus.SKIPPED.value,
      str(intel_stages))

# ── Trade Pipeline (lifecycle) ─────────────────────────────────────────────────

trade_result = svc.run_trade_pipeline(
    scan_source=SCAN_SOURCE,
    trade_source=TRADE_SOURCE,
    outcome_source=OUTCOME_SOURCE,
    trade_rows=_trade_rows(),
)
check("trade pipeline completed", trade_result["status"] == PipelineStatus.COMPLETED.value)
check("trade pipeline type", trade_result["pipeline_type"] == "trade")
check("trade pipeline has reasoning", trade_result["reasoning_review"] is not None)

# ── Status and History ───────────────────────────────────────────────────────

status = svc.status(scan_result["execution_id"])
check("status returns execution", status["execution_id"] == scan_result["execution_id"])
history = svc.history(limit=10)
check("history has records", len(history) >= 2, str(len(history)))
filtered = svc.history(pipeline_type="scan")
check("history filter by type", all(h["pipeline_type"] == "scan" for h in filtered))

# ── Events ───────────────────────────────────────────────────────────────────

check("events published", len(events_received) > 0, str(len(events_received)))
check("KnowledgeCaptured event", "KnowledgeCaptured" in events_received)
check("ReasoningCompleted event", "ReasoningCompleted" in events_received)
check("PipelineCompleted event", "PipelineCompleted" in events_received)

# ── Metrics ──────────────────────────────────────────────────────────────────

metrics = svc.get_metrics()
check("metrics total_executions", metrics["total_executions"] >= 2)
check("metrics completed", metrics["completed"] >= 2)
check("metrics avg_duration", metrics["avg_duration_ms"] > 0)

# ── Rebuild Trade ────────────────────────────────────────────────────────────

event_id = scan_result["event_id"]
rebuild = svc.rebuild_trade(event_id, trade_rows=_trade_rows())
check("rebuild completed", rebuild["status"] == PipelineStatus.COMPLETED.value)
check("rebuild skips knowledge",
      any(s["stage"] == "knowledge" and s["status"] == "skipped" for s in rebuild["stages"]))
check("rebuild has reasoning", rebuild["reasoning_review"] is not None)

# ── Coordinator Retry ────────────────────────────────────────────────────────

coordinator = PipelineCoordinatorImpl(
    knowledge_service=knowledge,
    reasoning_service=ReasoningService(),
    intelligence_service=IntelligenceService(),
    store=pipeline_store,
    event_bus=EventBus(),
)

# Force validation failure
bad_context = {"capture_mode": "scan", "scan_source": {"market": "crypto"}}
bad_exec = coordinator.execute("scan", bad_context)
check("bad scan fails", bad_exec.status == PipelineStatus.FAILED.value)
check("bad scan has error", len(bad_exec.errors) > 0)
check("failed execution persisted",
      coordinator.status(bad_exec.execution_id).status == PipelineStatus.FAILED.value)

retry_result = coordinator.retry(bad_exec.execution_id, stage="knowledge")
check("retry creates new execution", retry_result.execution_id != bad_exec.execution_id)

# ── Pipeline validation error ──────────────────────────────────────────────────

try:
    from scanner.pipeline.validation import raise_if_errors
    raise_if_errors(["test error"], stage="knowledge")
    check("ValidationError raised", False, "no exception")
except ValidationError as exc:
    check("ValidationError raised", True)
    check("ValidationError has errors", len(exc.errors) > 0)

# ── Report ───────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Pipeline Tests: {passed} passed, {failed} failed / {len(results)} total")
print(f"{'='*60}")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    suffix = f"  ({extra})" if extra and not ok else ""
    print(f"  [{mark}] {name}{suffix}")

sys.exit(1 if failed else 0)
