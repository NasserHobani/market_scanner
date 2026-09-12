# -*- coding: utf-8 -*-
"""Full model comparison — baselines, walk-forward, calibration."""
from __future__ import annotations

import statistics
from typing import Any

from scanner.ml.label_store import LabelName

from .baselines import run_all_baselines
from .calibration import calibration_report
from .evaluator import Evaluator
from .feature_registry import columns_for_version
from .quality_gates import evaluate_promotion, naive_baseline_metrics
from .trade_dataset import chronological_split


def walk_forward_report(wf_result: dict[str, Any]) -> dict[str, Any]:
    """Format walk-forward folds for reporting."""
    folds = wf_result.get("folds") or []
    accs = []
    fold_rows = []
    for f in folds:
        ev = f.get("evaluation") or {}
        cls = ev.get("classification") or {}
        acc = cls.get("accuracy")
        if acc is not None:
            accs.append(float(acc))
        fold_rows.append({
            "fold": f.get("fold_index", len(fold_rows)),
            "train_size": f.get("train_size"),
            "test_size": f.get("test_size"),
            "accuracy": acc,
        })

    agg = wf_result.get("aggregate") or {}
    return {
        "folds": fold_rows,
        "fold_count": len(fold_rows),
        "accuracies": [round(a * 100, 1) for a in accs],
        "mean_accuracy": agg.get("mean_accuracy"),
        "median_accuracy": round(statistics.median(accs), 4) if accs else None,
        "stdev_accuracy": round(statistics.pstdev(accs), 4) if len(accs) > 1 else 0,
        "mean_expectancy": agg.get("mean_expectancy"),
    }


def evaluate_candidate_model(rows: list[dict[str, Any]], *,
                             model_eval: dict[str, Any],
                             y_proba: list[float] | None = None,
                             walk_forward: dict[str, Any] | None = None,
                             feature_version: str = "2.0.0",
                             label_column: str = LabelName.BINARY_WIN.value) -> dict[str, Any]:
    """Compare model against all baselines on chronological test split."""
    splits = chronological_split(rows)
    test_rows = splits["test"] or splits["validation"]
    baseline_majority = naive_baseline_metrics(test_rows, label_column=label_column)
    all_baselines = run_all_baselines(test_rows, label_column=label_column)

    y_true = [int(r.get(label_column) or 0) for r in test_rows]
    cal = {}
    if y_proba and len(y_proba) == len(y_true):
        cal = calibration_report(y_true, y_proba)

    promotion = evaluate_promotion(
        test_metrics=model_eval,
        baseline_metrics=baseline_majority,
        walk_forward=walk_forward,
        calibration=cal,
    )

    return {
        "test_sample_size": len(test_rows),
        "model_metrics": model_eval,
        "baseline_majority": baseline_majority,
        "all_baselines": all_baselines,
        "walk_forward": walk_forward_report(walk_forward or {}),
        "calibration": cal,
        "promotion": promotion,
        "feature_version": feature_version,
        "feature_columns": columns_for_version(feature_version),
    }


def root_cause_analysis(rows: list[dict[str, Any]], *,
                        model_metrics: dict[str, Any],
                        baseline_metrics: dict[str, Any],
                        feature_audit: dict[str, Any],
                        dataset_quality: dict[str, Any],
                        walk_forward: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evidence-based diagnosis of why model underperforms baseline."""
    causes: list[dict[str, str]] = []
    cls = model_metrics.get("classification") or {}
    base_cls = baseline_metrics.get("classification") or {}
    model_acc = float(cls.get("accuracy") or 0)
    base_acc = float(base_cls.get("accuracy") or 0)

    if model_acc < base_acc:
        causes.append({
            "factor": "oos_underperformance",
            "evidence": f"model {model_acc:.1%} < baseline {base_acc:.1%}",
            "severity": "high",
        })

    useless = feature_audit.get("useless_features") or []
    if useless:
        causes.append({
            "factor": "weak_features",
            "evidence": f"constant/zero-variance: {', '.join(useless)}",
            "severity": "medium",
        })

    snap = dataset_quality.get("snapshot_coverage") or {}
    if snap.get("coverage_rate", 1) < 0.1:
        causes.append({
            "factor": "insufficient_signal",
            "evidence": f"snapshot coverage {snap.get('coverage_rate', 0):.1%}",
            "severity": "high",
        })

    if dataset_quality.get("concentration_warning"):
        causes.append({
            "factor": "symbol_timeframe_concentration",
            "evidence": dataset_quality["concentration_warning"],
            "severity": "medium",
        })

    cd = dataset_quality.get("class_distribution") or {}
    if cd.get("imbalance_ratio", 1) < 1.2:
        causes.append({
            "factor": "strong_naive_baseline",
            "evidence": f"near-balanced classes ({cd.get('positive_rate', 0):.1%} positive)",
            "severity": "medium",
        })

    wf = walk_forward or {}
    agg = wf.get("aggregate") or wf
    wf_mean = agg.get("mean_accuracy")
    fold_count = agg.get("fold_count") or len(wf.get("folds") or [])
    if wf_mean is None or fold_count < 2:
        causes.append({
            "factor": "walk_forward_insufficient",
            "evidence": "walk-forward folds missing or too few",
            "severity": "medium",
        })
    elif wf_mean < base_acc:
        causes.append({
            "factor": "temporal_instability",
            "evidence": f"walk-forward mean {wf_mean:.1%} < baseline",
            "severity": "high",
        })

    return {
        "model_accuracy": model_acc,
        "baseline_accuracy": base_acc,
        "gap": round(model_acc - base_acc, 4),
        "root_causes": causes,
        "primary_diagnosis": causes[0]["factor"] if causes else "unknown",
    }
