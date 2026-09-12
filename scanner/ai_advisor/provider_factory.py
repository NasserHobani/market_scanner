# -*- coding: utf-8 -*-
"""Provider factory — creates providers from configuration."""
from __future__ import annotations

from .provider_config import load_config
from .providers.claude_provider import ClaudeProvider
from .providers.base import LLMProvider


def create_claude_provider(config=None) -> ClaudeProvider:
    """Create production Claude provider from current settings."""
    return ClaudeProvider(_config=config or load_config())


def create_ollama_provider(config=None) -> LLMProvider:
    """Create Ollama local provider (AIA-06)."""
    from scanner.ai_local.ollama_provider import OllamaProvider
    return OllamaProvider(_config=config or load_config())


def get_default_provider_id() -> str:
    return load_config().default_provider
