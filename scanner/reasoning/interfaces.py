# -*- coding: utf-8 -*-
"""Reasoning layer interfaces — dependency inversion for future AI."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .confidence import ConfidenceBreakdown
from .contradiction import ContradictionReport
from .evidence import EvidenceBundle
from .explainability import StructuredExplanation
from .recommendation_review import RecommendationReview
from .reasoning_context import ReasoningContext


@runtime_checkable
class EvidenceProvider(Protocol):
    def build(self, context: dict[str, Any]) -> EvidenceBundle: ...


@runtime_checkable
class ConfidenceProvider(Protocol):
    def compute(self, bundle: EvidenceBundle, *,
                contradiction_count: int = 0) -> ConfidenceBreakdown: ...


@runtime_checkable
class ExplainabilityProvider(Protocol):
    def explain(self, bundle: EvidenceBundle, *,
                contradictions: ContradictionReport,
                confidence: ConfidenceBreakdown,
                tree_status: dict[str, Any] | None = None,
                ) -> StructuredExplanation: ...


@runtime_checkable
class ReasoningProvider(Protocol):
    def run(self, context: ReasoningContext | dict[str, Any]) -> RecommendationReview: ...

    def run_partial(self, context: ReasoningContext | dict[str, Any]) -> dict[str, Any]: ...
