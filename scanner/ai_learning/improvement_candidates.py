# -*- coding: utf-8 -*-
"""Improvement candidates — ranked by impact, confidence, evidence, sample, risk."""
from __future__ import annotations

from typing import Any

RANKING_VERSION = "1.0.0"

RISK_WEIGHTS = {
    "advisor_accuracy_drop": 0.3,
    "repeated_hallucination": 0.4,
    "timeframe_specific_failure": 0.5,
    "strategy_specific_failure": 0.6,
    "similarity_below_threshold": 0.4,
    "research_disagreement": 0.3,
    "prediction_overconfidence": 0.5,
    "low_liquidity_failure": 0.7,
    "wrong_agreement": 0.4,
    "missed_warning": 0.5,
    "hallucination": 0.4,
    "success_cluster": 0.1,
}


class ImprovementCandidates:
    """Rank possible improvements. Highest score first."""

    def rank(self, *,
             lessons: list[dict[str, Any]],
             proposals: list[dict[str, Any]] | None = None,
             hypotheses: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        for lesson in lessons:
            candidates.append(self._score_lesson(lesson))

        for proposal in (proposals or []):
            candidates.append(self._score_proposal(proposal))

        for hypothesis in (hypotheses or []):
            candidates.append(self._score_hypothesis(hypothesis))

        candidates.sort(key=lambda x: x["composite_score"], reverse=True)
        for i, c in enumerate(candidates, 1):
            c["rank"] = i
        return candidates

    def _score_lesson(self, lesson: dict[str, Any]) -> dict[str, Any]:
        ptype = lesson.get("pattern_type", "unknown")
        impact = self._impact_score(ptype, lesson.get("sample_size", 0))
        confidence = (lesson.get("confidence") or 0) / 100
        evidence = min(1.0, len(lesson.get("supporting_evidence", [])) / 5)
        sample = min(1.0, (lesson.get("sample_size") or 0) / 10)
        risk = RISK_WEIGHTS.get(ptype, 0.5)

        composite = (
            impact * 0.30
            + confidence * 0.25
            + evidence * 0.20
            + sample * 0.15
            + (1 - risk) * 0.10
        )

        return {
            "candidate_id": lesson.get("lesson_id", ""),
            "candidate_type": "lesson",
            "title": lesson.get("title", ""),
            "pattern_type": ptype,
            "impact": round(impact * 100, 1),
            "confidence": lesson.get("confidence", 0),
            "evidence_count": len(lesson.get("supporting_evidence", [])),
            "sample_size": lesson.get("sample_size", 0),
            "risk": round(risk * 100, 1),
            "composite_score": round(composite * 100, 1),
            "ranking_version": RANKING_VERSION,
        }

    def _score_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        confidence = (proposal.get("confidence") or 0) / 100
        evidence = min(1.0, len(proposal.get("supporting_lessons", [])) / 3)
        impact = 0.7
        sample = evidence
        risk = 0.4

        composite = impact * 0.30 + confidence * 0.25 + evidence * 0.20 + sample * 0.15 + (1 - risk) * 0.10

        return {
            "candidate_id": proposal.get("proposal_id", ""),
            "candidate_type": "proposal",
            "title": proposal.get("title", ""),
            "pattern_type": proposal.get("affected_module", ""),
            "impact": round(impact * 100, 1),
            "confidence": proposal.get("confidence", 0),
            "evidence_count": len(proposal.get("supporting_lessons", [])),
            "sample_size": len(proposal.get("supporting_lessons", [])),
            "risk": round(risk * 100, 1),
            "composite_score": round(composite * 100, 1),
            "ranking_version": RANKING_VERSION,
        }

    def _score_hypothesis(self, hypothesis: dict[str, Any]) -> dict[str, Any]:
        confidence = (hypothesis.get("confidence") or 0) / 100
        evidence = min(1.0, len(hypothesis.get("supporting_evidence", [])) / 5)
        sample = min(1.0, (hypothesis.get("sample_size") or 0) / 10)
        ptype = hypothesis.get("pattern_type", "unknown")
        impact = self._impact_score(ptype, hypothesis.get("sample_size", 0))
        risk = RISK_WEIGHTS.get(ptype, 0.5)

        composite = impact * 0.30 + confidence * 0.25 + evidence * 0.20 + sample * 0.15 + (1 - risk) * 0.10

        return {
            "candidate_id": hypothesis.get("hypothesis_id", ""),
            "candidate_type": "hypothesis",
            "title": hypothesis.get("statement", ""),
            "pattern_type": ptype,
            "impact": round(impact * 100, 1),
            "confidence": hypothesis.get("confidence", 0),
            "evidence_count": len(hypothesis.get("supporting_evidence", [])),
            "sample_size": hypothesis.get("sample_size", 0),
            "risk": round(risk * 100, 1),
            "composite_score": round(composite * 100, 1),
            "ranking_version": RANKING_VERSION,
        }

    @staticmethod
    def _impact_score(pattern_type: str, sample_size: int) -> float:
        base_impacts = {
            "advisor_accuracy_drop": 0.8,
            "repeated_hallucination": 0.9,
            "strategy_specific_failure": 0.85,
            "low_liquidity_failure": 0.75,
            "prediction_overconfidence": 0.7,
            "timeframe_specific_failure": 0.65,
            "similarity_below_threshold": 0.6,
            "success_cluster": 0.3,
        }
        base = base_impacts.get(pattern_type, 0.5)
        sample_boost = min(0.2, sample_size * 0.02)
        return min(1.0, base + sample_boost)
