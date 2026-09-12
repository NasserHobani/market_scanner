# -*- coding: utf-8 -*-
"""Structured explainability — no natural language generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .confidence import ConfidenceBreakdown
from .contradiction import ContradictionReport
from .evidence import Evidence, EvidenceBundle, EvidenceDirection


@dataclass
class StructuredExplanation:
    """Machine-readable explanation for a recommendation review."""

    trade_strengths: list[str] = field(default_factory=list)
    trade_weaknesses: list[str] = field(default_factory=list)
    missing_confirmations: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    important_features: list[str] = field(default_factory=list)
    evidence_summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_strengths": list(self.trade_strengths),
            "trade_weaknesses": list(self.trade_weaknesses),
            "missing_confirmations": list(self.missing_confirmations),
            "risk_factors": list(self.risk_factors),
            "important_features": list(self.important_features),
            "evidence_summary": list(self.evidence_summary),
        }


class ExplainabilityEngine:
    """Builds structured explanations from evidence and contradictions."""

    def explain(self, bundle: EvidenceBundle, *,
                contradictions: ContradictionReport,
                confidence: ConfidenceBreakdown,
                tree_status: dict[str, Any] | None = None) -> StructuredExplanation:
        strengths = [e.label for e in bundle.supporting()]
        weaknesses = [e.label for e in bundle.contradicting()]
        missing = [e.label for e in bundle.missing()]

        for cx in contradictions.items:
            weaknesses.append(cx.summary)

        risk_factors = [
            e.label for e in bundle.by_category("risk")
            if e.direction == EvidenceDirection.CONTRADICTS.value
        ]
        if confidence.contradiction_penalty > 0.1:
            risk_factors.append(
                f"contradiction_penalty={confidence.contradiction_penalty:.2f}")

        important = sorted(
            bundle.items,
            key=lambda e: e.weight * e.confidence,
            reverse=True,
        )[:5]
        important_features = [e.raw_key or e.label for e in important if e.raw_key]

        missing_confirmations: list[str] = list(missing)
        if tree_status:
            for stage in tree_status.get("stages") or []:
                if stage.get("status") == "missing":
                    missing_confirmations.append(f"stage:{stage.get('stage')}")

        evidence_summary = [
            f"{e.category}:{e.direction}:{e.confidence:.2f}" for e in bundle.items
        ]

        return StructuredExplanation(
            trade_strengths=strengths,
            trade_weaknesses=weaknesses,
            missing_confirmations=missing_confirmations,
            risk_factors=risk_factors,
            important_features=important_features,
            evidence_summary=evidence_summary,
        )


class ExplainabilityProvider(ExplainabilityEngine):
    """Protocol-facing alias."""

    pass
