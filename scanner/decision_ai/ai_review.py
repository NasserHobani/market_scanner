# -*- coding: utf-8 -*-
"""AI review — structured reviewer output, no LLM invocation."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .decision_summary import DecisionSummary
from .prompt_builder import StructuredPrompt


@dataclass
class AIReview:
    """Structured AI review — reviewer role, not trading engine."""

    review_id: str
    review_type: str
    event_id: str
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    prompt: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, Any] = field(default_factory=dict)
    guardrails: dict[str, Any] = field(default_factory=dict)
    status: str = "completed"
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "review_type": self.review_type,
            "event_id": self.event_id,
            "context_snapshot": self.context_snapshot,
            "evidence": self.evidence,
            "prompt": self.prompt,
            "summary": self.summary,
            "confidence": self.confidence,
            "guardrails": self.guardrails,
            "status": self.status,
            "generated_at": self.generated_at,
            "role": "reviewer",
            "disclaimer": "AI review for decision support only — not a trading recommendation",
            "llm_invoked": False,
        }


class AIReviewEngine:
    """Produce structured AI reviews without invoking LLM providers."""

    def review(self, review_type: str, context: dict[str, Any], *,
               evidence: dict[str, Any] | None = None,
               prompt: StructuredPrompt | None = None,
               summary: DecisionSummary | None = None,
               confidence: dict[str, Any] | None = None,
               guardrails: dict[str, Any] | None = None) -> AIReview:
        return AIReview(
            review_id=f"airev_{uuid.uuid4().hex[:16]}",
            review_type=review_type,
            event_id=context.get("event_id") or "",
            context_snapshot={
                "event_id": context.get("event_id"),
                "symbol": context.get("symbol"),
                "market": context.get("market"),
                "timeframe": context.get("timeframe"),
                "schema_version": context.get("schema_version"),
            },
            evidence=evidence or {},
            prompt=prompt.to_dict() if prompt else {},
            summary=summary.to_dict() if summary else {},
            confidence=confidence or {},
            guardrails=guardrails or {},
            status="completed",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
