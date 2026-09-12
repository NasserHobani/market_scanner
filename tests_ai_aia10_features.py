# -*- coding: utf-8 -*-
"""AIA-10 point-in-time feature snapshot tests."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.feature_snapshots.builder import build_snapshot, extract_v3_features
from scanner.feature_snapshots.contract import SnapshotStatus
from scanner.feature_snapshots.historical import legacy_to_source
from scanner.feature_snapshots.service import PointInTimeSnapshotService
from scanner.feature_snapshots import store as pit_store
from scanner.predictive.dataset_v3 import build_dataset_v3, encode_row_v3
from scanner.predictive.feature_registry import FEATURE_VERSION_V3, V3_COLUMNS
from scanner.predictive.leakage_detector import adversarial_leakage_tests, validate_provenance
from scanner.ml.label_store import LabelName
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _source(ts: str = "2025-06-01T10:00:00+00:00") -> dict:
    return {
        "symbol": "BTCUSDT",
        "market": "crypto",
        "timeframe": "1h",
        "decision_timestamp": ts,
        "candle_time": ts,
        "score": 72.0,
        "htf": 1,
        "rsi": 63.2,
        "rvol": 1.52,
        "atr_pct": 1.8,
        "recommendation": {
            "side": "buy", "confidence": 0.74, "grade": "A", "rr": 2.0,
        },
        "components": {"trend": 1, "rsi": 1, "volume": 1},
    }


TS = "2025-06-01T10:00:00+00:00"

# Snapshot creation
snap = build_snapshot(_source(TS), legacy_snapshot_id="fs_test123")
check("snapshot created", bool(snap.snapshot_id))
check("timestamp ordering", snap.feature_timestamp <= snap.decision_timestamp)
check("provenance present", len(snap.provenance) > 0)
check("features extracted", len(snap.features) > 0)
check("coverage computed", 0 < snap.coverage <= 1.0)

# Provenance fields
p0 = snap.provenance[0]
check("provenance has source", bool(p0.source))
check("provenance has calc version", bool(p0.calculation_version))

# Partial snapshot (sparse source)
sparse = build_snapshot({"symbol": "X", "timeframe": "1h", "decision_timestamp": TS})
check("partial or failed on sparse", sparse.status in (
    SnapshotStatus.PARTIAL.value, SnapshotStatus.FAILED.value, SnapshotStatus.REJECTED.value,
))

# Future timestamp rejected
bad_ts = build_snapshot({
    **_source(TS), "feature_timestamp": "2099-01-01T00:00:00+00:00",
})
check("future feature_timestamp rejected", bad_ts.status == SnapshotStatus.REJECTED.value)

# Persistence
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "v3.jsonl"
    pit_store.V3_STORE = path
    pit_store.INDEX_STORE = Path(tmp) / "index.json"
    svc = PointInTimeSnapshotService()
    saved = svc.capture_from_scan_row(
        symbol="ETHUSDT", market="crypto", timeframe="15m",
        candle_time=TS, row=_source(TS), legacy_snapshot_id="fs_persist",
    )
    check("snapshot persisted", path.exists() and saved.snapshot_id)
    loaded = svc.get(saved.snapshot_id)
    check("snapshot reload", loaded is not None and loaded.symbol == "ETHUSDT")

# Historical reconstruction source
legacy_row = {
    "snapshot_id": "fs_legacy1",
    "symbol": "BTCUSDT", "market": "crypto", "timeframe": "1h",
    "candle_time": TS, "score": 65, "htf": 1, "confluence": 2,
    "features": {"rsi": 55, "rvol": 1.1, "atr_pct": 2.0},
    "action": "buy", "grade": "B", "confidence": 0.6, "rr": 1.5,
}
src = legacy_to_source(legacy_row)
check("historical source mapping", src["rsi"] == 55)

trade_won = {
    "trade_id": "t1", "status": WON, "r_multiple": 2.0, "signal_at": TS,
    "symbol": "BTCUSDT", "market": "crypto", "timeframe": "1h",
    "feature_snapshot_id": "fs_legacy1",
}
pit_dict = snap.to_dict()
row_v3 = encode_row_v3(trade_won, pit_snapshot=pit_dict)
check("dataset row encodes", row_v3 is not None)
if row_v3:
    check("label separate from features", LabelName.BINARY_WIN.value not in row_v3["features"])
    check("no outcome in features", "r_multiple" not in row_v3["features"])

# Leakage adversarial
if row_v3:
    adv = adversarial_leakage_tests(row_v3)
    check("adversarial leakage detected", all(adv.values()), str(adv))

# Provenance validation
viols = validate_provenance([{
    "name": "rsi", "value": 1, "source": "x",
    "source_timestamp": "2099-01-01T00:00:00+00:00",
    "calculation_version": "v1",
}], decision_ts=TS)
check("future provenance caught", len(viols) > 0)

# Dataset V3 build (synthetic trades)
trades = []
for i in range(25):
    trades.append({
        "trade_id": f"t_{i}",
        "symbol": "BTCUSDT",
        "market": "crypto",
        "timeframe": "1h",
        "status": WON if i % 2 == 0 else LOST,
        "r_multiple": 1.0 if i % 2 == 0 else -1.0,
        "signal_at": datetime(2025, 1, 1 + i, tzinfo=timezone.utc).isoformat(),
        "feature_snapshot_id": "",
    })

manifest = build_dataset_v3(trades, reconstruct=False, validate_leakage=False)
check("dataset v3 builds", "dataset_id" in manifest)
check("v3 schema version", manifest["dataset_version"] == FEATURE_VERSION_V3)

# UDP integration
udp = svc.to_udp_summary(snap)
check("udp summary available", udp.get("available") is True)
check("udp has snapshot_id", bool(udp.get("snapshot_id")))
llm = svc.summarize_for_llm(snap)
check("llm summary no ohlc", "ohlc" not in json.dumps(llm).lower())

# Prediction adapter blocks inactive
from scanner.ai_fusion.prediction_adapter import PredictionAdapter
pred = PredictionAdapter().to_udp_section({})
check("inactive model blocks prediction", pred.get("status") == "UNAVAILABLE")

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\nAIA-10 tests: {passed}/{len(results)} passed")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
if failed:
    sys.exit(1)
