# -*- coding: utf-8 -*-
"""Configurable model catalog — models are never hardcoded in providers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "ai_provider_models.json"

_DEFAULT_CATALOG: dict[str, list[dict[str, str]]] = {
    "claude": [
        {"id": "claude-sonnet-4-6", "display": "Claude Sonnet 4.6"},
        {"id": "claude-sonnet-4-5-20250929", "display": "Claude Sonnet 4.5"},
        {"id": "claude-opus-4-6", "display": "Claude Opus 4.6"},
        {"id": "claude-opus-4-5-20251101", "display": "Claude Opus 4.5"},
        {"id": "claude-3-5-sonnet-20241022", "display": "Claude 3.5 Sonnet"},
        {"id": "claude-3-5-haiku-20241022", "display": "Claude 3.5 Haiku"},
    ],
    "providers": [
        {"id": "claude", "display": "Claude"},
        {"id": "mock", "display": "Mock (Testing)"},
        {"id": "openai", "display": "OpenAI"},
        {"id": "gemini", "display": "Gemini"},
        {"id": "deepseek", "display": "DeepSeek"},
        {"id": "opensource", "display": "Open Source"},
    ],
}


def _load_catalog() -> dict[str, Any]:
    if _CATALOG_PATH.exists():
        try:
            with open(_CATALOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT_CATALOG)


def claude_model_choices() -> tuple[tuple[str, str], ...]:
    catalog = _load_catalog()
    models = catalog.get("claude", _DEFAULT_CATALOG["claude"])
    return tuple((m["id"], m["display"]) for m in models)


def provider_choices() -> tuple[tuple[str, str], ...]:
    catalog = _load_catalog()
    providers = catalog.get("providers", _DEFAULT_CATALOG["providers"])
    return tuple((p["id"], p["display"]) for p in providers)


def default_claude_model() -> str:
    choices = claude_model_choices()
    return choices[0][0] if choices else ""


def valid_claude_model_ids() -> set[str]:
    return {m["id"] for m in list_claude_models()}


def resolve_claude_model(model_id: str) -> str:
    """Return model_id if valid, else fall back to catalog default."""
    cleaned = (model_id or "").strip()
    if cleaned in valid_claude_model_ids():
        return cleaned
    return default_claude_model()


def list_claude_models() -> list[dict[str, str]]:
    catalog = _load_catalog()
    return list(catalog.get("claude", _DEFAULT_CATALOG["claude"]))


def ollama_model_choices() -> tuple[tuple[str, str], ...]:
    catalog = _load_catalog()
    models = catalog.get("ollama", [
        {"id": "qwen3:4b", "display": "Qwen3 4B"},
        {"id": "qwen3:8b", "display": "Qwen3 8B"},
    ])
    return tuple((m["id"], m["display"]) for m in models)


def resolve_ollama_model(model_id: str) -> str:
    cleaned = (model_id or "").strip()
    valid = {m[0] for m in ollama_model_choices()}
    if cleaned in valid:
        return cleaned
    choices = ollama_model_choices()
    return choices[0][0] if choices else "qwen3:8b"
