# -*- coding: utf-8 -*-
"""Advisor review — structured output from LLM shadow review."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .decision_package import DecisionPackage
from .unified_package import UnifiedDecisionPackage
from .prompt_builder import AdvisorPrompt


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceCitation:
    evidence_id: str
    section: str
    field: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "section": self.section,
            "field": self.field,
            "note": self.note,
        }


@dataclass
class SuggestedExperiment:
    hypothesis: str = ""
    method: str = ""
    expected_outcome: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis": self.hypothesis,
            "method": self.method,
            "expected_outcome": self.expected_outcome,
        }


@dataclass
class AdvisorReview:
    """Complete advisor review result — shadow mode only."""

    review_id: str
    package_id: str
    event_id: str
    provider_id: str
    model_name: str
    prompt_version: str
    agreement: str
    confidence: float
    summary: str
    reasoning: str
    supporting_evidence: list[EvidenceCitation] = field(default_factory=list)
    contradicting_evidence: list[EvidenceCitation] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    suggested_experiment: SuggestedExperiment | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    status: str = "completed"
    accepted: bool = False
    shadow_mode: bool = True
    generated_at: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raw = dict(self.raw_response or {})
        analyst = {}
        try:
            from scanner.ai_advisor.analyst.normalize import extract_analyst_fields
            analyst = extract_analyst_fields(raw)
        except Exception:  # noqa: BLE001
            analyst = {}
        return {
            "review_id": self.review_id,
            "package_id": self.package_id,
            "event_id": self.event_id,
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "agreement": self.agreement,
            "confidence": self.confidence,
            "summary": self.summary,
            "reasoning": self.reasoning,
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contradicting_evidence": [e.to_dict() for e in self.contradicting_evidence],
            "risks": list(self.risks),
            "missing_information": list(self.missing_information),
            "suggested_experiment": (
                self.suggested_experiment.to_dict() if self.suggested_experiment else None
            ),
            "validation": dict(self.validation),
            "status": self.status,
            "accepted": self.accepted,
            "shadow_mode": self.shadow_mode,
            "generated_at": self.generated_at or _now(),
            "role": "advisor",
            "disclaimer": "AI advisor review — shadow mode, does not change platform decisions",
            "llm_invoked": True,
            "raw_response": raw,
            # AIA-13 optional analyst fields (presentation / evaluation)
            "language": analyst.get("language") or raw.get("language") or "ar",
            "recommendation_advice": analyst.get("recommendation") or {},
            "current_market_view": analyst.get("current_market_view") or {},
            "near_term_outlook": analyst.get("near_term_outlook") or {},
            "what_to_watch": analyst.get("what_to_watch") or [],
            "invalidation_conditions": analyst.get("invalidation_conditions") or [],
            "statistical_prediction": analyst.get("statistical_prediction") or {},
            "advisor_assessment": analyst.get("advisor_assessment") or {},
            "actionable_advice": analyst.get("actionable_advice") or "",
            "data_quality_note": analyst.get("data_quality_note") or "",
            "positive_signals": analyst.get("positive_signals") or [],
            "negative_signals": analyst.get("negative_signals") or [],
        }

    def to_ui_model(self) -> dict[str, Any]:
        """Presentation model for the UI — no chat, no raw JSON."""
        return {
            "review_id": self.review_id,
            "agreement": self.agreement,
            "confidence": self.confidence,
            "summary": self.summary,
            "reasoning": self.reasoning,
            "evidence": {
                "supporting": [e.to_dict() for e in self.supporting_evidence],
                "contradicting": [e.to_dict() for e in self.contradicting_evidence],
            },
            "risks": list(self.risks),
            "missing_information": list(self.missing_information),
            "suggested_experiment": (
                self.suggested_experiment.to_dict() if self.suggested_experiment else None
            ),
            "provider": self.provider_id,
            "model": self.model_name,
            "status": self.status,
            "accepted": self.accepted,
            "shadow_mode": self.shadow_mode,
        }


class ReviewEngine:
    """Assemble an AdvisorReview from validated parsed response."""

    def build(self, *,
              package: DecisionPackage | UnifiedDecisionPackage,
              prompt: AdvisorPrompt,
              provider_id: str,
              model_name: str,
              parsed: dict[str, Any],
              validation: dict[str, Any],
              raw_response: dict[str, Any] | None = None) -> AdvisorReview:
        accepted = validation.get("valid", False) and not validation.get("rejected", False)

        return AdvisorReview(
            review_id=f"adv_{uuid.uuid4().hex[:16]}",
            package_id=package.package_id,
            event_id=package.event_id,
            provider_id=provider_id,
            model_name=model_name,
            prompt_version=prompt.version,
            agreement=str(parsed.get("agreement", "partial")),
            confidence=float(parsed.get("confidence", 0)),
            summary=str(parsed.get("summary", "")),
            reasoning=str(parsed.get("reasoning", "")),
            supporting_evidence=self._citations(parsed.get("supporting_evidence")),
            contradicting_evidence=self._citations(parsed.get("contradicting_evidence")),
            risks=list(parsed.get("risks") or []),
            missing_information=list(parsed.get("missing_information") or []),
            suggested_experiment=self._experiment(parsed.get("suggested_experiment")),
            validation=validation,
            status="accepted" if accepted else "rejected",
            accepted=accepted,
            shadow_mode=True,
            generated_at=_now(),
            raw_response=raw_response or parsed,
        )

    @staticmethod
    def _citations(items: Any) -> list[EvidenceCitation]:
        if not isinstance(items, list):
            return []
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(EvidenceCitation(
                evidence_id=str(item.get("evidence_id", "")),
                section=str(item.get("section", "")),
                field=str(item.get("field", "")),
                note=str(item.get("note", "")),
            ))
        return out

    @staticmethod
    def _experiment(data: Any) -> SuggestedExperiment | None:
        if not isinstance(data, dict):
            return None
        return SuggestedExperiment(
            hypothesis=str(data.get("hypothesis", "")),
            method=str(data.get("method", "")),
            expected_outcome=str(data.get("expected_outcome", "")),
        )
