# -*- coding: utf-8 -*-
"""Prediction training orchestrator configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PredictionTrainingConfig:
    auto_enabled: bool = True
    min_eligible_trades: int = 50
    min_new_trades: int = 20
    min_test_samples: int = 5
    min_accuracy_improvement: float = 0.02
    walk_forward_enabled: bool = True
    walk_forward_train_size: int = 30
    walk_forward_test_size: int = 10
    scheduled_weekly: bool = True


_DEFAULTS = PredictionTrainingConfig()


def _load_appsettings():
    for mod in ("dashboard.appsettings", "web.dashboard.appsettings"):
        try:
            import importlib
            return importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            continue
    return None


def load_prediction_config() -> PredictionTrainingConfig:
    try:
        appsettings = _load_appsettings()
        if appsettings is None:
            return _DEFAULTS
        v = appsettings.values()
    except Exception:  # noqa: BLE001
        return _DEFAULTS

    return PredictionTrainingConfig(
        auto_enabled=bool(v.get("prediction_auto_enabled", _DEFAULTS.auto_enabled)),
        min_eligible_trades=int(v.get("prediction_min_eligible_trades", _DEFAULTS.min_eligible_trades)),
        min_new_trades=int(v.get("prediction_min_new_trades", _DEFAULTS.min_new_trades)),
        min_test_samples=int(v.get("prediction_min_test_samples", _DEFAULTS.min_test_samples)),
        min_accuracy_improvement=float(
            v.get("prediction_min_accuracy_improvement", _DEFAULTS.min_accuracy_improvement)),
        walk_forward_enabled=bool(
            v.get("prediction_walk_forward_enabled", _DEFAULTS.walk_forward_enabled)),
        walk_forward_train_size=int(
            v.get("prediction_walk_forward_train_size", _DEFAULTS.walk_forward_train_size)),
        walk_forward_test_size=int(
            v.get("prediction_walk_forward_test_size", _DEFAULTS.walk_forward_test_size)),
        scheduled_weekly=bool(v.get("prediction_weekly_enabled", _DEFAULTS.scheduled_weekly)),
    )


def config_to_public_dict(cfg: PredictionTrainingConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_prediction_config()
    return {
        "auto_enabled": cfg.auto_enabled,
        "min_eligible_trades": cfg.min_eligible_trades,
        "min_new_trades": cfg.min_new_trades,
        "min_test_samples": cfg.min_test_samples,
        "min_accuracy_improvement": cfg.min_accuracy_improvement,
        "walk_forward_enabled": cfg.walk_forward_enabled,
    }
