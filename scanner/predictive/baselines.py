# -*- coding: utf-8 -*-
"""Transparent baseline models for comparison."""
from __future__ import annotations

from typing import Any

from scanner.ml.label_store import LabelName

from .evaluator import Evaluator


def majority_baseline_predictions(rows: list[dict[str, Any]], *,
                                  label_column: str = LabelName.BINARY_WIN.value) -> list[float]:
    labels = [int(r.get(label_column) or 0) for r in rows]
    majority = 1.0 if sum(labels) >= len(labels) / 2 else 0.0
    return [majority] * len(rows)


def historical_winrate_baseline(rows: list[dict[str, Any]]) -> list[float]:
    """Use point-in-time historical win rate per symbol."""
    preds = []
    for r in rows:
        feats = r.get("features") or r
        rate = feats.get("hist_win_rate_symbol", 0.5)
        preds.append(float(rate) if rate else 0.5)
    return preds


def rule_based_baseline(rows: list[dict[str, Any]], *,
                        score_threshold: float = 60.0) -> list[float]:
    """Predict win if platform score >= threshold."""
    preds = []
    for r in rows:
        feats = r.get("features") or r
        score = float(feats.get("score") or feats.get("snap_score") or 0)
        preds.append(1.0 if score >= score_threshold else 0.0)
    return preds


def evaluate_baseline(name: str, rows: list[dict[str, Any]], *,
                      predictions: list[float],
                      label_column: str = LabelName.BINARY_WIN.value) -> dict[str, Any]:
    y_true = [float(int(r.get(label_column) or 0)) for r in rows]
    y_pred = predictions
    y_proba = predictions
    r_mults = [float(r.get(LabelName.R_MULTIPLE.value) or r.get("r_multiple") or 0) for r in rows]
    metrics = Evaluator().evaluate(
        y_true=y_true, y_pred=y_pred, y_proba=y_proba,
        r_multiples=r_mults, task_type="classification",
    )
    return {"name": name, "metrics": metrics}


def run_all_baselines(rows: list[dict[str, Any]], *,
                      label_column: str = LabelName.BINARY_WIN.value) -> list[dict[str, Any]]:
    results = []
    baselines = [
        ("naive_majority", majority_baseline_predictions(rows, label_column=label_column)),
        ("historical_winrate", historical_winrate_baseline(rows)),
        ("rule_score_60", rule_based_baseline(rows, score_threshold=60)),
        ("rule_score_70", rule_based_baseline(rows, score_threshold=70)),
    ]
    for name, preds in baselines:
        results.append(evaluate_baseline(name, rows, predictions=preds, label_column=label_column))
    return results


def logistic_regression_baseline(rows: list[dict[str, Any]], *,
                                 feature_columns: list[str],
                                 label_column: str = LabelName.BINARY_WIN.value) -> dict[str, Any]:
    """Sklearn logistic regression baseline — chronological train on all rows for eval only."""
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:
        return {"name": "logistic_regression", "error": "sklearn not available"}

    X, y = [], []
    for r in rows:
        feats = r.get("features") or r
        X.append([float(feats.get(c) or 0) for c in feature_columns])
        y.append(int(r.get(label_column) or 0))

    if len(set(y)) < 2 or len(X) < 20:
        return {"name": "logistic_regression", "error": "insufficient data"}

    split = int(len(X) * 0.7)
    model = LogisticRegression(max_iter=500, random_state=42)
    model.fit(X[:split], y[:split])
    proba = model.predict_proba(X[split:])[:, 1].tolist()
    test_rows = rows[split:]
    metrics = Evaluator().evaluate(
        y_true=[float(v) for v in y[split:]],
        y_pred=proba,
        y_proba=proba,
        r_multiples=[float(r.get(LabelName.R_MULTIPLE.value) or 0) for r in test_rows],
        task_type="classification",
    )
    return {"name": "logistic_regression", "metrics": metrics, "coefficients": dict(
        zip(feature_columns, model.coef_[0].tolist()))}
