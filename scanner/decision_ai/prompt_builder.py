# -*- coding: utf-8 -*-
"""Structured prompt templates — no free-form generation, no LLM calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .context_builder import DECISION_AI_VERSION


class PromptType(str, Enum):
    MARKET_REVIEW = "market_review"
    TRADE_REVIEW = "trade_review"
    RISK_REVIEW = "risk_review"
    RESEARCH_REVIEW = "research_review"
    PREDICTION_REVIEW = "prediction_review"


TEMPLATES: dict[str, str] = {
    PromptType.MARKET_REVIEW.value: """\
# Market Review — Structured Analysis Request

## Context
- Event ID: {event_id}
- Symbol: {symbol}
- Market: {market}
- Timeframe: {timeframe}

## Market Snapshot
{market_snapshot}

## Market Environment
{market_environment}

## Strategy Statistics
{strategy_statistics}

## Evidence Summary
{evidence_summary}

## Confidence
{confidence_summary}

## Instructions
Review the market context. Identify strengths, weaknesses, and missing data.
Do NOT generate buy/sell recommendations. Report uncertainty where evidence is insufficient.
""",

    PromptType.TRADE_REVIEW.value: """\
# Trade Review — Structured Analysis Request

## Context
- Event ID: {event_id}
- Symbol: {symbol}
- Action: {action}
- Direction: {direction}

## Recommendation
{recommendation_snapshot}

## Reasoning Verdict
{reasoning_verdict}

## Evidence ({evidence_count} items)
{evidence_summary}

## Similarity
{similarity_summary}

## Prediction Signal
{prediction_summary}

## Warnings
{warnings}

## Instructions
Review the trade setup. Assess alignment between evidence layers.
Do NOT generate buy/sell recommendations. Report contradictions and missing evidence.
""",

    PromptType.RISK_REVIEW.value: """\
# Risk Review — Structured Analysis Request

## Context
- Event ID: {event_id}
- Symbol: {symbol}

## Risk Evidence
{risk_evidence}

## Contradictions
{contradictions}

## Guardrail Warnings
{guardrail_warnings}

## Strategy Statistics
{strategy_statistics}

## Instructions
Assess risk factors. Identify guardrail violations and uncertainty.
Do NOT generate buy/sell recommendations.
""",

    PromptType.RESEARCH_REVIEW.value: """\
# Research Review — Structured Analysis Request

## Context
- Event ID: {event_id}

## Research Report
{research_summary}

## Hypothesis
{hypothesis}

## Metrics
{metrics}

## Limitations
{limitations}

## Instructions
Evaluate research support for the current decision context.
Report sample size concerns and statistical limitations.
""",

    PromptType.PREDICTION_REVIEW.value: """\
# Prediction Review — Structured Analysis Request

## Context
- Event ID: {event_id}

## Model Prediction
{prediction_summary}

## Feature Explainability
{explainability}

## Feature Intelligence
{feature_intelligence_summary}

## Disclaimer
Prediction is an analytical signal only — not a trading recommendation.

## Instructions
Assess model prediction quality. Report confidence level and feature drift concerns.
Do NOT generate buy/sell recommendations.
""",
}


@dataclass
class StructuredPrompt:
    """Built prompt from template — ready for future LLM integration."""

    prompt_type: str
    event_id: str
    template_version: str = DECISION_AI_VERSION
    content: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_type": self.prompt_type,
            "event_id": self.event_id,
            "template_version": self.template_version,
            "content": self.content,
            "sections": dict(self.sections),
            "metadata": dict(self.metadata),
            "llm_ready": False,
            "note": "Template only — no LLM provider invoked",
        }


class PromptBuilder:
    """Build structured prompts from templates only."""

    def build(self, prompt_type: str, context: dict[str, Any], *,
              evidence: dict[str, Any] | None = None,
              guardrails: dict[str, Any] | None = None) -> StructuredPrompt:
        template = TEMPLATES.get(prompt_type)
        if not template:
            raise ValueError(f"Unknown prompt type: {prompt_type}")

        sections = self._build_sections(prompt_type, context, evidence, guardrails)
        content = template.format(**sections)

        return StructuredPrompt(
            prompt_type=prompt_type,
            event_id=context.get("event_id") or "",
            content=content,
            sections=sections,
            metadata={"template": prompt_type, "section_count": len(sections)},
        )

    def available_types(self) -> list[str]:
        return list(TEMPLATES.keys())

    def _build_sections(self, prompt_type: str, context: dict[str, Any],
                        evidence: dict[str, Any] | None,
                        guardrails: dict[str, Any] | None) -> dict[str, str]:
        knowledge = context.get("knowledge") or {}
        reasoning = context.get("reasoning") or {}
        similarity = context.get("similarity") or {}
        prediction = context.get("prediction") or {}
        research = context.get("research") or {}
        fi = context.get("feature_intelligence") or {}

        ev_items = (evidence or {}).get("items") or []
        ev_summary = "\n".join(
            f"- [{e.get('source')}] {e.get('label')}: {e.get('direction')} "
            f"(conf={e.get('confidence')})"
            for e in ev_items[:20]
        ) or "No evidence available"

        base = {
            "event_id": context.get("event_id") or "",
            "symbol": context.get("symbol") or "",
            "market": context.get("market") or "",
            "timeframe": context.get("timeframe") or "",
            "market_snapshot": self._fmt(knowledge.get("market_snapshot")),
            "market_environment": self._fmt(knowledge.get("market_environment")),
            "strategy_statistics": self._fmt(context.get("strategy_statistics")),
            "evidence_summary": ev_summary,
            "evidence_count": str(len(ev_items)),
            "confidence_summary": self._fmt(reasoning.get("confidence")),
            "recommendation_snapshot": self._fmt(knowledge.get("recommendation_snapshot")),
            "action": reasoning.get("action") or "",
            "direction": reasoning.get("direction") or "",
            "reasoning_verdict": reasoning.get("verdict") or "unknown",
            "similarity_summary": self._fmt(similarity),
            "prediction_summary": self._fmt(prediction),
            "warnings": "\n".join(f"- {w}" for w in reasoning.get("warnings") or []) or "None",
            "risk_evidence": ev_summary,
            "contradictions": self._fmt(reasoning.get("contradictions")),
            "guardrail_warnings": self._fmt(guardrails),
            "research_summary": self._fmt(research),
            "hypothesis": self._fmt(research.get("methodology", {}).get("hypothesis")
                                    if isinstance(research.get("methodology"), dict) else None),
            "metrics": self._fmt(research.get("metrics")),
            "limitations": "\n".join(f"- {l}" for l in research.get("limitations") or []) or "None",
            "explainability": self._fmt(prediction.get("explainability")),
            "feature_intelligence_summary": self._fmt(fi),
        }
        return base

    @staticmethod
    def _fmt(obj: Any) -> str:
        if obj is None:
            return "N/A"
        if isinstance(obj, dict):
            lines = [f"  {k}: {v}" for k, v in list(obj.items())[:15]]
            return "\n".join(lines) if lines else "N/A"
        if isinstance(obj, (list, tuple)):
            return "\n".join(f"  - {item}" for item in obj[:10]) or "N/A"
        return str(obj)
