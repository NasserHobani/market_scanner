# -*- coding: utf-8 -*-
"""Reflection engine — periodic analysis over evaluations and outcomes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from scanner.tracking import wilson

REFLECTION_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReflectionEngine:
    """Reflect on completed evaluations within configurable scope.

  Scopes: last_n, last_week, last_month, market, timeframe, strategy, provider.
    """

    def reflect(self, *,
                evaluations: list[dict[str, Any]],
                scope: dict[str, Any] | None = None,
                trade_outcomes: list[dict[str, Any]] | None = None,
                research_results: list[dict[str, Any]] | None = None,
                optimization_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        scope = scope or {}
        filtered = self._filter(evaluations, scope)

        correct = sum(1 for e in filtered if e.get("advisor_correct"))
        n = len(filtered)
        lo, hi = wilson(correct, n) if n else (0.0, 0.0)

        failures = [e for e in filtered if not e.get("advisor_correct")]
        successes = [e for e in filtered if e.get("advisor_correct")]

        return {
            "reflection_version": REFLECTION_VERSION,
            "generated_at": _now(),
            "scope": scope,
            "sample_size": n,
            "accuracy": round(correct / n * 100, 1) if n else None,
            "accuracy_ci": [lo, hi],
            "failures": self._summarize_group(failures, "failure"),
            "successes": self._summarize_group(successes, "success"),
            "trade_outcomes_count": len(trade_outcomes or []),
            "research_results_count": len(research_results or []),
            "optimization_results_count": len(optimization_results or []),
            "evaluations": filtered,
        }

    def _filter(self, evaluations: list[dict[str, Any]],
                scope: dict[str, Any]) -> list[dict[str, Any]]:
        result = list(evaluations)

        if scope.get("last_n"):
            result = result[-int(scope["last_n"]):]

        if scope.get("last_week"):
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            result = [e for e in result if (e.get("execution_date") or "") >= since]

        if scope.get("last_month"):
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
            result = [e for e in result if (e.get("execution_date") or "") >= since]

        for field in ("market", "timeframe", "strategy", "provider"):
            if scope.get(field):
                val = str(scope[field]).lower()
                result = [
                    e for e in result
                    if str(e.get(field, "")).lower() == val
                ]

        return result

    @staticmethod
    def _summarize_group(items: list[dict[str, Any]], kind: str) -> dict[str, Any]:
        if not items:
            return {"count": 0, "top_reasons": [], "by_provider": {}, "by_market": {}}

        reasons: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        by_market: dict[str, int] = {}

        for e in items:
            if e.get("hallucination"):
                reasons["hallucination"] = reasons.get("hallucination", 0) + 1
            elif e.get("missed_warning"):
                reasons["missed_warning"] = reasons.get("missed_warning", 0) + 1
            elif e.get("false_warning"):
                reasons["false_warning"] = reasons.get("false_warning", 0) + 1
            elif kind == "failure" and e.get("advisor_agreement") == "agree":
                reasons["wrong_agreement"] = reasons.get("wrong_agreement", 0) + 1
            elif kind == "failure" and e.get("advisor_agreement") == "disagree":
                reasons["wrong_disagreement"] = reasons.get("wrong_disagreement", 0) + 1
            elif kind == "success":
                reasons["aligned_outcome"] = reasons.get("aligned_outcome", 0) + 1

            prov = e.get("provider", "unknown")
            by_provider[prov] = by_provider.get(prov, 0) + 1
            mkt = e.get("market", "unknown")
            by_market[mkt] = by_market.get(mkt, 0) + 1

        top = sorted(reasons.items(), key=lambda x: x[1], reverse=True)
        return {
            "count": len(items),
            "top_reasons": [{"reason": k, "count": v} for k, v in top[:5]],
            "by_provider": by_provider,
            "by_market": by_market,
        }
