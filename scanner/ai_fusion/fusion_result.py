# -*- coding: utf-8 -*-
"""Structured fusion output."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FusionResult:
    fusion_state: str = "PREDICTION_UNAVAILABLE"
    platform_action: str = ""
    platform_confidence: float | None = None
    prediction_available: bool = False
    prediction: dict[str, Any] = field(default_factory=dict)
    llm_assessment: dict[str, Any] = field(default_factory=dict)
    confidence_separation: dict[str, Any] = field(default_factory=dict)
    agreement: dict[str, Any] = field(default_factory=dict)
    policy: dict[str, Any] = field(default_factory=dict)
    package_fingerprint: str = ""
    review_id: str = ""
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fusion_state": self.fusion_state,
            "platform_action": self.platform_action,
            "platform_confidence": self.platform_confidence,
            "prediction_available": self.prediction_available,
            "prediction": dict(self.prediction),
            "llm_assessment": dict(self.llm_assessment),
            "confidence_separation": dict(self.confidence_separation),
            "agreement": dict(self.agreement),
            "policy": dict(self.policy),
            "package_fingerprint": self.package_fingerprint,
            "review_id": self.review_id,
            "provider": self.provider,
            "model": self.model,
        }
