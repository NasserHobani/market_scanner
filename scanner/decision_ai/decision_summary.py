# -*- coding: utf-8 -*-
"""Structured decision summary — JSON only, no natural language AI."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DecisionSummary:
    """Structured AI decision support summary."""

    summary_id: str
    event_id: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    prediction: dict[str, Any] = field(default_factory=dict)
    historical_support: dict[str, Any] = field(default_factory=dict)
    research_support: dict[str, Any] = field(default_factory=dict)
    overall_confidence: float = 0.0
    confidence_breakdown: dict[str, Any] = field(default_factory=dict)
    missing_evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    guardrails: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "event_id": self.event_id,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "contradictions": list(self.contradictions),
            "prediction": dict(self.prediction),
            "historical_support": dict(self.historical_support),
            "research_support": dict(self.research_support),
            "overall_confidence": round(self.overall_confidence, 4),
            "confidence_breakdown": dict(self.confidence_breakdown),
            "missing_evidence": list(self.missing_evidence),
            "warnings": list(self.warnings),
            "guardrails": dict(self.guardrails),
            "generated_at": self.generated_at,
            "disclaimer": "Decision support only — not a trading recommendation",
        }


class DecisionSummaryBuilder:
    """Generate structured decision summaries from context + evidence."""

    def build(self, context: dict[str, Any], *,
              evidence: dict[str, Any] | None = None,
              fused_confidence: dict[str, Any] | None = None,
              guardrails: dict[str, Any] | None = None) -> DecisionSummary:
        ev_items = (evidence or {}).get("items") or []
        reasoning = context.get("reasoning") or {}
        similarity = context.get("similarity") or {}
        prediction = context.get("prediction") or {}
        research = context.get("research") or {}

        strengths = self._strengths(ev_items, reasoning)
        weaknesses = self._weaknesses(ev_items, reasoning, guardrails)
        contradictions = self._contradictions(reasoning, ev_items)

        return DecisionSummary(
            summary_id=f"dsum_{uuid.uuid4().hex[:16]}",
            event_id=context.get("event_id") or "",
            strengths=strengths,
            weaknesses=weaknesses,
            contradictions=contradictions,
            prediction={
                "available": bool(prediction),
                "signal": prediction.get("prediction"),
                "probability": prediction.get("probability"),
                "confidence": prediction.get("confidence"),
                "model_id": prediction.get("model_id"),
                "disclaimer": "analytical_signal_only",
            },
            historical_support={
                "available": similarity.get("available", False),
                "match_count": similarity.get("match_count"),
                "avg_win_rate": similarity.get("average_win_rate"),
                "avg_r": similarity.get("average_r"),
            },
            research_support={
                "available": bool(research),
                "conclusions": research.get("conclusions") or [],
                "warnings": research.get("warnings") or [],
                "limitations": research.get("limitations") or [],
            },
            overall_confidence=(fused_confidence or {}).get("overall", 0.0),
            confidence_breakdown=fused_confidence or {},
            missing_evidence=(guardrails or {}).get("missing_evidence") or
                             (evidence or {}).get("sources_missing") or [],
            warnings=self._collect_warnings(reasoning, guardrails),
            guardrails=guardrails or {},
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _strengths(items: list[dict], reasoning: dict) -> list[str]:
        out: list[str] = []
        for ev in items:
            if ev.get("direction") == "supports" and (ev.get("confidence") or 0) >= 0.5:
                out.append(f"[{ev.get('source')}] {ev.get('label')} (conf={ev.get('confidence')})")
        if reasoning.get("verdict") == "aligned":
            out.append("Reasoning verdict: aligned")
        return out[:10]

    @staticmethod
    def _weaknesses(items: list[dict], reasoning: dict,
                    guardrails: dict | None) -> list[str]:
        out: list[str] = []
        for ev in items:
            if ev.get("direction") == "contradicts":
                out.append(f"[{ev.get('source')}] {ev.get('label')} contradicts")
        if reasoning.get("verdict") == "misaligned":
            out.append("Reasoning verdict: misaligned")
        for v in (guardrails or {}).get("violations") or []:
            if isinstance(v, dict):
                out.append(v.get("message", ""))
        return [w for w in out if w][:10]

    @staticmethod
    def _contradictions(reasoning: dict, items: list[dict]) -> list[str]:
        out: list[str] = []
        cx = reasoning.get("contradictions") or {}
        if isinstance(cx, dict):
            for item in cx.get("items") or cx.get("contradictions") or []:
                if isinstance(item, dict):
                    out.append(item.get("description") or item.get("label") or str(item))
                else:
                    out.append(str(item))
        for ev in items:
            if ev.get("direction") == "contradicts":
                out.append(f"{ev.get('source')}: {ev.get('label')}")
        return out[:10]

    @staticmethod
    def _collect_warnings(reasoning: dict, guardrails: dict | None) -> list[str]:
        warnings = list(reasoning.get("warnings") or [])
        warnings.extend((guardrails or {}).get("warnings") or [])
        return warnings[:15]
