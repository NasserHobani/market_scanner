# -*- coding: utf-8 -*-
"""Advisor Score — measure the AI advisor itself."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .memory import AdvisorMemory


@dataclass
class AdvisorScoreMetrics:
    total_reviews: int = 0
    accepted_reviews: int = 0
    rejected_reviews: int = 0
    helpful_reviews: int = 0
    misleading_reviews: int = 0
    hallucination_count: int = 0
    agreement_with_decision_engine: int = 0
    disagreement_with_decision_engine: int = 0
    agreement_with_reality: int = 0
    disagreement_with_reality: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_reviews": self.total_reviews,
            "accepted_reviews": self.accepted_reviews,
            "rejected_reviews": self.rejected_reviews,
            "helpful_reviews": self.helpful_reviews,
            "misleading_reviews": self.misleading_reviews,
            "hallucination_count": self.hallucination_count,
            "agreement_with_decision_engine": self.agreement_with_decision_engine,
            "disagreement_with_decision_engine": self.disagreement_with_decision_engine,
            "agreement_with_reality": self.agreement_with_reality,
            "disagreement_with_reality": self.disagreement_with_reality,
        }


class AdvisorScore:
    """Compute and track advisor quality metrics."""

    def __init__(self, memory: AdvisorMemory | None = None) -> None:
        self._memory = memory or AdvisorMemory()
        self._metrics = AdvisorScoreMetrics()

    def compute(self) -> dict[str, Any]:
        records = self._memory.list_recent(10000)
        m = AdvisorScoreMetrics()

        for record in records:
            m.total_reviews += 1
            if record.get("accepted"):
                m.accepted_reviews += 1
            if record.get("rejected"):
                m.rejected_reviews += 1

            response = record.get("response") or {}
            validation = response.get("validation") or {}
            m.hallucination_count += validation.get("hallucination_count", 0)

            agreement = response.get("agreement", "")
            if agreement == "agree":
                m.agreement_with_decision_engine += 1
            elif agreement == "disagree":
                m.disagreement_with_decision_engine += 1

            perf = record.get("later_performance") or {}
            if perf.get("outcome") == "correct":
                m.agreement_with_reality += 1
                m.helpful_reviews += 1
            elif perf.get("outcome") == "incorrect":
                m.disagreement_with_reality += 1
                m.misleading_reviews += 1

        self._metrics = m
        score = self._calculate_score(m)

        return {
            "metrics": m.to_dict(),
            "advisor_score": score,
            "grade": self._grade(score),
        }

    def _calculate_score(self, m: AdvisorScoreMetrics) -> float:
        if m.total_reviews == 0:
            return 0.0

        acceptance_rate = m.accepted_reviews / m.total_reviews
        hallucination_penalty = min(m.hallucination_count * 5, 50)
        helpfulness = (
            m.helpful_reviews / max(m.helpful_reviews + m.misleading_reviews, 1)
        )
        engine_alignment = (
            m.agreement_with_decision_engine /
            max(m.agreement_with_decision_engine + m.disagreement_with_decision_engine, 1)
        )

        raw = (
            acceptance_rate * 30
            + helpfulness * 30
            + engine_alignment * 20
            + max(0, 20 - hallucination_penalty)
        )
        return round(min(100, max(0, raw)), 1)

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        if score >= 35:
            return "D"
        return "F"

    def record_helpful(self) -> None:
        self._metrics.helpful_reviews += 1

    def record_misleading(self) -> None:
        self._metrics.misleading_reviews += 1
