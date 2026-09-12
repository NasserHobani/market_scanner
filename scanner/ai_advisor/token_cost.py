# -*- coding: utf-8 -*-
"""Token cost estimation for Claude models — USD per 1M tokens."""
from __future__ import annotations

# Rates approximate — configurable via data file in future sprint
_MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5-20251101": (15.0, 75.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-5-haiku-20241022": (0.8, 4.0),
}


def estimate_cost(model: str, *, prompt_tokens: int, completion_tokens: int) -> float:
    if (model or "").startswith("qwen") or "ollama" in (model or "").lower():
        return 0.0
    input_rate, output_rate = _MODEL_RATES.get(model, (3.0, 15.0))
    cost = (prompt_tokens / 1_000_000 * input_rate) + (completion_tokens / 1_000_000 * output_rate)
    return round(cost, 6)
