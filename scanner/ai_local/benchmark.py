# -*- coding: utf-8 -*-
"""Claude vs Qwen benchmark — observational, not winner selection."""
from __future__ import annotations

from typing import Any

from scanner.ai_advisor.runtime_history import AdvisorRuntimeHistory

from .comparisons import ComparisonStore
from .history import LocalAIHistory
from .metrics import compute_metrics


def build_leaderboard() -> dict[str, Any]:
    """Provider leaderboard from real persisted records."""
    claude_rows = AdvisorRuntimeHistory().list_recent(limit=500)
    local_rows = LocalAIHistory().list_recent(limit=500)

    def _agg(rows: list[dict[str, Any]], provider: str) -> dict[str, Any]:
        if not rows:
            return {
                "provider": provider,
                "reviews": 0,
                "success_rate": 0.0,
                "avg_confidence": 0.0,
                "avg_latency_ms": 0.0,
                "avg_grounding": 0.0,
                "avg_hallucination": 0.0,
                "estimated_cost": 0.0,
            }
        confs = [float(r.get("confidence") or 0) for r in rows]
        lats = [float(r.get("latency_ms") or 0) for r in rows]
        ground = [float(r.get("grounding_score") or 0) for r in rows]
        hall = [float(r.get("hallucination_score") or 0) for r in rows]
        cost = sum(float(r.get("estimated_cost") or 0) for r in rows)
        return {
            "provider": provider,
            "reviews": len(rows),
            "success_rate": 100.0,
            "avg_confidence": round(sum(confs) / len(confs), 1),
            "avg_latency_ms": round(sum(lats) / len(lats), 1),
            "avg_grounding": round(sum(ground) / len(ground), 1) if ground else 0.0,
            "avg_hallucination": round(sum(hall) / len(hall), 1) if hall else 0.0,
            "estimated_cost": round(cost, 4),
        }

    claude = _agg(
        [r for r in claude_rows if (r.get("provider") or "") == "claude"],
        "claude",
    )
    local = _agg(local_rows, "ollama")
    local_metrics = compute_metrics()

    return {
        "claude": claude,
        "ollama": {**local, **{
            "success_rate": round(
                local_metrics["successful_reviews"] / local_metrics["total_reviews"] * 100, 1
            ) if local_metrics["total_reviews"] else 0.0,
            "estimated_cost": local_metrics["estimated_cost"],
        }},
        "difference": {
            "confidence": round(claude["avg_confidence"] - local["avg_confidence"], 1),
            "latency_ms": round(claude["avg_latency_ms"] - local["avg_latency_ms"], 1),
            "grounding": round(claude["avg_grounding"] - local["avg_grounding"], 1),
            "cost": round(claude["estimated_cost"] - local["estimated_cost"], 4),
        },
        "note": "Observational only — higher agreement does not imply better provider.",
    }


def benchmark_from_comparison(comparison: dict[str, Any]) -> dict[str, Any]:
    return {
        "comparison_id": comparison.get("comparison_id"),
        "package_fingerprint": comparison.get("package_fingerprint"),
        "symbol": comparison.get("symbol"),
        "timeframe": comparison.get("timeframe"),
        "claude": {
            "agreement": comparison.get("claude_agreement"),
            "confidence": comparison.get("claude_confidence"),
            "latency_ms": comparison.get("claude_latency_ms"),
            "estimated_cost": comparison.get("claude_estimated_cost"),
        },
        "ollama": {
            "agreement": comparison.get("local_agreement"),
            "confidence": comparison.get("local_confidence"),
            "latency_ms": comparison.get("local_latency_ms"),
            "estimated_cost": 0.0,
        },
        "difference": {
            "confidence": (comparison.get("claude_confidence") or 0)
            - (comparison.get("local_confidence") or 0),
            "latency_ms": (comparison.get("claude_latency_ms") or 0)
            - (comparison.get("local_latency_ms") or 0),
        },
    }


def recent_comparisons(limit: int = 20) -> list[dict[str, Any]]:
    return ComparisonStore().list_recent(limit)
