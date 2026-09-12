# -*- coding: utf-8 -*-
"""Model quality gates — promotion requires beating baseline OOS."""
from __future__ import annotations

from typing import Any

PROMOTION_NOT_PROMOTED = "NOT_PROMOTED"
PROMOTION_CANDIDATE = "CANDIDATE_FOR_PROMOTION"
PROMOTION_ACTIVE = "ACTIVE"
PROMOTION_TRAINED = "TRAINED"
PROMOTION_RETIRED = "RETIRED"
PROMOTION_REJECTED = "REJECTED"


def evaluate_promotion(*,
                       test_metrics: dict[str, Any],
                       baseline_metrics: dict[str, Any],
                       walk_forward: dict[str, Any] | None = None,
                       calibration: dict[str, Any] | None = None,
                       min_samples: int = 10,
                       min_accuracy_improvement: float = 0.02,
                       min_test_samples: int = 5,
                       max_calibration_error: float = 0.20,
                       max_walk_forward_stdev: float = 0.15) -> dict[str, Any]:
    """Compare model OOS metrics against naive baseline."""
    cls = test_metrics.get("classification") or {}
    base_cls = baseline_metrics.get("classification") or {}
    trading = test_metrics.get("trading") or {}
    base_trading = baseline_metrics.get("trading") or {}

    test_n = int(test_metrics.get("sample_size") or cls.get("sample_size") or 0)
    if test_n < min_test_samples:
        return {
            "promotion_status": PROMOTION_NOT_PROMOTED,
            "passed": False,
            "reason": f"insufficient test samples ({test_n}/{min_test_samples})",
            "test_accuracy": cls.get("accuracy"),
            "baseline_accuracy": base_cls.get("accuracy"),
            "walk_forward_pass": False,
        }

    test_acc = float(cls.get("accuracy") or 0)
    base_acc = float(base_cls.get("accuracy") or 0)
    improvement = round(test_acc - base_acc, 4)

    wf_pass = True
    wf_mean = None
    wf_stdev = None
    if walk_forward:
        agg = walk_forward.get("aggregate") or walk_forward
        wf_mean = agg.get("mean_accuracy")
        wf_pass = wf_mean is not None and float(wf_mean) >= base_acc
        folds = walk_forward.get("folds") or []
        accs = [
            (f.get("evaluation") or {}).get("classification", {}).get("accuracy")
            for f in folds
        ]
        accs = [float(a) for a in accs if a is not None]
        if len(accs) > 1:
            import statistics
            wf_stdev = round(statistics.pstdev(accs), 4)
            if wf_stdev > max_walk_forward_stdev:
                wf_pass = False

    cal_status = "unknown"
    cal_pass = True
    if calibration:
        cal_status = calibration.get("calibration_status", "unknown")
        cal_pass = cal_status not in ("CALIBRATION_FAILED",)
        if cal_status == "INSUFFICIENT_SAMPLE":
            cal_pass = True
        elif calibration.get("mean_calibration_error") is not None:
            cal_pass = cal_pass and float(calibration["mean_calibration_error"]) <= max_calibration_error

    test_exp = trading.get("expectancy")
    base_exp = base_trading.get("expectancy")
    exp_better = True
    if test_exp is not None and base_exp is not None:
        exp_better = float(test_exp) >= float(base_exp)

    passed = (
        improvement >= min_accuracy_improvement
        and wf_pass
        and cal_pass
        and exp_better
        and test_n >= min_samples
    )

    status = PROMOTION_CANDIDATE if passed else PROMOTION_NOT_PROMOTED
    if not passed:
        if improvement < min_accuracy_improvement:
            reason = f"accuracy improvement {improvement:.3f} < {min_accuracy_improvement}"
        elif not cal_pass:
            reason = f"calibration gate failed ({cal_status})"
        elif not wf_pass:
            reason = "walk-forward or stability gate failed"
        else:
            reason = "expectancy gate failed"
    else:
        reason = "beats baseline on OOS with calibration and walk-forward"

    return {
        "promotion_status": status,
        "passed": passed,
        "reason": reason,
        "test_accuracy": round(test_acc, 4),
        "baseline_accuracy": round(base_acc, 4),
        "improvement": improvement,
        "improvement_pct": round(improvement * 100, 1),
        "test_expectancy": test_exp,
        "baseline_expectancy": base_exp,
        "walk_forward_mean_accuracy": wf_mean,
        "walk_forward_stdev": wf_stdev,
        "walk_forward_pass": wf_pass,
        "calibration_status": cal_status,
        "calibration_pass": cal_pass,
        "sample_size": test_n,
        "calibration": cal_status,
    }


def naive_baseline_metrics(rows: list[dict[str, Any]], *,
                           label_column: str = "label_binary_win") -> dict[str, Any]:
    """Majority-class baseline on label distribution."""
    if not rows:
        return {"classification": {"accuracy": 0.0, "sample_size": 0}}
    labels = [int(r.get(label_column) or r.get("labels", {}).get(label_column) or 0)
              for r in rows]
    n = len(labels)
    majority = 1 if sum(labels) >= n / 2 else 0
    acc = sum(1 for y in labels if y == majority) / n
    win_rate = sum(labels) / n
    return {
        "classification": {
            "accuracy": round(acc, 4),
            "sample_size": n,
            "precision": round(win_rate, 4),
            "recall": round(win_rate, 4) if majority == 1 else round(1 - win_rate, 4),
        },
        "trading": {
            "win_rate": round(win_rate * 100, 2),
            "expectancy": 0.0,
            "sample_size": n,
        },
        "sample_size": n,
        "baseline_type": "majority_class",
    }
