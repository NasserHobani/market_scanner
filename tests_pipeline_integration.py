# -*- coding: utf-8 -*-
"""Integration tests for pipeline + similarity — run: python tests_pipeline_integration.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.knowledge import KnowledgeRepository, KnowledgeService
from scanner.pipeline import NO_HISTORICAL_EVIDENCE, PipelineService, PipelineStatus
from scanner.pipeline.similarity_integration import build_similarity_context
from scanner.pipeline.persistence import PipelineStore
from scanner.similarity import SimilarityService
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


CANDLE = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)

SCAN_A = {
    "symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h",
    "candle_time": CANDLE, "close": 65000.0, "score": 72.0, "htf": 1,
    "liquidity": "high",
    "components": {"trend": 1, "rsi": 1, "obv_macd": 1, "vwap": 1, "spike": 0},
    "context": {"rsi": 58.2, "rvol": 1.4, "atr_pct": 2.1},
    "market_context": {"regime": "bullish", "regime_score": 1, "breadth_pct": 62.0},
    "recommendation": {
        "action": "now", "side": "buy", "grade": "A", "confidence": 0.75,
        "analysis": {
            "candles": [{"name": "hammer"}],
            "price_action": {"trend": "bullish", "sweeps": [{"side": "buy"}]},
        },
    },
}

SCAN_B = {**SCAN_A, "candle_time": datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc),
          "close": 65500.0, "score": 70.0}


def _trade_rows(n: int = 10) -> list[dict]:
    return [
        {"status": WON if i % 3 != 0 else LOST,
         "r_multiple": 1.5 if i % 3 != 0 else -1.0,
         "factors": ["htf"], "market": "crypto", "timeframe": "4h", "grade": "A",
         "closed_at": datetime(2025, 1, 1 + i, 12, 0, tzinfo=timezone.utc)}
        for i in range(n)
    ]


tmpdir = tempfile.mkdtemp()
repo = KnowledgeRepository(path=Path(tmpdir) / "knowledge.jsonl")
store = PipelineStore(path=Path(tmpdir) / "pipeline.jsonl")
ks = KnowledgeService(repository=repo)
sim = SimilarityService(knowledge_service=ks)
svc = PipelineService(knowledge_service=ks, similarity_service=sim, store=store)

# Seed historical knowledge
ks.capture_scan(SCAN_A)
ks.capture_scan(SCAN_B)

# ── Pipeline includes similarity stage ───────────────────────────────────────

result = svc.run_scan_pipeline(SCAN_A, trade_rows=_trade_rows())
check("pipeline completed", result["status"] == PipelineStatus.COMPLETED.value)
check("pipeline version 2.1", result["pipeline_version"] == "2.1.0")
check("has similarity stage",
      any(s["stage"] == "similarity" for s in result["stages"]))
check("similarity summary persisted", result.get("similarity_summary") is not None)
check("similarity summary has match_count",
      "match_count" in (result.get("similarity_summary") or {}))

sim_stage = next(s for s in result["stages"] if s["stage"] == "similarity")
check("similarity stage completed", sim_stage["status"] == PipelineStatus.COMPLETED.value)

# ── Reasoning consumes similarity evidence ───────────────────────────────────

review = result.get("reasoning_review") or {}
evidence_items = (review.get("evidence") or {}).get("items") or []
sim_evidence = [e for e in evidence_items if isinstance(e, dict) and (
    "similarity" in e.get("evidence_id", "") or "similarity" in e.get("source", "")
)]
check("reasoning has similarity evidence", len(sim_evidence) > 0, str(len(sim_evidence)))

# ── Intelligence consumes similarity statistics ───────────────────────────────

intel = result.get("intelligence_report") or {}
check("intelligence has similarity_statistics",
      "similarity_statistics" in intel)
if "similarity_statistics" in intel:
    check("similarity_statistics has match_count",
          "match_count" in intel["similarity_statistics"])

# ── Standalone similarity methods ────────────────────────────────────────────

standalone = svc.run_similarity(SCAN_A, event_id=result["event_id"])
check("run_similarity returns context", "similarity_context" in standalone)
check("run_similarity returns summary", "similarity_summary" in standalone)

sim_status = svc.similarity_status(execution_id=result["execution_id"])
check("similarity_status", sim_status.get("similarity_summary") is not None)

rebuild_sim = svc.rebuild_similarity(result["event_id"])
check("rebuild_similarity", "similarity_context" in rebuild_sim)

# ── Failure isolation ────────────────────────────────────────────────────────

empty_ctx = build_similarity_context(None)
check("empty context has no evidence msg",
      NO_HISTORICAL_EVIDENCE in empty_ctx.historical_evidence)
check("empty context not available", not empty_ctx.available)

# Broken similarity service — pipeline must continue
class BrokenSimilarity:
    def find_similar(self, *a, **kw):
        raise RuntimeError("similarity broken")

broken_svc = PipelineService(
    knowledge_service=ks,
    similarity_service=BrokenSimilarity(),  # type: ignore
    store=PipelineStore(path=Path(tmpdir) / "pipeline2.jsonl"),
)
broken_result = broken_svc.run_scan_pipeline(SCAN_B, trade_rows=_trade_rows())
check("pipeline continues on similarity failure",
      broken_result["status"] == PipelineStatus.COMPLETED.value)
check("reasoning still produced",
      broken_result.get("reasoning_review") is not None)

# ── Metrics ──────────────────────────────────────────────────────────────────

metrics = result.get("metrics") or {}
check("execution has metrics", bool(metrics))

# ── Report ───────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Pipeline Integration Tests: {passed} passed, {failed} failed / {len(results)} total")
print(f"{'='*60}")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    suffix = f"  ({extra})" if extra and not ok else ""
    print(f"  [{mark}] {name}{suffix}")

sys.exit(1 if failed else 0)
