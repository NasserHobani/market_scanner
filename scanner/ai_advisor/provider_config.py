# -*- coding: utf-8 -*-
"""AI Advisor configuration — loaded from settings, never from code."""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Any

from .models_catalog import default_claude_model, resolve_claude_model
from .prompt_builder import DEFAULT_PROMPT_VERSION


@dataclass(frozen=True)
class AIAdvisorConfig:
    claude_enabled: bool = True
    default_provider: str = "claude"
    claude_model: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: float = 60.0
    retry_count: int = 2
    shadow_mode: bool = True
    memory_enabled: bool = True
    evaluation_enabled: bool = True
    learning_enabled: bool = True
    prompt_version: str = "advisor_prompt_v4"
    strict_json: bool = True
    grounding_required: bool = True
    allow_experiments: bool = True
    max_evidence_items: int = 10
    save_raw_responses: bool = False
    health_check_interval: int = 300

    @property
    def api_key_configured(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def effective_model(self) -> str:
        return self.claude_model or default_claude_model()


_DEFAULTS = AIAdvisorConfig()


def apply_production_defaults(cfg: AIAdvisorConfig) -> AIAdvisorConfig:
    """When API key is configured, activate Claude for production runtime."""
    if not cfg.api_key_configured:
        return cfg
    if cfg.default_provider == "mock" or not cfg.claude_enabled:
        return dataclasses.replace(
            cfg, default_provider="claude", claude_enabled=True,
        )
    return cfg


def effective_provider_id(cfg: AIAdvisorConfig | None = None) -> str:
    """Resolve the provider used at runtime — never accidental mock in production."""
    cfg = apply_production_defaults(cfg or load_config_raw())
    pid = cfg.default_provider
    if pid == "mock":
        return "mock"
    if pid == "claude":
        return "claude" if cfg.api_key_configured else pid
    return pid


def _load_appsettings():
    for mod in ("dashboard.appsettings", "web.dashboard.appsettings"):
        try:
            import importlib
            return importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            continue
    return None


def load_config_raw() -> AIAdvisorConfig:
    """Load config without production overrides (for settings UI)."""
    try:
        appsettings = _load_appsettings()
        if appsettings is None:
            return _DEFAULTS
        v = appsettings.values()
    except Exception:  # noqa: BLE001
        return _DEFAULTS

    return AIAdvisorConfig(
        claude_enabled=bool(v.get("ai_claude_enabled", _DEFAULTS.claude_enabled)),
        default_provider=str(v.get("ai_default_provider", _DEFAULTS.default_provider)),
        claude_model=resolve_claude_model(str(v.get("ai_claude_model", "") or "")),
        temperature=float(v.get("ai_temperature", _DEFAULTS.temperature)),
        max_tokens=int(v.get("ai_max_tokens", _DEFAULTS.max_tokens)),
        timeout=float(v.get("ai_timeout", _DEFAULTS.timeout)),
        retry_count=int(v.get("ai_retry_count", _DEFAULTS.retry_count)),
        shadow_mode=bool(v.get("ai_shadow_mode", _DEFAULTS.shadow_mode)),
        memory_enabled=bool(v.get("ai_memory_enabled", _DEFAULTS.memory_enabled)),
        evaluation_enabled=bool(v.get("ai_evaluation_enabled", _DEFAULTS.evaluation_enabled)),
        learning_enabled=bool(v.get("ai_learning_enabled", _DEFAULTS.learning_enabled)),
        prompt_version=str(v.get("ai_prompt_version", _DEFAULTS.prompt_version)),
        strict_json=bool(v.get("ai_strict_json", _DEFAULTS.strict_json)),
        grounding_required=bool(v.get("ai_grounding_required", _DEFAULTS.grounding_required)),
        allow_experiments=bool(v.get("ai_allow_experiments", _DEFAULTS.allow_experiments)),
        max_evidence_items=int(v.get("ai_max_evidence_items", _DEFAULTS.max_evidence_items)),
        save_raw_responses=bool(v.get("ai_save_raw_responses", _DEFAULTS.save_raw_responses)),
        health_check_interval=int(v.get("ai_health_check_interval", _DEFAULTS.health_check_interval)),
    )


def load_config() -> AIAdvisorConfig:
    """Load config with production activation applied."""
    return apply_production_defaults(load_config_raw())


def config_to_public_dict(config: AIAdvisorConfig | None = None) -> dict[str, Any]:
    """Settings safe for UI — never includes API key."""
    cfg = apply_production_defaults(config or load_config_raw())
    return {
        "claude_enabled": cfg.claude_enabled,
        "default_provider": effective_provider_id(cfg),
        "effective_provider": effective_provider_id(cfg),
        "claude_model": cfg.effective_model(),
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "timeout": cfg.timeout,
        "retry_count": cfg.retry_count,
        "shadow_mode": cfg.shadow_mode,
        "memory_enabled": cfg.memory_enabled,
        "evaluation_enabled": cfg.evaluation_enabled,
        "learning_enabled": cfg.learning_enabled,
        "prompt_version": cfg.prompt_version,
        "strict_json": cfg.strict_json,
        "grounding_required": cfg.grounding_required,
        "allow_experiments": cfg.allow_experiments,
        "max_evidence_items": cfg.max_evidence_items,
        "save_raw_responses": cfg.save_raw_responses,
        "health_check_interval": cfg.health_check_interval,
        "api_key_configured": cfg.api_key_configured,
    }
