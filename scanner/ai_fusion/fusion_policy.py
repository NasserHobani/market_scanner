# -*- coding: utf-8 -*-
"""Transparent fusion policy — advisory only, never changes trading."""
from __future__ import annotations

from typing import Any

ADVISORY_CAUTION = "caution"
ADVISORY_NEUTRAL = "neutral"
ADVISORY_SUPPORT = "support"


def apply_policy(agreement: dict[str, Any]) -> dict[str, Any]:
    state = str(agreement.get("fusion_state", "PREDICTION_UNAVAILABLE")).upper()
    advisory = ADVISORY_NEUTRAL

    if state == "ALIGNED":
        advisory = ADVISORY_SUPPORT
    elif state in ("LLM_CONFLICT", "PREDICTION_CONFLICT", "STATISTICAL_CONFLICT", "MIXED"):
        advisory = ADVISORY_CAUTION
    elif state == "INSUFFICIENT_EVIDENCE":
        advisory = ADVISORY_NEUTRAL
    elif state == "PREDICTION_UNAVAILABLE":
        advisory = ADVISORY_NEUTRAL

    return {
        "platform_action": agreement.get("platform_action", ""),
        "fusion_state": state,
        "advisory": advisory,
        "modifies_trading": False,
        "shadow_mode": True,
    }
