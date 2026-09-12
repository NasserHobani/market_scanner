# -*- coding: utf-8 -*-
"""Knowledge proposals — advisory only, never modifies Knowledge."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

PROPOSAL_VERSION = "1.0.0"

PATTERN_TO_MODULE = {
    "advisor_accuracy_drop": "ai_advisor",
    "repeated_hallucination": "ai_advisor",
    "timeframe_specific_failure": "decision",
    "strategy_specific_failure": "optimization",
    "similarity_below_threshold": "similarity",
    "research_disagreement": "research",
    "prediction_overconfidence": "prediction",
    "low_liquidity_failure": "knowledge",
    "wrong_agreement": "ai_advisor",
    "missed_warning": "ai_advisor",
    "hallucination": "ai_advisor",
    "false_warning": "ai_advisor",
    "partial_on_loss": "ai_advisor",
    "partial_on_win": "ai_advisor",
    "incorrect_disagreement": "ai_advisor",
    "correct_disagreement": "ai_advisor",
    "high_confidence_wrong": "ai_advisor",
    "low_confidence_wrong": "ai_advisor",
    "other_failure": "ai_advisor",
    "success_cluster": "knowledge",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KnowledgeProposals:
    """Generate knowledge proposals from lessons. Never writes to Knowledge."""

    def generate(self, lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        proposals = []
        for lesson in lessons:
            if lesson.get("status") == "REJECTED":
                continue
            proposal = self._from_lesson(lesson)
            if proposal:
                proposals.append(proposal)
        return proposals

    def _from_lesson(self, lesson: dict[str, Any]) -> dict[str, Any] | None:
        pattern_type = lesson.get("pattern_type", "")
        module = PATTERN_TO_MODULE.get(pattern_type, "knowledge")
        sample = lesson.get("sample_size", 0)
        strength = lesson.get("recommendation_strength", "")
        if sample < 2 or strength == "insufficient":
            return None

        return {
            "proposal_id": f"prop_{uuid.uuid4().hex[:16]}",
            "reason": lesson.get("description", ""),
            "supporting_lessons": [lesson.get("lesson_id", "")],
            "expected_benefit": self._expected_benefit(pattern_type, sample),
            "confidence": lesson.get("confidence", 0),
            "affected_module": module,
            "required_experiment": self._required_experiment(pattern_type, lesson),
            "title": f"Knowledge update proposal: {lesson.get('title', '')}",
            "status": "NEW",
            "created_at": _now(),
            "proposal_version": PROPOSAL_VERSION,
        }

    @staticmethod
    def _expected_benefit(pattern_type: str, sample_size: int) -> str:
        benefits = {
            "advisor_accuracy_drop": "Improve advisor accuracy by refining prompts or provider selection",
            "repeated_hallucination": "Reduce hallucination rate through stricter grounding",
            "timeframe_specific_failure": "Adjust decision rules for specific timeframes",
            "strategy_specific_failure": "Review or disable underperforming strategy conditions",
            "similarity_below_threshold": "Increase similarity threshold for better match quality",
            "research_disagreement": "Align research parameters with platform decisions",
            "prediction_overconfidence": "Recalibrate prediction confidence thresholds",
            "low_liquidity_failure": "Add liquidity filters to knowledge base",
            "success_cluster": "Document and reinforce successful market patterns",
        }
        base = benefits.get(pattern_type, "General platform improvement")
        return f"{base} (based on {sample_size} observations)"

    @staticmethod
    def _required_experiment(pattern_type: str, lesson: dict[str, Any]) -> str:
        experiments = {
            "advisor_accuracy_drop": "A/B test advisor prompt versions on recent decision packages",
            "repeated_hallucination": "Run grounding validation audit on last 50 reviews",
            "timeframe_specific_failure": f"Backtest decision rules on {lesson.get('affected_timeframes', ['target'])[0] if lesson.get('affected_timeframes') else 'target'} timeframe",
            "strategy_specific_failure": f"Research experiment on {lesson.get('affected_strategies', ['target'])[0] if lesson.get('affected_strategies') else 'target'} strategy",
            "similarity_below_threshold": "Increase similarity threshold and measure match quality",
            "prediction_overconfidence": "Recalibrate confidence buckets and measure accuracy",
            "low_liquidity_failure": "Add minimum liquidity filter and backtest impact",
        }
        return experiments.get(pattern_type, "General research validation experiment")
