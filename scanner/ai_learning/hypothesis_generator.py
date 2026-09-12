# -*- coding: utf-8 -*-
"""Hypothesis generator — research hypotheses, never executes experiments."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

HYPOTHESIS_VERSION = "1.0.0"

HYPOTHESIS_TEMPLATES = {
    "advisor_accuracy_drop": "Switch to higher-accuracy provider for {scope} trades",
    "repeated_hallucination": "Tighten evidence grounding validation in advisor prompts",
    "timeframe_specific_failure": "Increase minimum confidence for {timeframe} timeframe entries",
    "strategy_specific_failure": "Disable {strategy} strategy under current market conditions",
    "similarity_below_threshold": "Increase Similarity threshold from current to 0.6+",
    "research_disagreement": "Align research baseline with current decision engine parameters",
    "prediction_overconfidence": "Increase minimum prediction confidence to 0.75",
    "low_liquidity_failure": "Reduce position size during low liquidity periods",
    "wrong_agreement": "Require contradicting evidence review before agreeing with platform",
    "missed_warning": "Enhance risk detection prompts for advisor reviews",
    "hallucination": "Reject reviews with any ungrounded evidence citations",
    "success_cluster": "Document and replicate successful patterns for {market}",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HypothesisGenerator:
    """Generate research hypotheses from lessons and patterns. Does NOT execute."""

    def generate(self, lessons: list[dict[str, Any]],
                 patterns: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        hypotheses = []
        seen_types: set[str] = set()

        for lesson in lessons:
            ptype = lesson.get("pattern_type", "")
            if ptype in seen_types:
                continue
            seen_types.add(ptype)
            hyp = self._from_lesson(lesson)
            if hyp:
                hypotheses.append(hyp)

        for pattern in (patterns or []):
            ptype = pattern.get("pattern_type", "")
            if ptype in seen_types:
                continue
            seen_types.add(ptype)
            hyp = self._from_pattern(pattern)
            if hyp:
                hypotheses.append(hyp)

        return hypotheses

    def _from_lesson(self, lesson: dict[str, Any]) -> dict[str, Any] | None:
        ptype = lesson.get("pattern_type", "")
        template = HYPOTHESIS_TEMPLATES.get(ptype)
        if not template:
            return None

        scope = self._format_scope(lesson)
        statement = template.format(
            scope=scope,
            timeframe=lesson.get("affected_timeframes", ["unknown"])[0] if lesson.get("affected_timeframes") else "unknown",
            strategy=lesson.get("affected_strategies", ["unknown"])[0] if lesson.get("affected_strategies") else "unknown",
            market=lesson.get("affected_markets", ["unknown"])[0] if lesson.get("affected_markets") else "unknown",
        )

        return {
            "hypothesis_id": f"hyp_{uuid.uuid4().hex[:16]}",
            "statement": statement,
            "pattern_type": ptype,
            "supporting_lessons": [lesson.get("lesson_id", "")],
            "supporting_evidence": lesson.get("supporting_evidence", []),
            "sample_size": lesson.get("sample_size", 0),
            "confidence": lesson.get("confidence", 0),
            "expected_outcome": self._expected_outcome(ptype),
            "status": "NEW",
            "created_at": _now(),
            "hypothesis_version": HYPOTHESIS_VERSION,
        }

    def _from_pattern(self, pattern: dict[str, Any]) -> dict[str, Any] | None:
        ptype = pattern.get("pattern_type", "")
        template = HYPOTHESIS_TEMPLATES.get(ptype)
        if not template:
            return None

        return {
            "hypothesis_id": f"hyp_{uuid.uuid4().hex[:16]}",
            "statement": template.format(
                scope="affected scope",
                timeframe=pattern.get("affected_timeframes", ["unknown"])[0] if pattern.get("affected_timeframes") else "unknown",
                strategy=pattern.get("affected_strategies", ["unknown"])[0] if pattern.get("affected_strategies") else "unknown",
                market=pattern.get("affected_markets", ["unknown"])[0] if pattern.get("affected_markets") else "unknown",
            ),
            "pattern_type": ptype,
            "supporting_lessons": [],
            "supporting_evidence": pattern.get("supporting_evidence", []),
            "sample_size": pattern.get("sample_size", 0),
            "confidence": pattern.get("confidence", 0),
            "expected_outcome": self._expected_outcome(ptype),
            "status": "NEW",
            "created_at": _now(),
            "hypothesis_version": HYPOTHESIS_VERSION,
        }

    @staticmethod
    def _format_scope(lesson: dict[str, Any]) -> str:
        parts = []
        if lesson.get("affected_markets"):
            parts.append(lesson["affected_markets"][0])
        if lesson.get("affected_providers"):
            parts.append(lesson["affected_providers"][0])
        return " / ".join(parts) if parts else "general"

    @staticmethod
    def _expected_outcome(pattern_type: str) -> str:
        outcomes = {
            "advisor_accuracy_drop": "Advisor accuracy improves by ≥10%",
            "repeated_hallucination": "Hallucination rate drops below 5%",
            "timeframe_specific_failure": "Failure rate on target timeframe drops below 40%",
            "strategy_specific_failure": "Strategy expectancy improves or strategy is disabled",
            "similarity_below_threshold": "Match quality improves with higher threshold",
            "prediction_overconfidence": "Calibration error reduces in high-confidence buckets",
            "low_liquidity_failure": "Losses during low liquidity decrease",
            "success_cluster": "Success rate maintained or improved in target market",
        }
        return outcomes.get(pattern_type, "Measurable improvement in target metric")
