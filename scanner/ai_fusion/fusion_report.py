# -*- coding: utf-8 -*-
"""Human-readable fusion comparison report."""
from __future__ import annotations

from typing import Any

from .fusion_metrics import compute_metrics


def build_comparison_report(*,
                            history: list[dict[str, Any]] | None = None,
                            evaluations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    metrics = compute_metrics(history=history, evaluations=evaluations)
    rows = []
    for name, key in (
        ("Platform", "platform_accuracy"),
        ("LightGBM", "prediction_accuracy"),
        ("Fusion", "fusion_accuracy"),
    ):
        acc = metrics.get(key)
        rows.append({
            "component": name,
            "accuracy": acc,
            "sample": metrics.get("evaluation_samples") if acc is not None else 0,
        })

    claude_n = metrics.get("claude", {}).get("reviews", 0)
    qwen_n = metrics.get("qwen", {}).get("reviews", 0)
    if claude_n:
        rows.append({"component": "Claude", "accuracy": None, "sample": claude_n})
    if qwen_n:
        rows.append({"component": "Qwen", "accuracy": None, "sample": qwen_n})

    return {
        "status": metrics.get("status"),
        "comparison_table": rows,
        "metrics": metrics,
    }
