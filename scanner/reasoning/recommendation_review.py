# -*- coding: utf-8 -*-
"""Review existing recommendations — never generate new ones."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .confidence import ConfidenceBreakdown
from .contradiction import ContradictionReport
from .decision_tree import DecisionTreeResult
from .evidence import EvidenceBundle
from .explainability import StructuredExplanation


@dataclass
class RecommendationReview:
    """Structured review output — agreement with evidence, not a new signal."""

    event_id: str
    recommendation_id: str
    action: str
    direction: str
    agreement_score: float
    engine_confidence: float
    recommendation_confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    contradictions: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, Any] = field(default_factory=dict)
    explanation: dict[str, Any] = field(default_factory=dict)
    decision_tree: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    verdict: str = "reviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "recommendation_id": self.recommendation_id,
            "action": self.action,
            "direction": self.direction,
            "agreement_score": round(self.agreement_score, 4),
            "agreement_pct": round(self.agreement_score * 100, 1),
            "engine_confidence": round(self.engine_confidence, 4),
            "recommendation_confidence": round(self.recommendation_confidence, 4),
            "evidence": self.evidence,
            "contradictions": self.contradictions,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "decision_tree": self.decision_tree,
            "warnings": list(self.warnings),
            "missing_information": list(self.missing_information),
            "verdict": self.verdict,
        }


def _agreement_score(bundle: EvidenceBundle, engine_conf: float,
                     reco_conf: float, contradiction_count: int) -> float:
    sup = len(bundle.supporting())
    con = len(bundle.contradicting())
    total = sup + con or 1
    evidence_ratio = sup / total
    score = 0.5 * evidence_ratio + 0.35 * engine_conf + 0.15 * reco_conf
    score -= min(0.25, contradiction_count * 0.06)
    return max(0.0, min(1.0, score))


class RecommendationReviewer:
    """Reviews recommendation snapshot against reasoning evidence."""

    def review(self, context: dict[str, Any], *,
               bundle: EvidenceBundle,
               contradictions: ContradictionReport,
               confidence: ConfidenceBreakdown,
               explanation: StructuredExplanation,
               tree: DecisionTreeResult) -> RecommendationReview:
        reco = context.get("recommendation_snapshot") or {}
        event_id = context.get("event_id") or bundle.event_id
        reco_id = reco.get("snapshot_id") or ""
        action = reco.get("action") or "none"
        direction = reco.get("direction") or reco.get("side") or "—"
        reco_conf = float(reco.get("confidence") or 0.0)

        warnings: list[str] = list(reco.get("warnings") or [])
        missing: list[str] = list(explanation.missing_confirmations)

        if action == "none":
            warnings.append("recommendation_action_is_none")
        if not context.get("feature_snapshot"):
            missing.append("feature_snapshot")
        if not context.get("market_snapshot"):
            missing.append("market_snapshot")

        for cx in contradictions.items:
            if cx.severity == "high":
                warnings.append(cx.summary)

        if confidence.overall < 0.45:
            warnings.append("low_engine_confidence")
        if not tree.completed:
            warnings.append(f"decision_tree_halted_at:{tree.halted_at}")

        agreement = _agreement_score(
            bundle, confidence.overall, reco_conf, len(contradictions.items))

        verdict = "aligned"
        if agreement < 0.45 or len(contradictions.items) >= 2:
            verdict = "caution"
        if agreement < 0.30 or (action in ("now", "pending") and confidence.overall < 0.35):
            verdict = "misaligned"

        return RecommendationReview(
            event_id=event_id,
            recommendation_id=reco_id,
            action=action,
            direction=direction,
            agreement_score=agreement,
            engine_confidence=confidence.overall,
            recommendation_confidence=reco_conf,
            evidence=bundle.to_dict(),
            contradictions=contradictions.to_dict(),
            confidence=confidence.to_dict(),
            explanation=explanation.to_dict(),
            decision_tree=tree.to_dict(),
            warnings=warnings,
            missing_information=missing,
            verdict=verdict,
        )
