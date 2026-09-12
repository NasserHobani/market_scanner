# -*- coding: utf-8 -*-
"""Research orchestrator configuration — loaded from settings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchOrchestratorConfig:
    auto_enabled: bool = True
    min_new_trades: int = 10
    weekly_enabled: bool = True
    hypothesis_enabled: bool = True
    failure_threshold: int = 10
    min_closed_trades: int = 20
    min_group_size: int = 5
    min_comparison_size: int = 5
    hypothesis_min_confidence: float = 60.0


_DEFAULTS = ResearchOrchestratorConfig()


def _load_appsettings():
    for mod in ("dashboard.appsettings", "web.dashboard.appsettings"):
        try:
            import importlib
            return importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            continue
    return None


def load_research_config() -> ResearchOrchestratorConfig:
    try:
        appsettings = _load_appsettings()
        if appsettings is None:
            return _DEFAULTS
        v = appsettings.values()
    except Exception:  # noqa: BLE001
        return _DEFAULTS

    return ResearchOrchestratorConfig(
        auto_enabled=bool(v.get("research_auto_enabled", _DEFAULTS.auto_enabled)),
        min_new_trades=int(v.get("research_min_new_trades", _DEFAULTS.min_new_trades)),
        weekly_enabled=bool(v.get("research_weekly_enabled", _DEFAULTS.weekly_enabled)),
        hypothesis_enabled=bool(v.get("research_hypothesis_enabled", _DEFAULTS.hypothesis_enabled)),
        failure_threshold=int(v.get("research_failure_threshold", _DEFAULTS.failure_threshold)),
        min_closed_trades=int(v.get("research_min_closed_trades", _DEFAULTS.min_closed_trades)),
        min_group_size=int(v.get("research_min_group_size", _DEFAULTS.min_group_size)),
        min_comparison_size=int(v.get("research_min_comparison_size", _DEFAULTS.min_comparison_size)),
        hypothesis_min_confidence=float(
            v.get("research_hypothesis_min_confidence", _DEFAULTS.hypothesis_min_confidence)),
    )


def config_to_public_dict(cfg: ResearchOrchestratorConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_research_config()
    return {
        "auto_enabled": cfg.auto_enabled,
        "min_new_trades": cfg.min_new_trades,
        "weekly_enabled": cfg.weekly_enabled,
        "hypothesis_enabled": cfg.hypothesis_enabled,
        "failure_threshold": cfg.failure_threshold,
        "min_closed_trades": cfg.min_closed_trades,
        "min_group_size": cfg.min_group_size,
        "min_comparison_size": cfg.min_comparison_size,
        "hypothesis_min_confidence": cfg.hypothesis_min_confidence,
    }
