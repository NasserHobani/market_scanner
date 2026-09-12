# -*- coding: utf-8 -*-
"""Local AI metrics aggregation."""
from __future__ import annotations

from typing import Any

from .history import LocalAIHistory


def compute_metrics(history: LocalAIHistory | None = None) -> dict[str, Any]:
    hist = history or LocalAIHistory()
    rows = hist.list_recent(limit=10_000)
    if not rows:
        return {
            "total_reviews": 0,
            "successful_reviews": 0,
            "failed_reviews": 0,
            "validation_failures": 0,
            "grounding_failures": 0,
            "average_latency_ms": 0.0,
            "average_confidence": 0.0,
            "average_tokens": 0.0,
            "estimated_cost": 0.0,
            "agreement_rate": 0.0,
            "local_runtime_seconds": 0.0,
        }

    total = len(rows)
    ok = [r for r in rows if r.get("validation_passed")]
    failed = total - len(ok)
    val_fail = sum(1 for r in rows if r.get("validation_passed") is False)
    ground_fail = sum(1 for r in rows if (r.get("grounding_score") or 100) < 50)
    latencies = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
    confs = [float(r["confidence"]) for r in rows if r.get("confidence") is not None]
    tokens = [float(r.get("total_tokens") or 0) for r in rows]
    agrees = sum(1 for r in ok if (r.get("agreement") or "").lower() == "agree")
    runtime_s = sum(float(r.get("latency_ms") or 0) for r in rows) / 1000.0

    return {
        "total_reviews": total,
        "successful_reviews": len(ok),
        "failed_reviews": failed,
        "validation_failures": val_fail,
        "grounding_failures": ground_fail,
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "average_confidence": round(sum(confs) / len(confs), 1) if confs else 0.0,
        "average_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
        "estimated_cost": 0.0,
        "agreement_rate": round(agrees / len(ok) * 100, 1) if ok else 0.0,
        "local_runtime_seconds": round(runtime_s, 1),
    }
