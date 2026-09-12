# -*- coding: utf-8 -*-
"""Provider leaderboard — ranks Claude, GPT, Gemini, DeepSeek, Open Source."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scanner.tracking import wilson

from .advisor_metrics import AdvisorMetrics

PROVIDER_IDS = ("claude", "openai", "gemini", "deepseek", "open_source", "openrouter", "mock")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderLeaderboard:
    """Rank providers by evaluation outcomes."""

    def __init__(self, metrics: AdvisorMetrics | None = None) -> None:
        self._metrics = metrics or AdvisorMetrics()

    def compute(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_provider: dict[str, list[dict]] = {}
        for r in records:
            pid = str(r.get("provider") or "unknown")
            by_provider.setdefault(pid, []).append(r)

        rows = []
        for provider, items in by_provider.items():
            correct = sum(1 for r in items if r.get("advisor_correct"))
            agreements = sum(1 for r in items if r.get("advisor_agreement") == "agree")
            hallucinations = sum(1 for r in items if r.get("hallucination"))
            useful = sum(1 for r in items if r.get("useful_warning"))
            confidences = [float(r["advisor_confidence"]) for r in items
                           if r.get("advisor_confidence") is not None]
            n = len(items)
            lo, hi = wilson(correct, n) if n else (0.0, 0.0)

            rows.append({
                "provider": provider,
                "accuracy": round(correct / n * 100, 1) if n else None,
                "accuracy_ci": [lo, hi],
                "agreement": round(agreements / n * 100, 1) if n else None,
                "hallucination_rate": round(hallucinations / n * 100, 1) if n else None,
                "useful_reviews": useful,
                "average_confidence": round(sum(confidences) / len(confidences), 1) if confidences else None,
                "review_count": n,
                "last_updated": _now(),
            })

        rows.sort(key=lambda x: (x["accuracy"] or 0, x["review_count"]), reverse=True)
        for i, row in enumerate(rows, 1):
            row["rank"] = i
        return rows

    def to_ui_model(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "providers": self.compute(records),
            "total_evaluations": len(records),
            "last_updated": _now(),
        }
