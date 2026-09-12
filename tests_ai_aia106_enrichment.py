# -*- coding: utf-8 -*-
"""AIA-10.6 runtime feature enrichment tests."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scanner.feature_snapshots.builder import V3_FEATURE_SPECS, build_snapshot, extract_v3_features
from scanner.feature_snapshots.enrichment import (
    build_source_from_score_result,
    enrich_snapshot_source,
    evidence_ids_for_snapshot,
    missing_by_category,
    normalize_structure,
)
from scanner.feature_snapshots import store as pit_store
from scanner.feature_snapshots.runtime_audit import (
    analyze_feature_coverage,
    classify_runtime_quality,
    validate_snapshot_provenance,
    verify_udp_snapshot,
)
from scanner.feature_snapshots.service import PointInTimeSnapshotService
from scanner.predictive.leakage_detector import validate_provenance
from scanner.scoring.engine import ScoreResult

results: list[tuple[bool, str, str]] = []

TS = "2025-06-01T10:00:00+00:00"
FUTURE_TS = "2025-06-02T10:00:00+00:00"


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _mock_knowledge() -> dict:
    return {
        "event_id": "evt_test",
        "feature_snapshot": {
            "final_score": 72,
            "groups": {"patterns": {"p1": {}, "p2": {}}},
            "confidence": 0.71,
        },
        "market_environment": {"regime": "trending"},
        "knowledge_confidence": 0.71,
    }


def _mock_similarity() -> dict:
    return {
        "match_count": 12,
        "average_similarity": 0.84,
        "average_win_rate": 0.61,
        "average_r": 1.2,
        "similarity_result": {"statistics": {"sample_size": 12}},
        "available": True,
    }


def _rich_reco() -> dict:
    return {
        "side": "buy",
        "confidence": 0.74,
        "grade": "A",
        "rr": 2.0,
        "analysis": {
            "price_action": {
                "trend": "bullish",
                "events": [
                    {"kind": "BOS"},
                    {"kind": "BOS"},
                    {"kind": "CHoCH"},
                ],
                "zones": [
                    {"kind": "demand", "top": 99.0},
                    {"kind": "supply", "bottom": 105.0},
                ],
            },
        },
    }


def _score_result() -> ScoreResult:
    return ScoreResult(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=pd.Timestamp(TS),
        close=100.0,
        score=76.0,
        decision="buy",
        components={"trend": 1, "rsi": 1, "volume": 1, "obv_macd": 1, "div": 1},
        context={
            "rsi": 63.2,
            "rvol": 1.52,
            "atr_pct": 1.8,
            "atr_percentile": 0.41,
            "channel": "rising",
            "ch_zone": "buy",
        },
        confluence=["trend", "volume"],
        htf=1,
        recommendation=_rich_reco(),
    )


# 1 scoring components captured
src = build_source_from_score_result(_score_result(), market="crypto")
check("scoring components captured", src["components"].get("trend") == 1)
check("factor flags populated", len(src.get("factor_flags", [])) >= 3)

# 2 trend
feats, prov = extract_v3_features(src, decision_ts=TS)
check("trend direction captured", "trend_direction" in feats)
check("htf trend captured", "higher_timeframe_trend" in feats)

# 3 momentum
check("rsi captured", feats.get("rsi") == 63.2)
check("divergence captured", feats.get("divergence") == 1.0)

# 4 volatility
check("atr captured", feats.get("atr_pct") == 1.8)
check("atr percentile captured", feats.get("atr_percentile") == 0.41)
check("volatility regime captured", "volatility_regime" in feats)

# 5 volume
check("rvol captured", feats.get("rvol") == 1.52)
check("volume participation captured", "volume_participation" in feats)

# 6 structure
struct = normalize_structure(_rich_reco()["analysis"], close=100.0)
check("structure bos count", struct.get("bos_count") == 2)
check("structure choch count", struct.get("choch_count") == 1)
src["structure"] = struct
feats2, _ = extract_v3_features(src, decision_ts=TS)
check("structure direction captured", feats2.get("structure_direction") == 1.0)
check("support distance captured", feats2.get("support_distance") == 1.0)

# 7-9 enrichment collectors (mocked)
base = {
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "1h",
    "decision_timestamp": TS,
    "candle_time": TS,
    "score": 76,
    "htf": 1,
    "components": {"trend": 1, "rsi": 1, "volume": 1},
    "context": {"rsi": 63.2, "rvol": 1.52, "atr_pct": 1.8},
    "recommendation": _rich_reco(),
}
with mock.patch("scanner.feature_snapshots.enrichment._collect_knowledge", return_value=(_mock_knowledge(), "")):
    with mock.patch("scanner.feature_snapshots.enrichment._collect_similarity",
                     return_value=({
                         "match_count": 12,
                         "average_similarity": 0.84,
                         "average_win_rate": 0.61,
                         "average_r": 1.2,
                         "similarity_dataset_timestamp": TS,
                         "similarity_status": "available",
                     }, "")):
        with mock.patch("scanner.feature_snapshots.enrichment.collect_validated_research",
                         return_value=({
                             "available": True,
                             "research_id": "rex_test",
                             "validation_status": "VALIDATED",
                             "created_at": TS,
                             "statistics": {"significant": True, "confidence": 0.8, "sample_size": 50},
                         }, "")):
            enriched, meta = enrich_snapshot_source(base, score_result=_score_result(), market="crypto")

check("similarity captured", enriched.get("enriched_similarity", {}).get("match_count") == 12)
check("knowledge captured", "knowledge_context" in enriched)
check("research captured", enriched.get("enriched_research", {}).get("available") is True)
check("coverage improves or stable", meta["coverage_after"] >= meta["coverage_before"],
      f"{meta['coverage_before']} -> {meta['coverage_after']}")

# 10 provenance
snap = build_snapshot(
    enriched,
    similarity=enriched["enriched_similarity"],
    research=enriched["enriched_research"],
    knowledge=enriched["knowledge_context"],
)
prov_audit = validate_snapshot_provenance(snap)
check("provenance complete", prov_audit["valid"])

# 11 timestamp ordering
check("source timestamps ordered", all(
    p.source_timestamp <= TS for p in snap.provenance
))

# 12 future timestamp rejection
bad_prov = [{
    "name": "rsi",
    "value": 50.0,
    "source": "scanner.indicators.pine",
    "source_timestamp": FUTURE_TS,
    "calculation_version": "rsi-v2",
}]
violations = validate_provenance(bad_prov, decision_ts=TS)
check("future timestamp rejection", any("LEAKAGE" in v.upper() or "future" in v.lower() or ">" in v
                                        for v in violations), str(violations))

# 13 missing feature reporting
cov = analyze_feature_coverage(snap)
check("missing features list", isinstance(cov["missing_features"], list))
check("missing by category", isinstance(cov.get("missing_by_category"), dict))

# 14 category coverage
mbc = missing_by_category(cov["missing_features"])
check("category keys present", "trend" in mbc and "platform" in mbc)

# 15 UDP preservation
with tempfile.TemporaryDirectory() as tmp:
    pit_store.V3_STORE = Path(tmp) / "v3.jsonl"
    pit_store.INDEX_STORE = Path(tmp) / "index.json"
    svc = PointInTimeSnapshotService()
    with mock.patch("scanner.feature_snapshots.enrichment._collect_knowledge", return_value=(_mock_knowledge(), "")):
        with mock.patch("scanner.feature_snapshots.enrichment._collect_similarity", return_value=(_mock_similarity(), "")):
            with mock.patch("scanner.feature_snapshots.enrichment.collect_validated_research", return_value=({}, "missing_research")):
                captured = svc.capture_from_scan_row(
                    symbol="BTCUSDT", market="crypto", timeframe="1h", candle_time=TS,
                    row={
                        "score": 76, "htf": 1, "close": 100,
                        "rsi": 63.2, "rvol": 1.52, "atr_pct": 1.8,
                        "c_trend": 1, "c_rsi": 1, "c_volume": 1,
                    },
                    reco=_rich_reco(),
                    legacy_snapshot_id="fs_aia106",
                    score_result=_score_result(),
                )
    udp = {
        "feature_snapshot": {
            **svc.to_udp_summary(captured),
            **svc.summarize_for_llm(captured),
        },
    }
    from scanner.ai_advisor.unified_package import UnifiedDecisionPackage
    from scanner.ai_advisor.package_compression import compress_package
    from scanner.ai_advisor.token_optimizer import DEFAULT_TOKEN_BUDGET, optimize_tokens
    pkg = UnifiedDecisionPackage(
        package_id="pkg_test",
        event_id="evt_test",
        feature_snapshot=udp["feature_snapshot"],
    )
    compressed, _ = compress_package(pkg)
    check("compression preserves feature_snapshot",
          (compressed.feature_snapshot or {}).get("available") is True)
    optimized, _ = optimize_tokens(compressed, budget=DEFAULT_TOKEN_BUDGET)
    fs_out = optimized.feature_snapshot or {}
    check("token optimize preserves feature_snapshot", fs_out.get("available") is True)
    udp_check = verify_udp_snapshot({"feature_snapshot": fs_out})
    check("udp no ohlc", udp_check["no_ohlc"])

# 16 LLM-safe summary
llm = svc.summarize_for_llm(captured)
check("llm category summary", "summary_by_category" in llm)
check("llm has trend", llm["summary_by_category"].get("trend", {}).get("direction") is not None)
blob = json.dumps(llm).lower()
check("llm no raw ohlc", "ohlc" not in blob and '"candles"' not in blob)

# 17 evidence IDs
check("evidence ids per category", len(llm.get("evidence_ids", {})) >= 3)
check("evidence id root", bool(llm.get("evidence_id")))

# 18 historical safety — research after decision excluded
with mock.patch("scanner.research.experiment.ExperimentStore.history") as hist:
    from scanner.research.experiment import Experiment, ExperimentStatus
    hist.return_value = [
        Experiment(
            experiment_id="rex_future",
            title="future",
            status=ExperimentStatus.COMPLETED.value,
            ended_at=FUTURE_TS,
            hypothesis={"validation_status": "VALIDATED"},
            results={"report": {"metrics": {"significant": True, "sample_size": 10}}},
        ),
    ]
    res, err = __import__(
        "scanner.feature_snapshots.enrichment", fromlist=["collect_validated_research"]
    ).collect_validated_research(TS)
    check("future research excluded", not res.get("available"), err)

# 19 failure isolation
with mock.patch("scanner.feature_snapshots.enrichment._collect_similarity",
                side_effect=RuntimeError("sim down")):
    _, fail_meta = enrich_snapshot_source(base, market="crypto")
check("failure isolation similarity", any("similarity" in f for f in fail_meta.get("collector_failures", [])))

with tempfile.TemporaryDirectory() as tmp2:
    pit_store.V3_STORE = Path(tmp2) / "v3.jsonl"
    pit_store.INDEX_STORE = Path(tmp2) / "index.json"
    with mock.patch("scanner.feature_snapshots.service.build_snapshot", side_effect=RuntimeError("boom")):
        failed = PointInTimeSnapshotService().capture_from_scan_row(
            symbol="X", market="crypto", timeframe="1h", candle_time=TS, row={},
            legacy_snapshot_id="fs_fail2",
            skip_enrichment=True,
        )
    check("snapshot failure non-blocking", failed.snapshot_id == "" or failed.status)

# 20 performance (enrichment mocked)
with tempfile.TemporaryDirectory() as tmp3:
    pit_store.V3_STORE = Path(tmp3) / "v3.jsonl"
    pit_store.INDEX_STORE = Path(tmp3) / "index.json"
    t0 = time.perf_counter()
    with mock.patch("scanner.feature_snapshots.enrichment._collect_knowledge", return_value=(_mock_knowledge(), "")):
        with mock.patch("scanner.feature_snapshots.enrichment._collect_similarity", return_value=(_mock_similarity(), "")):
            with mock.patch("scanner.feature_snapshots.enrichment.collect_validated_research", return_value=({}, "")):
                perf = PointInTimeSnapshotService().capture_from_scan_row(
                    symbol="BTCUSDT", market="crypto", timeframe="1h", candle_time=TS,
                    row={"score": 70, "htf": 1, "rsi": 55, "rvol": 1.1, "atr_pct": 2, "close": 100},
                    reco={"side": "buy", "confidence": 0.6, "grade": "B", "rr": 1.5},
                    legacy_snapshot_id="fs_perf106",
                    score_result=_score_result(),
                )
    elapsed = (time.perf_counter() - t0) * 1000
    check("performance under 100ms", elapsed < 100 or perf.capture_latency_ms < 100, f"{elapsed:.1f}ms")

# Coverage target on enriched rich snapshot
quality = classify_runtime_quality(snap)
check("enriched coverage >= 70%", quality["coverage"] >= 0.70,
      f"{quality['coverage_pct']}%")
check("runtime quality not FAILED on rich", quality["runtime_quality"] in ("GOOD", "PARTIAL"))

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\nAIA-10.6 tests: {passed}/{len(results)} passed")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
if failed:
    sys.exit(1)
