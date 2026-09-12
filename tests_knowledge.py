# -*- coding: utf-8 -*-
"""Unit tests for scanner.knowledge — run: python tests_knowledge.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.knowledge import (
    ContextBuilder,
    KnowledgeRepository,
    KnowledgeService,
    SnapshotBuilder,
    SnapshotKind,
)
from scanner.knowledge.exceptions import SnapshotNotFoundError
from scanner.knowledge.snapshot_builder import (
    build_feature_snapshot,
    build_market_snapshot,
    build_outcome_snapshot,
    build_recommendation_snapshot,
    build_trade_snapshot,
    make_event_id,
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
        "trend": 1, "rsi": 1, "obv_macd": 1, "vwap": 1, "spike": 0,
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

TRADE_SOURCE = {
    "trade_id": 42,
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "side": "buy",
    "source": "auto",
    "status": "won",
    "entry": 65000,
    "stop": 64000,
    "target1": 67000,
    "rr": 2.0,
    "entry_price": 65000,
    "exit_price": 67000,
    "r_multiple": 2.0,
    "best_r": 2.3,
    "worst_r": -0.4,
    "bars_held": 5,
    "signal_at": CANDLE,
    "candle_time": CANDLE,
    "opened_at": datetime(2025, 6, 1, 16, 0, tzinfo=timezone.utc),
    "closed_at": datetime(2025, 6, 2, 8, 0, tzinfo=timezone.utc),
    "resolution_note": "لمس الهدف",
    "grade": "A",
    "confidence": 0.75,
    "factors": ["htf", "confluence"],
}


# ── Snapshot builders ──

market = build_market_snapshot(SCAN_SOURCE)
check("market snapshot symbol", market.symbol == "BTCUSDT")
check("market snapshot atr_pct", market.atr_pct == 2.1)
check("market snapshot regime", market.regime == "صاعد")
check("market snapshot trend", market.trend_direction == "bullish")

features = build_feature_snapshot(SCAN_SOURCE)
check("feature snapshot grade", features.final_grade == "A")
check("feature groups trend", features.groups.trend.get("htf_bias") == 1)
check("feature liquidity sweeps", len(features.groups.liquidity.get("sweeps", [])) == 1)
check("feature elliott", features.groups.elliott.get("direction") == "up")

reco = build_recommendation_snapshot(SCAN_SOURCE)
check("reco action", reco.action == "now")
check("reco targets", reco.targets == [67000, 69000])
check("reco analysis summary", reco.analysis_summary.get("has_elliott") is True)

trade = build_trade_snapshot(TRADE_SOURCE)
check("trade lifecycle closed", trade.lifecycle == "closed")
check("trade current_r", trade.current_r == 2.0)
check("trade duration", trade.duration_seconds is not None and trade.duration_seconds > 0)

outcome = build_outcome_snapshot(TRADE_SOURCE)
check("outcome winner", outcome.outcome_class == "winner")
check("outcome mfe", outcome.mfe_r == 2.3)
check("outcome mae", outcome.mae_r == -0.4)

eid = make_event_id(symbol="BTCUSDT", market="crypto", timeframe="4h",
                    candle_time=CANDLE)
check("event id stable prefix", eid.startswith("ke_"))
check("event id deterministic",
      eid == make_event_id(symbol="BTCUSDT", market="crypto", timeframe="4h",
                           candle_time=CANDLE))

# ── Sprint AI-01.5 hardening ──

from scanner.knowledge import (
    KNOWLEDGE_SCHEMA_VERSION,
    KnowledgeGraph,
    KnowledgeMemory,
    MarketEnvironment,
    market_fingerprint,
    upgrade_snapshot,
)
from scanner.knowledge.feature_metadata import FeatureValue
from scanner.knowledge.snapshot_builder import build_market_environment

check("schema version", market.schema.schema_version == KNOWLEDGE_SCHEMA_VERSION)
check("market fingerprint", market.fingerprint.startswith("mf_"))
check("fingerprint stable", market.fingerprint == market_fingerprint(market.to_dict()))
check("feature registry rsi metadata",
      (fv := features.get_feature("rsi")) is not None and fv.calculation_module != "")
check("feature to_vector", len(features.to_vector()) > 0)
check("feature to_dataframe columns",
      "columns" in features.to_dataframe() and "rows" in features.to_dataframe())
check("quality report attached", market.quality.completeness_score > 0)
check("audit trail attached", market.audit.pipeline_stage == "market_capture")

env = build_market_environment(SCAN_SOURCE)
check("market environment regime", env.market_regime == "صاعد")
check("market environment breadth", env.market_breadth == 62.0)

legacy = upgrade_snapshot({"snapshot_id": "ms_x", "symbol": "BTC", "market": "crypto",
                           "timeframe": "4h", "timestamp": CANDLE.isoformat(),
                           "event_id": "ke_test"})
check("legacy upgrade schema", legacy.get("schema", {}).get("schema_version") == KNOWLEDGE_SCHEMA_VERSION)

mem = KnowledgeMemory(event_id=eid)
check("memory empty slots", len(mem.empty_slots()) == 4)

# ── Round-trip serialization ──

from scanner.knowledge.market_snapshot import MarketSnapshot
from scanner.knowledge.feature_snapshot import FeatureSnapshot
from scanner.knowledge.recommendation_snapshot import RecommendationSnapshot
from scanner.knowledge.trade_snapshot import TradeSnapshot
from scanner.knowledge.outcome_snapshot import OutcomeSnapshot

check("market round-trip",
      MarketSnapshot.from_dict(market.to_dict()).symbol == "BTCUSDT")
check("feature round-trip",
      FeatureSnapshot.from_dict(features.to_dict()).final_grade == "A")
check("reco round-trip",
      RecommendationSnapshot.from_dict(reco.to_dict()).action == "now")
check("trade round-trip",
      TradeSnapshot.from_dict(trade.to_dict()).status == "won")
check("outcome round-trip",
      OutcomeSnapshot.from_dict(outcome.to_dict()).profit is True)

# ── Repository ──

with tempfile.TemporaryDirectory() as tmp:
    store = Path(tmp) / "knowledge.jsonl"
    repo = KnowledgeRepository(store)

    rec_id = repo.save_snapshot(
        kind=SnapshotKind.MARKET,
        event_id=eid,
        payload=market.to_dict(),
    )
    check("repository save", bool(rec_id))

    loaded = repo.load(rec_id)
    check("repository load", loaded.event_id == eid)

    found = repo.search(symbol="BTCUSDT", kind=SnapshotKind.MARKET)
    check("repository search", len(found) == 1)

    hist = repo.history(eid)
    check("repository history", len(hist) == 1)

    stats = repo.statistics(market="crypto")
    check("repository statistics", stats["total_records"] == 1)

    # ── Service + context ──

    svc = KnowledgeService(repository=repo)
    ids = svc.capture_scan({**SCAN_SOURCE, "event_id": eid})
    check("service capture scan", "feature_snapshot_id" in ids)

    svc.capture_trade({**TRADE_SOURCE, "event_id": eid,
                       "feature_snapshot_id": ids.get("feature_snapshot_id")})
    svc.capture_outcome({**TRADE_SOURCE, "event_id": eid})

    ctx = svc.get_context(eid)
    check("context has market", ctx["market_snapshot"] is not None)
    check("context has environment", ctx["market_environment"] is not None)
    check("context has graph", ctx["knowledge_graph"] is not None)
    check("context has memory scaffold", ctx["knowledge_memory"] is not None)
    check("context has outcome", ctx["outcome_snapshot"] is not None)
    check("context timeline", len(ctx["timeline"]) >= 3)

    graph = svc.get_graph(eid)
    check("graph nodes", len(graph.nodes) >= 3)
    check("graph edges", len(graph.edges) >= 2)

    strat = svc.strategy_stats_from_rows([
        {"status": "won", "r_multiple": 2.0},
        {"status": "lost", "r_multiple": -1.0},
        {"status": "won", "r_multiple": 1.5},
    ])
    check("strategy stats expectancy", strat.expectancy is not None)

    ctx2 = svc.get_context(
        eid,
        strategy_stats=strat,
        recent_performance={"rolling_30": 0.5},
    )
    check("context strategy stats",
          ctx2["strategy_statistics"]["closed_trades"] == 3)

    try:
        svc.get_context("ke_nonexistent")
        check("missing context raises", False)
    except SnapshotNotFoundError:
        check("missing context raises", True)

# ── Interfaces ──

builder = SnapshotBuilder()
check("SnapshotProvider market",
      isinstance(builder.build_market(SCAN_SOURCE), dict))
check("SnapshotProvider features",
      isinstance(builder.build_features(SCAN_SOURCE), dict))

ctx_builder = ContextBuilder(repo)
check("ContextProvider protocol", hasattr(ctx_builder, "build_context"))

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
