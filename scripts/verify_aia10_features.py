# -*- coding: utf-8 -*-
"""AIA-10 runtime verification — point-in-time snapshots & Dataset V3."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from scanner.feature_snapshots import PointInTimeSnapshotService
    from scanner.feature_snapshots.builder import build_snapshot, extract_v3_features
    from scanner.feature_snapshots.coverage import coverage_report
    from scanner.feature_snapshots.contract import SnapshotStatus
    from scanner.feature_snapshots.historical import batch_reconstruct
    from scanner.feature_snapshots.store import count_snapshots, iter_snapshots
    from scanner.predictive.dataset_v3 import build_dataset_v3, dataset_v3_quality, run_v3_experiment
    from scanner.predictive.feature_audit import audit_features_v3
    from scanner.predictive.feature_registry import FEATURE_VERSION_V3, V3_COLUMNS
    from scanner.predictive.leakage_detector import adversarial_leakage_tests, validate_provenance
    from scanner.predictive.trade_dataset import load_trades_from_django
    from scanner.ai_fusion.prediction_adapter import PredictionAdapter

    print("=" * 40)
    print("AIA-10 FEATURE VERIFICATION")
    print("=" * 40)

    trades: list[dict] = []
    try:
        trades = load_trades_from_django()
    except Exception:
        trades = []

    hist = batch_reconstruct(trades) if trades else {"original_snapshot_count": 0,
                                                      "reconstructed_snapshot_count": 0,
                                                      "unavailable_count": 0}
    cov = coverage_report(closed_trades=trades) if trades else {
        "historical": {"coverage_pct": 0}, "runtime": {"coverage_pct": 0},
    }

    print(f"\nHistorical snapshots:")
    print(f"  original: {hist.get('original_snapshot_count', 0)}")
    print(f"  reconstructed: {hist.get('reconstructed_snapshot_count', 0)}")
    print(f"  unavailable: {hist.get('unavailable_count', 0)}")
    print(f"\nHistorical coverage: {cov['historical'].get('coverage_pct', 0)}%")

    runtime = cov.get("runtime", {})
    print(f"\nNew runtime snapshots: {runtime.get('created', 0)} created, "
          f"{runtime.get('partial', 0)} partial, {runtime.get('failed', 0)} failed")
    print(f"New runtime coverage: {runtime.get('coverage_pct', 0)}%")

    pit_count = count_snapshots()
    snaps = iter_snapshots()
    feat_counts = [len(s.features) for s in snaps]
    avg_feats = sum(feat_counts) / len(feat_counts) if feat_counts else 0
    print(f"\nFeature count (avg): {avg_feats:.1f} / {len(V3_COLUMNS)} spec")

    manifest = build_dataset_v3(trades, reconstruct=False) if trades else {"rows": [], "eligible_count": 0}
    rows = manifest.get("rows") or []
    audit = audit_features_v3(rows) if rows else {"classifications": {}}
    missing_rates = [f.get("missing_rate", 0) for f in audit.get("features", [])]
    avg_missing = sum(missing_rates) / len(missing_rates) if missing_rates else 0
    print(f"Feature missing rate (avg): {avg_missing:.2%}")

    leakage_pass = manifest.get("leakage_validation", {}).get("passed", True)
    if rows:
        base = rows[0]
        adv = adversarial_leakage_tests(base)
        leakage_pass = leakage_pass and all(adv.values())
    print(f"\nLeakage: {'PASS' if leakage_pass else 'FAIL'}")

    dq = dataset_v3_quality(manifest) if rows else {}
    print(f"\nDataset V3: {manifest.get('dataset_id', 'n/a')}")
    print(f"Eligible: {manifest.get('eligible_count', 0)}")
    print(f"Rejected: {manifest.get('rejected_count', 0)}")

    from scanner.feature_snapshots.config import DEFAULT_RUNTIME_CONFIG

    cfg = DEFAULT_RUNTIME_CONFIG
    eligible_n = manifest.get("eligible_count", 0)
    print(f"\nV3 smoke minimum: {cfg.v3_smoke_min_rows} (train: {cfg.v3_train_min_rows})")
    if eligible_n < cfg.v3_smoke_min_rows:
        print("Model evaluation: SKIPPED — insufficient V3 eligible rows")
        experiment = {}
    else:
        experiment = run_v3_experiment(manifest)
    naive = experiment.get("naive_baseline", {})
    base_acc = (naive.get("classification") or {}).get("accuracy")
    v3_acc = (experiment.get("v3_test", {}).get("classification") or {}).get("accuracy")
    print(f"\nBaseline: {round(base_acc * 100, 1) if base_acc else 'n/a'}%")
    print(f"V3 OOS: {round(v3_acc * 100, 1) if v3_acc else 'n/a'}%")
    wf = experiment.get("walk_forward", {})
    print(f"Walk-forward: mean={wf.get('mean_accuracy', 'n/a')}")
    cal = experiment.get("calibration", {})
    print(f"Calibration: {cal.get('calibration_status', 'n/a')}")
    gate = experiment.get("quality_gate", {})
    print(f"Quality Gate: {gate.get('promotion_status', 'NOT_RUN')}")

    pred = PredictionAdapter().to_udp_section({})
    pred_status = pred.get("status", "UNAVAILABLE")
    if pred_status != "ACTIVE":
        pred_line = "UNAVAILABLE — no model passed quality gates."
    else:
        pred_line = "ACTIVE"
    print(f"\nPrediction: {pred_line}")
    print(f"Fusion: PREDICTION_UNAVAILABLE" if pred_status != "ACTIVE" else "Fusion: operational")
    print("=" * 40)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
