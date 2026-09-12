# -*- coding: utf-8 -*-
"""Unit tests for scanner.reasoning — run: python tests_reasoning.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.knowledge import KnowledgeService
from scanner.reasoning import (
    ConfidenceEngine,
    ContradictionEngine,
    DecisionTree,
    EvidenceEngine,
    ExplainabilityEngine,
    ReasoningContext,
    ReasoningEngine,
    ReasoningService,
)

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
    "decision": "شراء",
    "htf": 1,
    "liquidity": "high",
    "quote_volume": 5_000_000.0,
    "ready": True,
    "blocker": "",
    "components": {
        "trend": 1, "rsi": 1, "obv_macd": 1, "vwap": 1, "spike": 1,
        "div": -1,
    },
    "context": {"rsi": 58.2, "rvol": 1.4, "atr_pct": 2.1, "htf_text": "صاعد"},
    "market_context": {
        "regime": "صاعد", "regime_score": 1,
        "breadth_pct": 62.0, "volatility": "تذبذب طبيعي",
    },
    "recommendation": {
        "action": "now", "side": "buy", "entry": 65000, "stop": 64000,
        "targets": [67000, 69000], "rr": 2.0, "confidence": 0.75,
        "grade": "A", "reasons": ["الدرجة 72", "فيبوناتشي"],
        "votes": 3.2, "breakdown": [{"label": "الدرجة", "value": 1.0}],
        "analysis": {
            "candles": [{"name": "hammer"}],
            "chart_patterns": [{"name": "ascending_triangle"}],
            "elliott": {"direction": "up", "current_wave": 3},
            "price_action": {
                "trend": "صاعد",
                "structure_events": [{"kind": "bos", "level": 64000}],
                "zones": [{"kind": "demand", "top": 64500, "bottom": 64000}],
                "sweeps": [{"side": "buy", "level": 63800}],
            },
            "channel": {"kind": "ascending", "zone": "mid"},
        },
    },
}


# Build knowledge context
with tempfile.TemporaryDirectory() as tmp:
    from scanner.knowledge import KnowledgeRepository
    from scanner.knowledge.snapshot_builder import make_event_id

    eid = make_event_id(symbol="BTCUSDT", market="crypto", timeframe="4h", candle_time=CANDLE)
    repo = KnowledgeRepository(Path(tmp) / "k.jsonl")
    ks = KnowledgeService(repository=repo)
    ks.capture_scan({**SCAN_SOURCE, "event_id": eid})
    kctx = ks.get_context(eid, recent_performance={"rolling_30": 0.2})

# ── ReasoningContext ──
rctx = ReasoningContext.from_knowledge(kctx)
check("reasoning context event", rctx.event_id == eid)
check("reasoning context has reco", rctx.recommendation_snapshot is not None)

# ── Evidence Engine ──
engine = EvidenceEngine()
bundle = engine.build(kctx)
check("evidence count", len(bundle.items) >= 5)
check("bullish trend evidence",
      any("Bullish Trend" in e.label for e in bundle.items))
check("evidence has trace", all(e.trace for e in bundle.items))
check("evidence has source", all(e.source for e in bundle.items))

# ── Contradiction Engine ──
cx = ContradictionEngine().analyze(bundle)
check("contradictions traceable",
      all(c.supporting_id and c.contradicting_id for c in cx.items) if cx.items else True)

# ── Confidence Engine ──
conf = ConfidenceEngine().compute(bundle, contradiction_count=len(cx.items))
check("confidence overall range", 0 <= conf.overall <= 1)
check("confidence breakdown", "trend" in conf.categories or len(conf.categories) > 0)
check("confidence reproducible",
      conf.overall == ConfidenceEngine().compute(bundle, contradiction_count=len(cx.items)).overall)

# ── Decision Tree ──
tree = DecisionTree().run(kctx, bundle)
check("decision tree stages", len(tree.stages) >= 5)
check("decision tree has status", all(s.status for s in tree.stages))

# ── Explainability ──
exp = ExplainabilityEngine().explain(bundle, contradictions=cx, confidence=conf)
check("explanation strengths", isinstance(exp.trade_strengths, list))
check("explanation structured", "trade_weaknesses" in exp.to_dict())

# ── Full pipeline ──
review = ReasoningEngine().run(rctx)
check("review verdict", review.verdict in ("aligned", "caution", "misaligned"))
check("review agreement", 0 <= review.agreement_score <= 1)
check("review has evidence", review.evidence.get("count", 0) > 0)
check("review has confidence breakdown", "overall" in review.confidence)
check("review has warnings list", isinstance(review.warnings, list))
check("review does not change action", review.action == "now")

# ── ReasoningService ──
svc = ReasoningService()
review2 = svc.review_from_knowledge(kctx)
check("service review", review2.event_id == eid)
partial = svc.explain(kctx)
check("service partial", "evidence" in partial and "confidence" in partial)

# ── Interfaces ──
from scanner.reasoning.interfaces import ReasoningProvider
check("ReasoningProvider protocol", isinstance(ReasoningEngine(), ReasoningProvider))

# ── Round-trip ──
d = review.to_dict()
check("review round-trip", d["verdict"] == review.verdict and "agreement_pct" in d)

# ── Summary ──
passed = sum(1 for ok, _, _ in results if ok)
failed = [name for ok, name, extra in results if not ok]
print(f"\n{'✓' if not failed else '✗'} {passed}/{len(results)} اختباراً")
for ok, name, extra in results:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {name}"
    if extra:
        line += f" — {extra}"
    print(line)
if failed:
    sys.exit(1)
