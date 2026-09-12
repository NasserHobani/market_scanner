# -*- coding: utf-8 -*-
"""Local AI runtime helpers."""
from __future__ import annotations

from typing import Any

from scanner.ai_advisor.provider_config import load_config

from .config import LocalAIConfig, load_local_config
from .health import check_ollama_health


def is_local_ai_configured() -> bool:
    cfg = load_local_config()
    return cfg.local_enabled and cfg.ollama_enabled


def runtime_status() -> str:
    """NOT READY | CONFIGURED | CONNECTED | RUNNING | VERIFIED"""
    local = load_local_config()
    if not local.local_enabled:
        return "NOT READY"
    if not local.ollama_enabled:
        return "CONFIGURED"
    health = check_ollama_health(local)
    if not health.get("ollama_reachable"):
        return "CONFIGURED"
    if not health.get("model_available"):
        return "CONNECTED"
    from .history import LocalAIHistory
    verified = any(
        r.get("validation_passed") and r.get("provider") == "ollama"
        for r in LocalAIHistory().list_recent(50)
    )
    if verified:
        return "VERIFIED"
    if load_config().shadow_mode:
        return "RUNNING"
    return "CONNECTED"


def status_payload() -> dict[str, Any]:
    local = load_local_config()
    health = check_ollama_health(local)
    from .history import LocalAIHistory
    from .metrics import compute_metrics

    last = LocalAIHistory().list_recent(1)
    return {
        "status": runtime_status(),
        "enabled": local.local_enabled,
        "execution_mode": local.execution_mode,
        "health": health,
        "metrics": compute_metrics(),
        "last_review": last[0] if last else None,
    }
