# -*- coding: utf-8 -*-
"""LLM provider implementations.

Claude is production-ready (claude_provider.py).
Other vendors remain stubs until their integration sprints.
"""
from __future__ import annotations

from typing import Any

from .base import LLMProvider, ProviderMetadata
from ..decision_package import DecisionPackage
from ..prompt_builder import AdvisorPrompt
from .claude_provider import ClaudeProvider


def _stub_response(package: DecisionPackage, provider_id: str) -> dict[str, Any]:
    """Generate a deterministic stub response grounded in the package."""
    decision = package.decision or {}
    evidence_ids = [e.evidence_id for e in package.evidence_index[:3]]
    return {
        "agreement": "partial",
        "confidence": 65,
        "summary": f"Stub review from {provider_id} for {package.event_id}",
        "reasoning": "Provider stub — no live LLM invoked.",
        "supporting_evidence": [
            {"evidence_id": eid, "section": "decision", "field": "verdict",
             "note": f"Platform verdict: {decision.get('verdict')}"}
            for eid in evidence_ids[:1]
        ],
        "contradicting_evidence": [],
        "risks": ["Stub mode — no real analysis performed"],
        "missing_information": list(package.knowledge_summary.get("memory_gaps") or [])[:3],
        "suggested_experiment": {
            "hypothesis": "Validate edge on out-of-sample window",
            "method": "Walk-forward on last 90 days",
            "expected_outcome": "Confirm or reject current expectancy",
        },
        "shadow_mode_acknowledged": True,
    }


class _StubProvider(LLMProvider):
    """Base for vendor-specific stub providers."""

    def __init__(self, provider_id: str, display_name: str,
                 vendor: str, model_family: str, model: str) -> None:
        self._id = provider_id
        self._meta = ProviderMetadata(
            provider_id=provider_id,
            display_name=display_name,
            vendor=vendor,
            model_family=model_family,
            description=f"Stub {display_name} provider — no API key required",
        )
        self._model = model

    @property
    def provider_id(self) -> str:
        return self._id

    @property
    def metadata(self) -> ProviderMetadata:
        return self._meta

    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]:
        return _stub_response(package, self._id)

    def health(self) -> dict[str, Any]:
        return {"healthy": True, "provider_id": self._id, "mode": "stub"}

    def model_name(self) -> str:
        return self._model


class OpenAIProvider(_StubProvider):
    def __init__(self) -> None:
        super().__init__("openai", "OpenAI", "openai", "gpt", "gpt-stub")


class GeminiProvider(_StubProvider):
    def __init__(self) -> None:
        super().__init__("gemini", "Gemini", "google", "gemini", "gemini-stub")


class DeepSeekProvider(_StubProvider):
    def __init__(self) -> None:
        super().__init__("deepseek", "DeepSeek", "deepseek", "deepseek", "deepseek-stub")


class OpenRouterProvider(_StubProvider):
    def __init__(self) -> None:
        super().__init__("openrouter", "OpenRouter", "openrouter", "multi", "openrouter-stub")


class OpenSourceProvider(_StubProvider):
    def __init__(self) -> None:
        super().__init__("opensource", "Open Source", "community", "oss", "llama-stub")


class MockProvider(_StubProvider):
    """Explicit mock for unit tests."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        super().__init__("mock", "Mock", "test", "mock", "mock-v1")
        self._custom_response = response

    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]:
        if self._custom_response:
            return dict(self._custom_response)
        return _stub_response(package, "mock")
