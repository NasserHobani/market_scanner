# -*- coding: utf-8 -*-
"""LLM provider base class and metadata."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..decision_package import DecisionPackage
from ..prompt_builder import AdvisorPrompt


@dataclass
class ProviderMetadata:
    """Descriptor for a registered LLM provider."""

    provider_id: str
    display_name: str
    vendor: str
    model_family: str
    supports_json: bool = True
    supports_streaming: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "vendor": self.vendor,
            "model_family": self.model_family,
            "supports_json": self.supports_json,
            "supports_streaming": self.supports_streaming,
            "description": self.description,
        }


class LLMProvider(ABC):
    """Abstract base for all LLM providers.

  No API keys. No network calls in the base class.
  Concrete implementations are registered at runtime.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata: ...

    @abstractmethod
    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]:
        """Send prompt to LLM and return raw response dict."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return provider health status."""

    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier this provider uses."""

    def provider_info(self) -> dict[str, Any]:
        return {
            **self.metadata.to_dict(),
            "model_name": self.model_name(),
            "healthy": self.health().get("healthy", False),
        }


@dataclass
class MockProviderResponse:
    """Canned response for testing."""

    raw_json: dict[str, Any] = field(default_factory=dict)
    healthy: bool = True
    model: str = "mock-model-v1"

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw_json)
