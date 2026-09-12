# -*- coding: utf-8 -*-
"""Feature importance extraction and stability across folds."""
from __future__ import annotations

from typing import Any


def extract_importance(artifact: Any, *,
                       feature_columns: list[str]) -> list[dict[str, Any]]:
    """Extract feature importance from trained model artifact."""
    model = getattr(artifact, "model", None)
    if model is None:
        return []

    importances: dict[str, float] = {}
    if hasattr(model, "feature_importances_"):
        raw = model.feature_importances_
        for col, imp in zip(feature_columns, raw):
            importances[col] = float(imp)
    elif hasattr(model, "feature_importance"):
        raw = model.feature_importance(importance_type="gain")
        for col in feature_columns:
            importances[col] = float(raw.get(col, 0))

    total = sum(importances.values()) or 1.0
    rows = []
    for col in feature_columns:
        imp = importances.get(col, 0.0)
        rows.append({
            "feature": col,
            "importance": round(imp / total, 4),
            "raw_importance": round(imp, 4),
            "direction": None,
            "status": "useful" if imp / total > 0.05 else "low",
        })
    rows.sort(key=lambda r: r["importance"], reverse=True)
    return rows


def stability_across_folds(fold_importances: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Rank features by mean importance and coefficient of variation."""
    if not fold_importances:
        return []

    accum: dict[str, list[float]] = {}
    for fold in fold_importances:
        for row in fold:
            accum.setdefault(row["feature"], []).append(row["importance"])

    stable = []
    for feat, vals in accum.items():
        mean_imp = sum(vals) / len(vals)
        stdev = (sum((v - mean_imp) ** 2 for v in vals) / len(vals)) ** 0.5
        cv = stdev / mean_imp if mean_imp > 0 else 999.0
        status = "stable" if cv < 0.5 and mean_imp > 0.03 else (
            "unstable" if cv >= 0.5 else "useless")
        stable.append({
            "feature": feat,
            "mean_importance": round(mean_imp, 4),
            "stdev": round(stdev, 4),
            "cv": round(cv, 4),
            "folds_seen": len(vals),
            "status": status,
        })
    stable.sort(key=lambda r: r["mean_importance"], reverse=True)
    return stable
