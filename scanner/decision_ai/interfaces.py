# -*- coding: utf-8 -*-
"""Decision AI protocols."""
from __future__ import annotations

from typing import Any, Protocol

from .ai_review import AIReview
from .context_builder import DecisionAIContext
from .decision_summary import DecisionSummary
from .prompt_builder import StructuredPrompt


class ContextBuilderProtocol(Protocol):
    def build(self, **kwargs: Any) -> DecisionAIContext: ...


class EvidenceBuilderProtocol(Protocol):
    def build(self, context: dict[str, Any]) -> Any: ...


class PromptBuilderProtocol(Protocol):
    def build(self, prompt_type: str, context: dict[str, Any], **kwargs: Any) -> StructuredPrompt: ...


class DecisionAIServiceProtocol(Protocol):
    def build_context(self, **kwargs: Any) -> DecisionAIContext: ...
    def build_prompt(self, prompt_type: str, context: dict[str, Any], **kwargs: Any) -> StructuredPrompt: ...
    def review_trade(self, **kwargs: Any) -> AIReview: ...
    def review_market(self, **kwargs: Any) -> AIReview: ...
    def decision_summary(self, context: dict[str, Any], **kwargs: Any) -> DecisionSummary: ...
