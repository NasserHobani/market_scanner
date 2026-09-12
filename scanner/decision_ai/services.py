# -*- coding: utf-8 -*-
"""Public Decision AI service API."""
from __future__ import annotations

from typing import Any

from .ai_review import AIReview, AIReviewEngine
from .confidence_fusion import ConfidenceFusion, FUSION_WEIGHTS
from .context_builder import ContextBuilder, DecisionAIContext
from .decision_summary import DecisionSummary, DecisionSummaryBuilder
from .evidence_builder import EvidenceBuilder
from .guardrails import Guardrails
from .prompt_builder import PromptBuilder, PromptType, StructuredPrompt


class DecisionAIService:
    """Public facade for AI decision support.

    Structured reasoning only — no LLM calls, no chat, no buy/sell.
    The AI is a reviewer, never the trading engine.
    """

    def __init__(self,
                 context_builder: ContextBuilder | None = None,
                 evidence_builder: EvidenceBuilder | None = None,
                 prompt_builder: PromptBuilder | None = None,
                 confidence_fusion: ConfidenceFusion | None = None,
                 guardrails: Guardrails | None = None,
                 summary_builder: DecisionSummaryBuilder | None = None,
                 review_engine: AIReviewEngine | None = None) -> None:
        self._context = context_builder or ContextBuilder()
        self._evidence = evidence_builder or EvidenceBuilder()
        self._prompts = prompt_builder or PromptBuilder()
        self._fusion = confidence_fusion or ConfidenceFusion()
        self._guardrails = guardrails or Guardrails()
        self._summary = summary_builder or DecisionSummaryBuilder()
        self._review = review_engine or AIReviewEngine()

    def build_context(self, *,
                      event_id: str,
                      knowledge_context: dict[str, Any] | None = None,
                      reasoning_review: dict[str, Any] | None = None,
                      similarity_context: dict[str, Any] | None = None,
                      research_report: dict[str, Any] | None = None,
                      feature_analysis: dict[str, Any] | None = None,
                      prediction: dict[str, Any] | None = None,
                      intelligence_report: dict[str, Any] | None = None,
                      strategy_statistics: dict[str, Any] | None = None,
                      memory_gaps: list[str] | None = None) -> DecisionAIContext:
        """Collect all layer information into one immutable context."""
        return self._context.build(
            event_id=event_id,
            knowledge_context=knowledge_context,
            reasoning_review=reasoning_review,
            similarity_context=similarity_context,
            research_report=research_report,
            feature_analysis=feature_analysis,
            prediction=prediction,
            intelligence_report=intelligence_report,
            strategy_statistics=strategy_statistics,
            memory_gaps=memory_gaps,
        )

    def build_prompt(self, prompt_type: str,
                     context: DecisionAIContext | dict[str, Any]) -> StructuredPrompt:
        """Build structured prompt from template."""
        ctx = context.to_dict() if isinstance(context, DecisionAIContext) else context
        evidence = self._evidence.build(ctx).to_dict()
        guardrail_report = self._guardrails.validate(ctx, evidence=evidence)
        return self._prompts.build(
            prompt_type, ctx,
            evidence=evidence,
            guardrails=guardrail_report.to_dict(),
        )

    def decision_summary(self, context: DecisionAIContext | dict[str, Any]) -> DecisionSummary:
        """Generate structured decision summary (JSON only)."""
        ctx = context.to_dict() if isinstance(context, DecisionAIContext) else context
        evidence = self._evidence.build(ctx).to_dict()
        fused = self._fusion.fuse(ctx).to_dict()
        guardrail_report = self._guardrails.validate(ctx, evidence=evidence).to_dict()
        return self._summary.build(
            ctx, evidence=evidence,
            fused_confidence=fused,
            guardrails=guardrail_report,
        )

    def review_trade(self, *,
                     event_id: str,
                     knowledge_context: dict[str, Any] | None = None,
                     reasoning_review: dict[str, Any] | None = None,
                     similarity_context: dict[str, Any] | None = None,
                     prediction: dict[str, Any] | None = None,
                     research_report: dict[str, Any] | None = None,
                     feature_analysis: dict[str, Any] | None = None,
                     **kwargs: Any) -> AIReview:
        """Full trade review pipeline."""
        ctx = self.build_context(
            event_id=event_id,
            knowledge_context=knowledge_context,
            reasoning_review=reasoning_review,
            similarity_context=similarity_context,
            prediction=prediction,
            research_report=research_report,
            feature_analysis=feature_analysis,
            **kwargs,
        )
        return self._full_review(PromptType.TRADE_REVIEW.value, ctx)

    def review_market(self, *,
                      event_id: str,
                      knowledge_context: dict[str, Any] | None = None,
                      strategy_statistics: dict[str, Any] | None = None,
                      **kwargs: Any) -> AIReview:
        """Full market review pipeline."""
        ctx = self.build_context(
            event_id=event_id,
            knowledge_context=knowledge_context,
            strategy_statistics=strategy_statistics,
            **kwargs,
        )
        return self._full_review(PromptType.MARKET_REVIEW.value, ctx)

    def review_risk(self, context: DecisionAIContext | dict[str, Any]) -> AIReview:
        return self._full_review(PromptType.RISK_REVIEW.value, context)

    def review_research(self, context: DecisionAIContext | dict[str, Any]) -> AIReview:
        return self._full_review(PromptType.RESEARCH_REVIEW.value, context)

    def review_prediction(self, context: DecisionAIContext | dict[str, Any]) -> AIReview:
        return self._full_review(PromptType.PREDICTION_REVIEW.value, context)

    def fusion_weights(self) -> dict[str, float]:
        """Expose confidence fusion weights."""
        return dict(FUSION_WEIGHTS)

    def _full_review(self, review_type: str,
                     context: DecisionAIContext | dict[str, Any]) -> AIReview:
        ctx = context.to_dict() if isinstance(context, DecisionAIContext) else context
        evidence = self._evidence.build(ctx).to_dict()
        fused = self._fusion.fuse(ctx).to_dict()
        guardrail_report = self._guardrails.validate(ctx, evidence=evidence).to_dict()
        summary = self._summary.build(
            ctx, evidence=evidence,
            fused_confidence=fused,
            guardrails=guardrail_report,
        )
        prompt = self._prompts.build(
            review_type, ctx,
            evidence=evidence,
            guardrails=guardrail_report,
        )
        return self._review.review(
            review_type, ctx,
            evidence=evidence,
            prompt=prompt,
            summary=summary,
            confidence=fused,
            guardrails=guardrail_report,
        )
