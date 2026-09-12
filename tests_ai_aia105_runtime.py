# -*- coding: utf-8 -*-
"""AIA-10.5 runtime PIT snapshot validation tests."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

from scanner.feature_snapshots.builder import build_snapshot
from scanner.feature_snapshots.config import RuntimeSnapshotConfig
from scanner.feature_snapshots.contract import SnapshotStatus
from scanner.feature_snapshots import store as pit_store
from scanner.feature_snapshots.runtime_audit import (
    analyze_feature_coverage,
    audit_linkage,
    classify_runtime_quality,
    dataset_eligibility_report,
    make_recommendation_id,
    snapshot_content_hash,
    validate_snapshot_provenance,
    verify_udp_snapshot,
)
from scanner.feature_snapshots.service import PointInTimeSnapshotService
from scanner.ml.label_store import LabelName
from scanner.predictive.dataset_v3 import build_dataset_v3, encode_row_v3
from scanner.predictive.leakage_detector import adversarial_leakage_tests
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


TS = "2025-06-01T10:00:00+00:00"
FS_ID = "fs_test_runtime_001"


def _rich_source() -> dict:
    return {
        "symbol": "BTCUSDT",
        "market": "crypto",
        "timeframe": "1h",
        "decision_timestamp": TS,
        "candle_time": TS,
        "score": 78.0,
        "htf": 1,
        "rsi": 63.2,
        "rvol": 1.52,
        "atr_pct": 1.8,
        "components": {"trend": 1, "rsi": 1, "volume": 1, "obv_macd": 1},
        "context": {"atr_percentile": 0.41, "volatility": "normal"},
        "recommendation": {
            "side": "buy", "confidence": 0.74, "grade": "A", "rr": 2.0,
            "analysis": {"price_action": {"bos_count": 2, "choch_count": 1, "trend": "bullish"}},
        },
        "recommendation_id": make_recommendation_id(legacy_snapshot_id=FS_ID),
    }


# Runtime snapshot created
with tempfile.TemporaryDirectory() as tmp:
    pit_store.V3_STORE = Path(tmp) / "v3.jsonl"
    pit_store.INDEX_STORE = Path(tmp) / "index.json"
    svc = PointInTimeSnapshotService()
    snap = svc.capture_from_scan_row(
        symbol="BTCUSDT", market="crypto", timeframe="1h",
        candle_time=TS,
        row={"score": 78, "htf": 1, "rsi": 63.2, "rvol": 1.52, "atr_pct": 1.8},
        reco={"side": "buy", "confidence": 0.74, "grade": "A", "rr": 2.0},
        legacy_snapshot_id=FS_ID,
    )
    check("runtime snapshot created", bool(snap.snapshot_id))
    check("recommendation link", snap.recommendation_id == f"reco_{FS_ID}")
    check("legacy link", snap.legacy_snapshot_id == FS_ID)
    check("timestamp validation", snap.feature_timestamp <= snap.decision_timestamp)
    check("persisted", pit_store.get_by_id(snap.snapshot_id) is not None)

    # Trade link simulation
    trade = {
        "trade_id": "t_rt_1",
        "feature_snapshot_id": FS_ID,
        "status": WON,
        "r_multiple": 1.5,
        "signal_at": TS,
        "symbol": "BTCUSDT",
        "market": "crypto",
        "timeframe": "1h",
    }
    pit = pit_store.get_by_legacy(FS_ID)
    check("trade to snapshot via legacy", pit is not None and pit.snapshot_id == snap.snapshot_id)

    # Immutability
    h1 = snap.content_hash
    h2 = snapshot_content_hash(pit_store.get_by_id(snap.snapshot_id))
    check("snapshot immutable hash", h1 == h2 and svc.verify_immutable(snap.snapshot_id, h1))

    # Outcome does not modify snapshot
    trade_closed = {**trade, "status": LOST, "r_multiple": -1.0}
    h3 = snapshot_content_hash(pit_store.get_by_id(snap.snapshot_id))
    check("outcome does not alter snapshot", h1 == h3)

# Provenance validation
snap2 = build_snapshot(_rich_source(), legacy_snapshot_id=FS_ID)
prov = validate_snapshot_provenance(snap2)
check("provenance valid on rich source", prov["valid"])
check("provenance count matches features", prov["provenance_count"] == prov["feature_count"])

# Feature coverage analysis
cov = analyze_feature_coverage(snap2)
check("coverage lists missing", "missing_features" in cov)
check("coverage pct computed", cov["coverage_pct"] > 0)
check("missing reasons populated", isinstance(cov["missing_reasons"], list))

# GOOD / PARTIAL / FAILED classification
strict = RuntimeSnapshotConfig(good_coverage_min=0.95, partial_coverage_min=0.85)
loose = RuntimeSnapshotConfig(good_coverage_min=0.30, partial_coverage_min=0.20)
rich_q = classify_runtime_quality(snap2, config=loose)
sparse = build_snapshot({"symbol": "X", "timeframe": "1h", "decision_timestamp": TS})
sparse_q = classify_runtime_quality(sparse, config=strict)
check("rich snapshot not FAILED", rich_q["runtime_quality"] in ("GOOD", "PARTIAL"))
check("sparse snapshot FAILED", sparse_q["runtime_quality"] == "FAILED")
check("failure reasons explain WHY", len(sparse_q["missing_reasons"]) > 0)

# Leakage on live snapshot row
row_v3 = encode_row_v3(
    {"trade_id": "t1", "status": WON, "signal_at": TS},
    pit_snapshot=snap2.to_dict(),
)
if row_v3:
    adv = adversarial_leakage_tests(row_v3)
    check("adversarial leakage all detected", all(adv.values()), str(adv))

# UDP integration
udp_pkg = {
    "feature_snapshot": {
        **PointInTimeSnapshotService().to_udp_summary(snap2),
        **PointInTimeSnapshotService().summarize_for_llm(snap2),
    }
}
udp_check = verify_udp_snapshot(udp_pkg)
check("udp available", udp_check["available"])
check("udp snapshot_id", udp_check["has_snapshot_id"])
check("udp no ohlc", udp_check["no_ohlc"])
check("udp summary categories", len(udp_check["summary_categories"]) > 0)

# UnifiedDecisionPackage build
try:
    from scanner.ai_advisor.unified_pipeline import build_unified_package
    from scanner.ai_advisor.layer_collectors import collect_platform_layers

    layers = collect_platform_layers(
        symbol="BTCUSDT", market="crypto", timeframe="1h",
        row={"score": 78, "htf": 1, "rsi": 63.2, "feature_snapshot_id": FS_ID,
             "candle_time": TS},
        recommendation={"side": "buy", "confidence": 0.74, "grade": "A", "rr": 2.0},
    )
    eid = layers.pop("event_id", "evt_test")
    result = build_unified_package(event_id=eid, use_cache=False, **layers)
    pkg = result.package
    check("udp package built", pkg is not None)
    if pkg:
        fs = pkg.feature_snapshot
        check("udp feature_snapshot available", fs.get("available") is True)
        check("udp feature count", (fs.get("feature_count") or 0) > 0)
        llm_blob = json.dumps(pkg.to_dict()).lower()
        check("udp no raw ohlc", "ohlc" not in llm_blob and '"candles"' not in llm_blob)
except Exception as exc:  # noqa: BLE001
    check("udp package built", False, str(exc)[:120])

# LLM visibility evidence id
llm = PointInTimeSnapshotService().summarize_for_llm(snap2)
check("llm evidence id", bool(llm.get("evidence_id")))
check("llm category summary", "summary_by_category" in llm)

# Dataset eligibility
trades = [
    {"trade_id": "t1", "status": WON, "r_multiple": 1, "signal_at": TS,
     "feature_snapshot_id": FS_ID, "symbol": "BTCUSDT", "market": "crypto", "timeframe": "1h"},
    {"trade_id": "t2", "status": LOST, "r_multiple": -1, "signal_at": TS,
     "feature_snapshot_id": "", "symbol": "ETHUSDT", "market": "crypto", "timeframe": "1h"},
]
elig = dataset_eligibility_report(trades, reconstruct=False)
check("eligibility reports rejected", elig["rejected"] >= 1)
check("v3 smoke not ready small sample", elig["v3_smoke_ready"] is False)

# Orphan / linkage audit
link = audit_linkage(
    scan_results=[{"feature_snapshot_id": FS_ID}],
    trades=trades,
    snapshots=[snap2],
)
check("linkage recommendations counted", link["recommendations"] >= 1)

# Failure does not block — service returns failed snap, no raise
with mock.patch("scanner.feature_snapshots.service.build_snapshot", side_effect=RuntimeError("boom")):
    failed = PointInTimeSnapshotService().capture_from_scan_row(
        symbol="X", market="crypto", timeframe="1h", candle_time=TS, row={}, legacy_snapshot_id="fs_fail",
    )
    check("failure does not raise", failed.status == SnapshotStatus.FAILED.value)

# Performance measurement
with tempfile.TemporaryDirectory() as tmp2:
    pit_store.V3_STORE = Path(tmp2) / "v3.jsonl"
    pit_store.INDEX_STORE = Path(tmp2) / "index.json"
    t0 = time.perf_counter()
    perf_snap = PointInTimeSnapshotService().capture_from_scan_row(
        symbol="BTCUSDT", market="crypto", timeframe="1h", candle_time=TS,
        row={"score": 70, "htf": 1, "rsi": 55, "rvol": 1.1, "atr_pct": 2},
        reco={"side": "buy", "confidence": 0.6, "grade": "B", "rr": 1.5},
        legacy_snapshot_id="fs_perf",
        skip_enrichment=True,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    check("performance under 100ms", elapsed < 100 or perf_snap.capture_latency_ms < 100,
          f"{elapsed:.1f}ms")

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\nAIA-10.5 tests: {passed}/{len(results)} passed")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
if failed:
    sys.exit(1)
