# -*- coding: utf-8 -*-
"""AIA-08 prediction improvement tests — run: python tests_prediction_improvement.py"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ml.label_store import LabelName
from scanner.predictive.baselines import run_all_baselines
from scanner.predictive.calibration import calibration_report
from scanner.predictive.dataset_quality import dataset_quality_report
from scanner.predictive.feature_audit import audit_features
from scanner.predictive.feature_engineering import add_point_in_time_history, encode_trade_row_v2
from scanner.predictive.feature_registry import V2_COLUMNS, FEATURE_VERSION_V2
from scanner.predictive.label_analysis import label_audit
from scanner.predictive.leakage_detector import LeakageError, inject_leakage_test_row, validate_dataset
from scanner.predictive.quality_gates import evaluate_promotion, naive_baseline_metrics
from scanner.predictive.trade_dataset import build_from_trade_dicts, chronological_split
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _trade(i: int, *, won: bool = True, score: float = 70.0,
           snap_id: str = "") -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 10, 0, tzinfo=timezone.utc)
    return {
        "trade_id": f"t_{i}",
        "symbol": ["BTCUSDT", "ETHUSDT", "SOLUSDT"][i % 3],
        "market": "crypto",
        "timeframe": ["1h", "15m", "4h"][i % 3],
        "side": "buy",
        "status": WON if won else LOST,
        "score": score,
        "confidence": 0.7,
        "rr": 2.0,
        "grade": "A",
        "factors": ["htf", "confluence"],
        "r_multiple": 2.0 if won else -1.0,
        "signal_at": ts.isoformat(),
        "feature_snapshot_id": snap_id,
    }


TRADES = [_trade(i, won=(i % 3 != 0)) for i in range(60)]

# V2 dataset
manifest = build_from_trade_dicts(TRADES, feature_version=FEATURE_VERSION_V2)
rows = manifest["rows"]
check("v2 dataset builds", manifest["sample_count"] == 60)
check("v2 feature count", len(manifest["feature_schema"]["columns"]) == len(V2_COLUMNS))
check("leakage validation passed", manifest["leakage_validation"]["passed"])

# Leakage injection
if rows:
    bad = inject_leakage_test_row(rows[0])
    caught = False
    try:
        validate_dataset([bad], feature_version=FEATURE_VERSION_V2, fail_loud=True)
    except LeakageError:
        caught = True
    check("leakage injection rejected", caught)

# Point-in-time history — first trade has zero prior
first_feats = rows[0]["features"]
check("hist count zero for first trade", first_feats["hist_trade_count_symbol"] == 0.0)

# Feature audit
audit = audit_features(rows, version=FEATURE_VERSION_V2)
check("feature audit runs", audit["row_count"] == 60)

# Dataset quality
dq = dataset_quality_report(manifest)
check("dataset quality", dq["eligible_trades"] == 60)

# Label audit
labels = label_audit(rows)
check("label audit", labels["primary_label"] == LabelName.BINARY_WIN.value)

# Baselines
splits = chronological_split(rows)
test = splits["test"]
baselines = run_all_baselines(test)
check("baselines computed", len(baselines) >= 3)

# Calibration
y_true = [int(r.get(LabelName.BINARY_WIN.value) or 0) for r in test]
cal = calibration_report(y_true, [0.6] * len(y_true))
check("calibration report", "calibration_status" in cal)

# Quality gates — weak model should NOT promote
weak = evaluate_promotion(
    test_metrics={"classification": {"accuracy": 0.40}, "sample_size": len(test)},
    baseline_metrics=naive_baseline_metrics(test),
    walk_forward={"aggregate": {"mean_accuracy": 0.40}},
    calibration={"calibration_status": "GOOD", "mean_calibration_error": 0.05},
)
check("weak model NOT_PROMOTED", weak["promotion_status"] == "NOT_PROMOTED")
check("weak model not passed", not weak["passed"])

# V2 encode single row
row = encode_trade_row_v2(_trade(0))
check("v2 encode", row is not None and "factor_count" in row["features"])

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\n{'='*50}")
print(f"AIA-08 Prediction Tests: {passed}/{len(results)} passed")
for ok, name, extra in results:
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f" — {extra}" if extra else ""))
if failed:
    print(f"\nFAILED: {failed}")
    sys.exit(1)
print("All tests passed.")
