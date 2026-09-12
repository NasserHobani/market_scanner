# -*- coding: utf-8 -*-
"""Prediction result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PredictionResult:
    """Structured prediction output — analytical signal only, no buy/sell."""

    prediction: float
    probability: float | None = None
    confidence: float | None = None
    model_id: str = ""
    model_version: str = ""
    feature_version: str = ""
    plugin: str = ""
    explainability: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction": self.prediction,
            "probability": self.probability,
            "confidence": self.confidence,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "plugin": self.plugin,
            "explainability": dict(self.explainability),
            "timestamp": self.timestamp or datetime.now(timezone.utc).isoformat(),
            "disclaimer": "Analytical signal only — not a trading recommendation",
        }
