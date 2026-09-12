# -*- coding: utf-8 -*-
"""Context profiles for compact advisor packages — AIA-13."""
from __future__ import annotations

from typing import Any

# Token targets (approximate). Critical sections are never pruned below usability.
CONTEXT_PROFILES: dict[str, int] = {
    "fast": 1500,       # automatic scanner reviews
    "standard": 2500,   # manual symbol analysis
    "deep": 4000,       # escalations / deep reviews
}

DEFAULT_PROFILE = "standard"
PROFILE_ALIASES = {
    "auto": "fast",
    "automatic": "fast",
    "manual": "standard",
    "full": "deep",
}


def resolve_profile(profile: str | None) -> str:
    key = (profile or DEFAULT_PROFILE).strip().lower()
    key = PROFILE_ALIASES.get(key, key)
    if key not in CONTEXT_PROFILES:
        return DEFAULT_PROFILE
    return key


def resolve_budget(profile: str | None = None, budget: int | None = None) -> int:
    """Return token budget for package optimization."""
    if budget is not None:
        try:
            b = int(budget)
            if b > 0:
                return b
        except (TypeError, ValueError):
            pass
    return CONTEXT_PROFILES[resolve_profile(profile)]


def profile_meta(profile: str | None = None, budget: int | None = None) -> dict[str, Any]:
    p = resolve_profile(profile)
    return {
        "context_profile": p,
        "token_budget": resolve_budget(p, budget),
    }
