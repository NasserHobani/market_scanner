# -*- coding: utf-8 -*-
"""Reasoning orchestrator — evidence → confidence → review."""
from __future__ import annotations

from typing import Any

from .confidence import ConfidenceEngine
from .contradiction import ContradictionEngine
from .decision_tree import DecisionTree
from .evidence_engine import EvidenceEngine
from .explainability import ExplainabilityEngine
from .reasoning_context import ReasoningContext
from .recommendation_review import RecommendationReview, RecommendationReviewer


class ReasoningEngine:
    """Full reasoning pipeline — explainable, reproducible, no LLM."""

    def __init__(self, *,
                 evidence_engine: EvidenceEngine | None = None,
                 contradiction_engine: ContradictionEngine | None = None,
                 confidence_engine: ConfidenceEngine | None = None,
                 decision_tree: DecisionTree | None = None,
                 explainability_engine: ExplainabilityEngine | None = None,
                 reviewer: RecommendationReviewer | None = None) -> None:
        self.evidence_engine = evidence_engine or EvidenceEngine()
        self.contradiction_engine = contradiction_engine or ContradictionEngine()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.decision_tree = decision_tree or DecisionTree()
        self.explainability_engine = explainability_engine or ExplainabilityEngine()
        self.reviewer = reviewer or RecommendationReviewer()

    def run(self, context: ReasoningContext | dict[str, Any]) -> RecommendationReview:
        if isinstance(context, ReasoningContext):
            ctx = context.as_knowledge_dict()
        else:
            ctx = dict(context)

        bundle = self.evidence_engine.build(ctx)
        contradictions = self.contradiction_engine.analyze(bundle)
        confidence = self.confidence_engine.compute(
            bundle, contradiction_count=len(contradictions.items))
        tree = self.decision_tree.run(ctx, bundle)
        explanation = self.explainability_engine.explain(
            bundle,
            contradictions=contradictions,
            confidence=confidence,
            tree_status=tree.to_dict(),
        )
        return self.reviewer.review(
            ctx,
            bundle=bundle,
            contradictions=contradictions,
            confidence=confidence,
            explanation=explanation,
            tree=tree,
        )

    def run_partial(self, context: ReasoningContext | dict[str, Any]) -> dict[str, Any]:
        """Return intermediate artifacts for debugging."""
        ctx = (context.as_knowledge_dict() if isinstance(context, ReasoningContext)
               else dict(context))
        bundle = self.evidence_engine.build(ctx)
        contradictions = self.contradiction_engine.analyze(bundle)
        confidence = self.confidence_engine.compute(
            bundle, contradiction_count=len(contradictions.items))
        tree = self.decision_tree.run(ctx, bundle)
        explanation = self.explainability_engine.explain(
            bundle, contradictions=contradictions, confidence=confidence,
            tree_status=tree.to_dict())
        return {
            "evidence": bundle.to_dict(),
            "contradictions": contradictions.to_dict(),
            "confidence": confidence.to_dict(),
            "decision_tree": tree.to_dict(),
            "explanation": explanation.to_dict(),
        }
