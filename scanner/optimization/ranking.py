# -*- coding: utf-8 -*-
"""Parameter set ranking and leaderboards."""
from __future__ import annotations

from typing import Any


DEFAULT_RANKING_WEIGHTS = {
    "expectancy": 0.35,
    "profit_factor": 0.20,
    "avg_r": 0.15,
    "win_rate": 0.10,
    "oos_expectancy": 0.20,
}


class ParameterRanker:
    """Generate leaderboards from evaluation results."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or dict(DEFAULT_RANKING_WEIGHTS)

    def _score(self, result: dict[str, Any]) -> float:
        score = 0.0
        total_weight = 0.0
        for metric, weight in self._weights.items():
            val = result.get(metric)
            if metric == "oos_expectancy":
                oos = result.get("oos_performance") or {}
                val = oos.get("expectancy")
            if val is None:
                continue
            total_weight += weight
            if metric == "win_rate":
                score += weight * (float(val) / 100.0)
            elif metric == "profit_factor":
                score += weight * min(float(val), 5.0) / 5.0
            else:
                score += weight * float(val)
        return round(score / total_weight, 6) if total_weight > 0 else 0.0

    def rank(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scored = []
        for r in results:
            entry = dict(r)
            entry["composite_score"] = self._score(r)
            scored.append(entry)
        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        for i, entry in enumerate(scored):
            entry["rank"] = i + 1
        return scored

    def leaderboard(self, results: list[dict[str, Any]], *,
                    top_n: int = 10) -> dict[str, Any]:
        ranked = self.rank(results)
        return {
            "top_strategies": ranked[:top_n],
            "top_parameter_sets": [r["params"] for r in ranked[:top_n]],
            "worst_parameter_sets": [r["params"] for r in ranked[-top_n:][::-1]],
            "total_evaluated": len(ranked),
            "weights": dict(self._weights),
        }

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)
