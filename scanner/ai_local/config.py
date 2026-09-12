# -*- coding: utf-8 -*-
"""Local AI configuration — additive, default claude_only."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

EXECUTION_MODES = ("claude_only", "local_only", "local_first", "compare")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "qwen3:8b"


@dataclass(frozen=True)
class LocalAIConfig:
    local_enabled: bool = False
    ollama_enabled: bool = False
    ollama_base_url: str = DEFAULT_OLLAMA_URL
    local_default_model: str = DEFAULT_LOCAL_MODEL
    execution_mode: str = "claude_only"
    # Escalation thresholds (local_first)
    escalate_on_validation_failure: bool = True
    escalate_on_provider_error: bool = True
    escalate_on_malformed_response: bool = True
    escalate_min_confidence: float = 40.0
    escalate_on_grounding_failure: bool = True
    escalate_grounding_below: float = 50.0


_DEFAULTS = LocalAIConfig()


def _load_appsettings():
    for mod in ("dashboard.appsettings", "web.dashboard.appsettings"):
        try:
            import importlib
            return importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            continue
    return None


def load_local_config() -> LocalAIConfig:
    try:
        appsettings = _load_appsettings()
        if appsettings is None:
            return _DEFAULTS
        v = appsettings.values()
    except Exception:  # noqa: BLE001
        return _DEFAULTS

    mode = str(v.get("ai_execution_mode", _DEFAULTS.execution_mode)).strip().lower()
    if mode not in EXECUTION_MODES:
        mode = "claude_only"

    return LocalAIConfig(
        local_enabled=bool(v.get("ai_local_enabled", _DEFAULTS.local_enabled)),
        ollama_enabled=bool(v.get("ai_ollama_enabled", _DEFAULTS.ollama_enabled)),
        ollama_base_url=str(v.get("ai_ollama_base_url", _DEFAULTS.ollama_base_url)
                            ).strip() or DEFAULT_OLLAMA_URL,
        local_default_model=str(v.get("ai_local_model", _DEFAULTS.local_default_model)
                               ).strip() or DEFAULT_LOCAL_MODEL,
        execution_mode=mode,
        escalate_on_validation_failure=bool(
            v.get("ai_escalate_on_validation_failure", True)),
        escalate_on_provider_error=bool(v.get("ai_escalate_on_provider_error", True)),
        escalate_on_malformed_response=bool(
            v.get("ai_escalate_on_malformed_response", True)),
        escalate_min_confidence=float(v.get("ai_escalate_min_confidence", 40.0)),
        escalate_on_grounding_failure=bool(
            v.get("ai_escalate_on_grounding_failure", True)),
        escalate_grounding_below=float(v.get("ai_escalate_grounding_below", 50.0)),
    )


def local_config_to_public_dict(cfg: LocalAIConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_local_config()
    return {
        "local_enabled": cfg.local_enabled,
        "ollama_enabled": cfg.ollama_enabled,
        "ollama_base_url": cfg.ollama_base_url,
        "local_default_model": cfg.local_default_model,
        "execution_mode": cfg.execution_mode,
        "escalate_min_confidence": cfg.escalate_min_confidence,
        "escalate_grounding_below": cfg.escalate_grounding_below,
    }
