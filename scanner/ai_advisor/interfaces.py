# -*- coding: utf-8 -*-
"""AI Advisor protocols — provider abstraction and service contracts."""
from __future__ import annotations

from typing import Any, Protocol

from .decision_package import DecisionPackage
from .prompt_builder import AdvisorPrompt
from .review import AdvisorReview


class LLMProviderProtocol(Protocol):
    """Every LLM provider must implement this contract."""

    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]: ...

    def health(self) -> dict[str, Any]: ...

    def model_name(self) -> str: ...


class AdvisorServiceProtocol(Protocol):
    """Public advisor service contract."""

    def review(self, package: DecisionPackage, *,
               provider_id: str | None = None,
               prompt_version: str | None = None) -> AdvisorReview: ...

    def list_providers(self) -> list[dict[str, Any]]: ...

    def advisor_score(self) -> dict[str, Any]: ...


class MemoryStoreProtocol(Protocol):
    def save(self, record: dict[str, Any]) -> str: ...
    def load(self, record_id: str) -> dict[str, Any] | None: ...
    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]: ...
