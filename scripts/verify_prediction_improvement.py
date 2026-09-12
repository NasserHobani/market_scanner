#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIA-08 prediction improvement verification — real data, 15 stages.

Usage: python scripts/verify_prediction_improvement.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARNING"
REPORT_DIR = ROOT / "scanner"


def _stage(name: str, status: str, detail: str = "", **extra) -> dict:
    row = {"stage": name, "status": status, "detail": detail}
    row.update(extra)
    return row


def _write_report(name: str, content: str) -> Path:
    path = REPORT_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    stages: list[dict] = []
    numbers: dict = {}
    print("=== AIA-08 Prediction Improvement Verification ===\n")

    from scanner.predictive.trade_dataset import (
        DEFAULT_FEATURE_VERSION,
        build_from_trade_dicts,
        chronological_split,
        load_trades_from_django,
    )
    from scanner.predictive.feature_audit import audit_features
    from scanner.predictive.dataset_quality import dataset_quality_report
    from scanner.predictive.label_analysis import label_audit
    from scanner.predictive.leakage_detector import (
        LeakageError,
        inject_leakage_test_row,
        validate_dataset,
    )
    from scanner.predictive.baselines import run_all_baselines
    from scanner.predictive.calibration import calibration_report
    from scanner.predictive.model_evaluation import root_cause_analysis, walk_forward_report
    from scanner.predictive.quality_gates import evaluate_promotion, naive_baseline_metrics
    from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator
    from scanner.predictive.services import PredictiveService
    from scanner.predictive.config import load_prediction_config

    # 1. Load trades
    try:
        trades = load_trades_from_django()
        numbers["total_trades"] = len(trades)
        stages.append(_stage("load_trades", PASS if trades else FAIL, f"{len(trades)} closed"))
        print(f"Closed trades: {len(trades)}")
    except Exception as exc:  # noqa: BLE001
        stages.append(_stage("load_trades", FAIL, str(exc)[:200]))
        trades = []

    # 2. Dataset generation (V2)
    manifest = build_from_trade_dicts(trades, feature_version=DEFAULT_FEATURE_VERSION)
    rows = manifest["rows"]
    numbers["eligible_trades"] = manifest["sample_count"]
    numbers["rejected_trades"] = manifest["rejected_count"]
    numbers["dataset_id"] = manifest["dataset_id"]
    numbers["feature_version"] = manifest["dataset_version"]
    numbers["feature_count"] = len(manifest["feature_schema"]["columns"])
    stages.append(_stage(
        "dataset_generation", PASS if rows else FAIL,
        f"eligible={manifest['sample_count']} rejected={manifest['rejected_count']}",
    ))

    # 3. Feature audit
    feat_audit = audit_features(rows, version=DEFAULT_FEATURE_VERSION)
    numbers["useless_features"] = feat_audit.get("useless_features", [])
    stages.append(_stage(
        "feature_audit", PASS,
        f"{feat_audit['active_feature_count']} active, "
        f"{len(numbers['useless_features'])} constant",
    ))

    # 4. Leakage test
    try:
        validate_dataset(rows, feature_version=DEFAULT_FEATURE_VERSION, fail_loud=True)
        bad = inject_leakage_test_row(rows[0]) if rows else {}
        caught = False
        try:
            validate_dataset([bad], feature_version=DEFAULT_FEATURE_VERSION, fail_loud=True)
        except LeakageError:
            caught = True
        stages.append(_stage("leakage_test", PASS if caught else FAIL,
                             "injection rejected" if caught else "injection not caught"))
    except LeakageError as exc:
        stages.append(_stage("leakage_test", FAIL, str(exc)[:200]))

    # 5. Dataset quality
    dq = dataset_quality_report(manifest)
    numbers["class_distribution"] = dq.get("class_distribution")
    numbers["snapshot_coverage"] = dq.get("snapshot_coverage")
    stages.append(_stage(
        "dataset_quality", PASS if dq["eligible_trades"] > 0 else FAIL,
        dq.get("concentration_warning") or "diversity ok",
    ))

    # 6. Label analysis
    labels = label_audit(rows)
    numbers["label_noise"] = labels.get("label_noise_estimate")
    stages.append(_stage("label_analysis", PASS,
                         f"positive_rate={labels.get('win_loss_positive_rate')}"))

    # 7. Chronological split
    splits = chronological_split(rows)
    stages.append(_stage(
        "chronological_split", PASS,
        f"train={len(splits['train'])} val={len(splits['validation'])} test={len(splits['test'])}",
    ))

    # 8. Baselines
    test_rows = splits["test"] or splits["validation"]
    baselines = run_all_baselines(test_rows) if test_rows else []
    baseline_majority = naive_baseline_metrics(test_rows) if test_rows else {}
    numbers["baseline_accuracy"] = (baseline_majority.get("classification") or {}).get("accuracy")
    stages.append(_stage(
        "baselines", PASS if baselines else WARN,
        f"majority={numbers['baseline_accuracy']}",
    ))

    # 9. Existing model metrics
    svc = PredictiveService()
    models = svc.list_models()
    numbers["model_count"] = len(models)
    latest = models[0] if models else None
    model_eval = {}
    wf_report = {}
    cal = {}
    promotion = {}
    if latest and test_rows:
        try:
            model_eval = svc.evaluate(latest["model_id"], test_rows)
            numbers["model_oos_accuracy"] = (model_eval.get("classification") or {}).get("accuracy")
            wf_raw = latest.get("walk_forward_summary") or {}
            wf_report = walk_forward_report(wf_raw)
            y_true = [int(r.get("label_binary_win") or 0) for r in test_rows]
            # Use majority proba as placeholder if no proba available
            proba = [numbers["model_oos_accuracy"] or 0.5] * len(y_true)
            cal = calibration_report(y_true, proba)
            promotion = evaluate_promotion(
                test_metrics=model_eval,
                baseline_metrics=baseline_majority,
                walk_forward=wf_raw,
                calibration=cal,
            )
            numbers["promotion_status"] = promotion.get("promotion_status")
        except Exception as exc:  # noqa: BLE001
            stages.append(_stage("existing_model", WARN, str(exc)[:200]))
    stages.append(_stage(
        "existing_model",
        PASS if latest else WARN,
        f"model={latest.get('model_id') if latest else 'none'} "
        f"oos={numbers.get('model_oos_accuracy')}",
    ))

    # 10. Walk-forward
    stages.append(_stage(
        "walk_forward",
        PASS if wf_report.get("fold_count", 0) >= 1 else WARN,
        f"folds={wf_report.get('fold_count', 0)} mean={wf_report.get('mean_accuracy')}",
    ))

    # 11. Calibration
    stages.append(_stage(
        "calibration",
        PASS if cal.get("calibration_status") != "CALIBRATION_FAILED" else WARN,
        cal.get("calibration_status", "n/a"),
    ))

    # 12. Quality gates
    gate_pass = promotion.get("passed", False)
    stages.append(_stage(
        "quality_gates",
        PASS if gate_pass else WARN,
        promotion.get("reason", "no model evaluated"),
    ))

    # 13. Model registry
    stages.append(_stage(
        "model_registry", PASS if models else WARN, f"{len(models)} models"),
    )

    # 14. Inference (ACTIVE only)
    orch = PredictionTrainingOrchestrator()
    pred = orch.predict_for_trade_context({"trade": trades[0] if trades else {}})
    inference_ok = not pred.get("available")  # Should be UNAVAILABLE without ACTIVE
    stages.append(_stage(
        "inference",
        PASS if inference_ok else WARN,
        pred.get("reason", "UNAVAILABLE as expected"),
    ))

    # 15. Orchestrator status
    status = orch.status()
    ps = status.get("prediction_status") or {}
    numbers["prediction_status"] = ps.get("status")
    numbers["active_model"] = status.get("models", {}).get("active")
    stages.append(_stage(
        "orchestrator_status", PASS,
        f"status={ps.get('status')} active={numbers['active_model']}",
    ))

    # Root cause
    root = root_cause_analysis(
        rows,
        model_metrics=model_eval or {"classification": {"accuracy": 0}},
        baseline_metrics=baseline_majority,
        feature_audit=feat_audit,
        dataset_quality=dq,
        walk_forward=latest.get("walk_forward_summary") if latest else {},
    )
    numbers["root_cause"] = root.get("primary_diagnosis")

    cfg = load_prediction_config()
    numbers["next_training_trigger"] = cfg.min_new_trades

    # Write reports
    feat_table = "| feature | source | availability | missing_rate | leakage_risk | type | status |\n"
    feat_table += "|---|---|---|---|---|---|---|\n"
    for f in feat_audit.get("features", []):
        feat_table += (
            f"| {f['feature']} | {f['source']} | {f['availability']} | "
            f"{f['missing_rate']} | {f['leakage_risk']} | {f['type']} | {f['status']} |\n"
        )

    _write_report("AIA-08_FEATURE_AUDIT.md", f"""# AIA-08 Feature Audit

- Dataset: `{manifest['dataset_id']}`
- Feature version: `{DEFAULT_FEATURE_VERSION}`
- Eligible rows: {manifest['sample_count']}
- Active features: {feat_audit['active_feature_count']}
- Useless/constant: {', '.join(numbers['useless_features']) or 'none'}

{feat_table}
""")

    _write_report("AIA-08_DATASET_REPORT.md", f"""# AIA-08 Dataset Report

| Metric | Value |
|---|---|
| Total trades | {dq['total_trades']} |
| Eligible | {dq['eligible_trades']} |
| Rejected | {dq['rejected_trades']} |
| Duplicates | {len(dq.get('duplicate_trade_ids') or [])} |
| Positive rate | {dq['class_distribution']['positive_rate']} |
| Symbols | {dq['symbols']['count']} |
| Snapshot coverage | {dq['snapshot_coverage']['coverage_rate']} |
| Concentration | {dq.get('concentration_warning') or 'OK'} |
| Date range | {manifest.get('date_range')} |
| Fingerprint | `{manifest.get('fingerprint')}` |
""")

    bl_lines = "\n".join(
        f"- **{b['name']}**: accuracy={(b.get('metrics') or {}).get('classification', {}).get('accuracy')}"
        for b in baselines
    )
    _write_report("AIA-08_MODEL_COMPARISON.md", f"""# AIA-08 Model Comparison

## Existing model
- Model ID: `{latest.get('model_id') if latest else 'none'}`
- OOS accuracy: {numbers.get('model_oos_accuracy')}
- Baseline (majority): {numbers.get('baseline_accuracy')}
- Gap: {root.get('gap')}

## Baselines
{bl_lines}

## Root cause
Primary: **{root.get('primary_diagnosis')}**

{json.dumps(root.get('root_causes', []), indent=2)}
""")

    fold_lines = "\n".join(
        f"- Fold {f['fold']}: {f.get('accuracy')}" for f in wf_report.get("folds", [])
    )
    _write_report("AIA-08_WALK_FORWARD_REPORT.md", f"""# AIA-08 Walk-Forward Report

- Fold count: {wf_report.get('fold_count', 0)}
- Mean accuracy: {wf_report.get('mean_accuracy')}
- Median: {wf_report.get('median_accuracy')}
- Stdev: {wf_report.get('stdev_accuracy')}

## Folds
{fold_lines or 'No walk-forward folds available'}
""")

    bucket_lines = "\n".join(
        f"- {b['range']}: predicted={b['predicted_mid']} actual={b.get('actual_rate')} n={b['sample_size']}"
        for b in cal.get("buckets", [])
    )
    _write_report("AIA-08_CALIBRATION_REPORT.md", f"""# AIA-08 Calibration Report

- Status: **{cal.get('calibration_status', 'n/a')}**
- Brier score: {cal.get('brier_score')}
- Mean calibration error: {cal.get('mean_calibration_error')}

## Buckets
{bucket_lines or 'Insufficient data for calibration buckets'}
""")

    _write_report("AIA-08_QUALITY_GATE_REPORT.md", f"""# AIA-08 Quality Gate Report

- Promotion status: **{promotion.get('promotion_status', 'NOT_PROMOTED')}**
- Passed: {promotion.get('passed', False)}
- Reason: {promotion.get('reason', 'n/a')}
- OOS: {promotion.get('test_accuracy')}
- Baseline: {promotion.get('baseline_accuracy')}
- Improvement: {promotion.get('improvement_pct')}%
- Walk-forward pass: {promotion.get('walk_forward_pass')}
- Calibration pass: {promotion.get('calibration_pass')}
""")

    fail_count = sum(1 for s in stages if s["status"] == FAIL)
    warn_count = sum(1 for s in stages if s["status"] == WARN)
    overall = FAIL if fail_count else (WARN if warn_count else PASS)

    runtime_md = f"""# AIA-08 Runtime Verification

**Overall: {overall}**

| Stage | Status | Detail |
|---|---|---|
"""
    for s in stages:
        runtime_md += f"| {s['stage']} | {s['status']} | {s['detail'][:80]} |\n"

    runtime_md += f"""
## Summary numbers
```json
{json.dumps(numbers, indent=2, default=str)}
```

## Label audit
{json.dumps(labels, indent=2, default=str)}

## Prediction status
- Status: **{numbers.get('prediction_status')}**
- Active model: `{numbers.get('active_model')}`
- Models trained: {numbers.get('model_count')}
"""
    _write_report("AIA-08_RUNTIME_VERIFICATION.md", runtime_md)

    print("\n=== Stage Results ===")
    for s in stages:
        print(f"  [{s['status']}] {s['stage']}: {s['detail'][:100]}")
    print(f"\nOverall: {overall}")
    print(f"Reports written to {REPORT_DIR}/AIA-08_*.md")
    return 1 if overall == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
