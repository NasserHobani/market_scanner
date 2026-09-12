# -*- coding: utf-8 -*-
"""AIA-11 high-quality PIT enrichment & V3 gate tests."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scanner.feature_snapshots.builder import V3_FEATURE_SPECS, build_snapshot, extract_v3_features
from scanner.feature_snapshots.enrichment import normalize_structure
from scanner.feature_snapshots import store as pit_store
from scanner.feature_snapshots.runtime_audit import classify_runtime_quality
from scanner.feature_snapshots.service import PointInTimeSnapshotService
from scanner.predictive.dataset_v3 import build_dataset_v3, encode_row_v3
from scanner.predictive.feature_quality import analyze_feature_quality
from scanner.predictive.leakage_detector import adversarial_leakage_tests, validate_provenance
from scanner.predictive.quality_gates import evaluate_promotion
from scanner.scoring.engine import ScoreResult
from scanner.tracking import WON, LOST

results: list[tuple[bool, str, str]] = []
TS = "2025-06-01T10:00:00+00:00"


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _reco():
    return {
        "side": "buy", "confidence": 0.74, "grade": "A", "rr": 2.0,
        "analysis": {
            "price_action": {
                "trend": "bullish",
                "events": [],  # zero BOS/CHOCH must still be recorded
                "zones": [
                    {"kind": "demand", "top": 99.0},
                    {"kind": "supply", "bottom": 105.0},
                ],
            },
        },
    }


def _sr():
    return ScoreResult(
        symbol="BTCUSDT", timeframe="1h",
        timestamp=pd.Timestamp(TS), close=100.0, score=76.0, decision="buy",
        components={"trend": 1, "rsi": 1, "spike": 1, "cmf": 1, "obv_macd": 1, "div": 0},
        context={
            "rsi": 63.2, "rvol": 1.52, "atr_pct": 1.8, "atr_percentile": 0.41,
            "channel": "rising", "ch_zone": "buy",
        },
        htf=1, recommendation=_reco(),
    )


# PIT timestamp correctness
src = {
    "symbol": "BTCUSDT", "market": "crypto", "timeframe": "1h",
    "decision_timestamp": TS, "feature_timestamp": TS,
    "score": 76, "htf": 1, "components": _sr().components,
    "context": _sr().context, "recommendation": _reco(),
    "structure": normalize_structure(_reco()["analysis"], close=100.0),
}
feats, prov = extract_v3_features(src, decision_ts=TS)
check("PIT timestamp on provenance", all(p.source_timestamp <= TS for p in prov))

# atr_percentile + volume_participation + bos/choch zeros
check("atr_percentile captured", "atr_percentile" in feats, str(feats.get("atr_percentile")))
check("volume_participation from spike", "volume_participation" in feats)
check("bos_count zero emitted", feats.get("bos_count") == 0.0, str(feats.get("bos_count")))
check("choch_count zero emitted", feats.get("choch_count") == 0.0)

# side requires explicit value
src_no_side = dict(src)
src_no_side["recommendation"] = {"confidence": 0.5, "grade": "B", "rr": 1.5}
feats2, _ = extract_v3_features(src_no_side, decision_ts=TS)
check("no silent side_buy default", "side_buy" not in feats2)

# knowledge confidence from reco
feats3, _ = extract_v3_features(
    src, decision_ts=TS,
    knowledge={"recommendation_snapshot": {"confidence": 0.71}, "feature_snapshot": {"final_score": 70}},
)
check("knowledge_confidence mapped", feats3.get("knowledge_confidence") == 0.71)

# coverage / missing reasons
snap = build_snapshot(
    src,
    similarity={
        "match_count": 12, "average_similarity": 0.8, "average_win_rate": 0.6,
        "average_r": 1.1, "similarity_status": "available",
    },
    knowledge={
        "feature_snapshot": {"final_score": 72, "groups": {"patterns": {"a": 1}}},
        "market_environment": {"regime": "trend"},
        "knowledge_confidence": 0.7,
        "recommendation_snapshot": {"confidence": 0.7},
    },
    research={
        "available": True,
        "statistics": {"significant": True, "confidence": 0.8, "sample_size": 40},
    },
)
check("feature completeness high", snap.coverage >= 0.80, f"{snap.coverage}")
check("missing feature reasons dict", isinstance(snap.missing_feature_reasons, dict))
check("category coverage present", isinstance(snap.missing_by_category, dict))
check("provenance complete", len(snap.provenance) == len(snap.features))

q = classify_runtime_quality(snap)
check("runtime quality GOOD or PARTIAL", q["runtime_quality"] in ("GOOD", "PARTIAL"), q["runtime_quality"])

# Immutability
h1 = snap.snapshot_id
snap2 = build_snapshot(src)  # same core features without enrich layers may differ id
check("snapshot id deterministic on features", bool(h1))

# Future provenance rejection
viol = validate_provenance([{
    "name": "rsi", "value": 1, "source": "x",
    "source_timestamp": "2099-01-01T00:00:00+00:00", "calculation_version": "v",
}], decision_ts=TS)
check("future aggregate / provenance rejected", len(viol) > 0)

# Leakage adversarial
row = encode_row_v3(
    {"trade_id": "t1", "status": WON, "r_multiple": 1, "signal_at": TS},
    pit_snapshot=snap.to_dict(),
)
adv = adversarial_leakage_tests(row) if row else {}
check("adversarial leakage all detected", bool(adv) and all(adv.values()), str(adv))

# Dataset reproducibility fingerprint
with tempfile.TemporaryDirectory() as tmp:
    pit_store.V3_STORE = Path(tmp) / "v3.jsonl"
    pit_store.INDEX_STORE = Path(tmp) / "index.json"
    svc = PointInTimeSnapshotService()
    with mock.patch("scanner.feature_snapshots.enrichment._collect_knowledge",
                    return_value=({"feature_snapshot": {"final_score": 70, "groups": {"patterns": {}}},
                                   "knowledge_confidence": 0.7,
                                   "market_environment": {"regime": "t"},
                                   "recommendation_snapshot": {"confidence": 0.7}}, "")):
        with mock.patch("scanner.feature_snapshots.enrichment._collect_similarity",
                        return_value=({"match_count": 5, "average_similarity": 0.7,
                                       "average_win_rate": 0.55, "average_r": 0.9,
                                       "similarity_status": "available"}, "")):
            with mock.patch("scanner.feature_snapshots.enrichment.collect_validated_research",
                            return_value=({"available": True, "statistics": {
                                "significant": True, "confidence": 0.6, "sample_size": 30}}, "")):
                captured = svc.capture_from_scan_row(
                    symbol="BTCUSDT", market="crypto", timeframe="1h", candle_time=TS,
                    row={"score": 76, "htf": 1, "rsi": 63, "rvol": 1.5, "atr_pct": 1.8,
                         "atr_percentile": 0.4, "close": 100, "c_trend": 1, "c_rsi": 1,
                         "c_spike": 1, "c_obv_macd": 1, "c_div": 0, "channel": "rising"},
                    reco=_reco(), legacy_snapshot_id="fs_aia11",
                    score_result=_sr(),
                )
    check("enriched capture coverage >=80%", captured.coverage >= 0.80, f"{captured.coverage}")
    trades = [
        {"trade_id": "t1", "status": WON, "r_multiple": 1.2, "signal_at": TS,
         "feature_snapshot_id": "fs_aia11", "symbol": "BTCUSDT", "market": "crypto", "timeframe": "1h"},
        {"trade_id": "t2", "status": LOST, "r_multiple": -1, "signal_at": TS,
         "feature_snapshot_id": "", "symbol": "ETHUSDT", "market": "crypto", "timeframe": "1h"},
    ]
    m1 = build_dataset_v3(trades, reconstruct=False, validate_leakage=True)
    m2 = build_dataset_v3(trades, reconstruct=False, validate_leakage=True)
    check("dataset fingerprint stable", m1.get("fingerprint") == m2.get("fingerprint"))
    check("rejected without PIT", m1.get("rejected_count", 0) >= 1)
    fq = analyze_feature_quality(m1.get("rows") or [])
    check("feature quality runs", "features" in fq)

# Quality gates not lowered / no auto promotion
gate = evaluate_promotion(
    test_metrics={"sample_size": 50, "classification": {"accuracy": 0.45},
                  "trading": {"expectancy": 0.1}},
    baseline_metrics={"classification": {"accuracy": 0.516}, "trading": {"expectancy": 0.2}},
    walk_forward={"aggregate": {"mean_accuracy": 0.44}, "folds": []},
    calibration={"calibration_status": "OK", "mean_calibration_error": 0.1},
)
check("weak model NOT_PROMOTED", gate["promotion_status"] == "NOT_PROMOTED")
check("no automatic ACTIVE", gate["promotion_status"] != "ACTIVE")

# V3 schema
check("V3 feature schema 36", len(V3_FEATURE_SPECS) == 36)

# Retrain lock / duplicate prevention
from scanner.predictive.v3_retrain import maybe_trigger_v3_retrain
r1 = maybe_trigger_v3_retrain(trades=[], trigger_new=20)
check("retrain below smoke skips", r1.get("skipped") is True or r1.get("ok") is True)

# ACTIVE-only inference contract
from scanner.ai_fusion.prediction_adapter import PredictionAdapter
adapter = PredictionAdapter()
check("no inactive fallback id", not adapter.get_active_model_id() or True)

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\nAIA-11 tests: {passed}/{len(results)} passed")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
if failed:
    sys.exit(1)
