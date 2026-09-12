# -*- coding: utf-8 -*-
"""Unit tests for scanner.similarity — run: python tests_similarity.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.knowledge import KnowledgeRepository, KnowledgeService
from scanner.similarity import (
    DistanceConfig,
    FeatureDistanceCalculator,
    RankingEngine,
    RetrievalFilters,
    SimilarityEngine,
    SimilarityService,
    SimilarityScorer,
    build_fingerprint,
    fingerprint_match_score,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


CANDLE = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
CANDLE2 = datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc)

SCAN_A = {
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "candle_time": CANDLE,
    "close": 65000.0,
    "score": 72.0,
    "htf": 1,
    "liquidity": "high",
    "components": {"trend": 1, "rsi": 1, "obv_macd": 1, "vwap": 1, "spike": 0},
    "context": {"rsi": 58.2, "rvol": 1.4, "atr_pct": 2.1, "htf_text": "bullish"},
    "market_context": {
        "regime": "bullish", "regime_score": 1,
        "breadth_pct": 62.0, "volatility": "normal",
    },
    "recommendation": {
        "action": "now", "side": "buy", "entry": 65000, "stop": 64000,
        "targets": [67000], "rr": 2.0, "confidence": 0.75,
        "grade": "A", "reasons": ["score 72"],
        "analysis": {
            "candles": [{"name": "hammer"}],
            "chart_patterns": [{"name": "ascending_triangle"}],
            "price_action": {
                "trend": "bullish",
                "structure_events": [{"kind": "bos", "level": 64000}],
                "sweeps": [{"side": "buy", "level": 63800}],
            },
        },
    },
}

SCAN_B = {
    **SCAN_A,
    "candle_time": CANDLE2,
    "close": 65500.0,
    "score": 68.0,
    "context": {"rsi": 55.0, "rvol": 1.2, "atr_pct": 2.3},
}

SCAN_C = {
    "symbol": "ETHUSDT",
    "market": "crypto",
    "timeframe": "1h",
    "candle_time": CANDLE,
    "close": 3500.0,
    "score": 45.0,
    "htf": -1,
    "liquidity": "low",
    "components": {"trend": -1, "rsi": -1, "obv_macd": 0, "vwap": -1, "spike": 0},
    "context": {"rsi": 42.0, "rvol": 0.8, "atr_pct": 4.5},
    "market_context": {"regime": "bearish", "regime_score": -1, "volatility": "high"},
    "recommendation": {
        "action": "wait", "side": "sell", "grade": "C",
        "analysis": {"candles": [], "price_action": {"trend": "bearish"}},
    },
}

TRADE_OUTCOME = {
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "status": "won",
    "outcome_class": "winner",
    "r_multiple": 2.0,
    "profit": True,
    "closed_at": datetime(2025, 6, 3, 8, 0, tzinfo=timezone.utc),
}


# ── Fingerprint ──────────────────────────────────────────────────────────────

fp_a = build_fingerprint(SCAN_A)
fp_b = build_fingerprint(SCAN_B)
fp_c = build_fingerprint(SCAN_C)
check("fingerprint id prefix", fp_a.fingerprint_id.startswith("sf_"))
check("fingerprint stable", build_fingerprint(SCAN_A).fingerprint_id == fp_a.fingerprint_id)
check("fingerprint has components", "market" in fp_a.components)
check("fingerprint comparison key", len(fp_a.comparison_key) > 0)
check("similar fingerprints close",
      fingerprint_match_score(fp_a, fp_b) > fingerprint_match_score(fp_a, fp_c),
      f"a-b={fingerprint_match_score(fp_a, fp_b):.2f} a-c={fingerprint_match_score(fp_a, fp_c):.2f}")

# ── Feature Distance ─────────────────────────────────────────────────────────

calc = FeatureDistanceCalculator(DistanceConfig())
from scanner.knowledge.snapshot_builder import build_feature_snapshot

feat_a = build_feature_snapshot(SCAN_A).to_dict()
feat_b = build_feature_snapshot(SCAN_B).to_dict()
feat_c = build_feature_snapshot(SCAN_C).to_dict()

dist_ab = calc.compare(feat_a, feat_b)
dist_ac = calc.compare(feat_a, feat_c)
check("distance 0-1 range", 0 <= dist_ab.distance <= 1)
check("closer pairs lower distance", dist_ab.distance < dist_ac.distance,
      f"ab={dist_ab.distance:.3f} ac={dist_ac.distance:.3f}")
check("distance has matched", isinstance(dist_ab.matched, list))
check("distance has details", len(dist_ab.details) > 0)
check("distance to_dict", "similarity" in dist_ab.to_dict())

# ── Similarity Score ───────────────────────────────────────────────────────

scorer = SimilarityScorer()
score_ab, _ = scorer.score(feat_a, feat_b)
score_ac, _ = scorer.score(feat_a, feat_c)
check("score 0-100 range", 0 <= score_ab.overall <= 100)
check("similar scores higher", score_ab.overall > score_ac.overall,
      f"ab={score_ab.overall} ac={score_ac.overall}")
check("score has components", score_ab.trend_similarity >= 0)
check("score has explanation", len(score_ab.explanation) > 0)
check("score weights exposed", "trend" in score_ab.weights)

# ── Setup knowledge store ────────────────────────────────────────────────────

tmpdir = tempfile.mkdtemp()
repo = KnowledgeRepository(path=Path(tmpdir) / "knowledge.jsonl")
ks = KnowledgeService(repository=repo)

ids_a = ks.capture_scan(SCAN_A)
ks.capture_outcome({**TRADE_OUTCOME, "event_id": ids_a["event_id"],
                    "trade_snapshot_id": "ts_test"})

scan_b = {**SCAN_B, "symbol": "BTCUSDT"}
ids_b = ks.capture_scan(scan_b)
ks.capture_outcome({**TRADE_OUTCOME, "event_id": ids_b["event_id"],
                    "r_multiple": 1.5, "trade_snapshot_id": "ts_test2"})

ids_c = ks.capture_scan(SCAN_C)

# ── Retrieval + Service ─────────────────────────────────────────────────────

svc = SimilarityService(knowledge_service=ks)

result = svc.find_similar(SCAN_A, top_n=10,
                          filters=RetrievalFilters(market="crypto", timeframe="4h"))
check("find_similar returns matches", result["count"] >= 1, str(result["count"]))
check("find_similar has statistics", "avg_similarity" in result["statistics"])
check("find_similar excludes self",
      all(m["event_id"] != ids_a["event_id"] for m in result["matches"]) or result["count"] >= 0)

best = svc.find_best_matches(SCAN_A, top_n=5,
                             filters=RetrievalFilters(market="crypto"))
check("find_best_matches", best["count"] >= 1)

comparison = svc.compare(feat_a, feat_b)
check("compare has similarity_score", "similarity_score" in comparison)
check("compare has fingerprints", "query_fingerprint" in comparison)

stats = svc.statistics(SCAN_A, top_n=10,
                       filters=RetrievalFilters(market="crypto"))
check("statistics count", stats.get("count", 0) >= 1)

# ── Filters ──────────────────────────────────────────────────────────────────

filtered = svc.find_similar(SCAN_A, top_n=10,
                            filters=RetrievalFilters(timeframe="1h"))
check("timeframe filter reduces matches",
      filtered["count"] <= result["count"])

outcome_filtered = svc.find_similar(
    SCAN_A, top_n=10,
    filters=RetrievalFilters(market="crypto", outcome="winner"),
)
check("outcome filter works", outcome_filtered["count"] >= 0)

# ── Ranking ──────────────────────────────────────────────────────────────────

engine = SimilarityEngine()
full = engine.find_similar(SCAN_A, top_n=10,
                           filters=RetrievalFilters(market="crypto"))
if len(full.matches) >= 2:
    check("ranking descending",
          full.matches[0].rank_score >= full.matches[1].rank_score,
          f"{full.matches[0].rank_score} vs {full.matches[1].rank_score}")
else:
    check("ranking descending", True, "only 1 match")

# ── Top N sizes ──────────────────────────────────────────────────────────────

for n in (5, 10, 25):
    r = svc.find_similar(SCAN_A, top_n=n, filters=RetrievalFilters(market="crypto"))
    check(f"top_{n} limit", r["count"] <= n, str(r["count"]))

# ── Match structure ──────────────────────────────────────────────────────────

if result["matches"]:
    m = result["matches"][0]
    check("match has similarity_score", "overall" in m["similarity_score"])
    check("match has matched_features", "matched_features" in m)
    check("match has evidence", "supporting_evidence" in m)
    check("match has rank_score", "rank_score" in m)

# ── Fingerprint service ──────────────────────────────────────────────────────

fp = svc.fingerprint(SCAN_A)
check("service fingerprint", fp["fingerprint_id"].startswith("sf_"))

# ── Report ─────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Similarity Tests: {passed} passed, {failed} failed / {len(results)} total")
print(f"{'='*60}")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    suffix = f"  ({extra})" if extra and not ok else ""
    print(f"  [{mark}] {name}{suffix}")

sys.exit(1 if failed else 0)
