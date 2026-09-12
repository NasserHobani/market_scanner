# -*- coding: utf-8 -*-
"""Provider registry — runtime registration, no hardcoded singletons."""
from __future__ import annotations

from typing import Any

from .providers.base import LLMProvider
from .providers import (
    DeepSeekProvider,
    GeminiProvider,
    MockProvider,
    OpenAIProvider,
    OpenRouterProvider,
    OpenSourceProvider,
)


class ProviderRegistry:
    """Register and resolve LLM providers at runtime.

    Designed for future multi-model dispatch: one Decision Package
    can be sent to multiple providers simultaneously.
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.provider_id] = provider

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)

    def get(self, provider_id: str) -> LLMProvider:
        if provider_id not in self._providers:
            from .provider_config import effective_provider_id, load_config
            if provider_id == "mock":
                fallback = effective_provider_id(load_config())
                if fallback in self._providers:
                    return self._providers[fallback]
            raise KeyError(f"Provider not registered: {provider_id}")
        return self._providers[provider_id]

    def list_all(self) -> list[dict[str, Any]]:
        return [p.provider_info() for p in self._providers.values()]

    def health_check_all(self) -> dict[str, Any]:
        results = {}
        for pid, provider in self._providers.items():
            results[pid] = provider.health()
        healthy = sum(1 for h in results.values() if h.get("healthy"))
        return {
            "providers": results,
            "total": len(results),
            "healthy": healthy,
        }

    def register_defaults(self) -> None:
        """Register all built-in providers."""
        from .provider_factory import create_claude_provider, create_ollama_provider
        self.register(create_claude_provider())
        try:
            self.register(create_ollama_provider())
        except Exception:  # noqa: BLE001
            pass  # local provider optional at import time
        for cls in (OpenAIProvider, GeminiProvider,
                    DeepSeekProvider, OpenRouterProvider, OpenSourceProvider):
            p = cls()
            self.register(p)


_default_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry()
        _default_registry.register_defaults()
    return _default_registry
