# -*- coding: utf-8 -*-
"""AIA-13 Arabic AI Market Analyst — package exports."""
from __future__ import annotations

from .context_profile import (
    CONTEXT_PROFILES,
    DEFAULT_PROFILE,
    resolve_budget,
    resolve_profile,
)
from .gate import gate_prediction, scan_text_for_invented_probability
from .normalize import normalize_analyst_response
from .outlook_eval import evaluate_outlook, outlook_pattern_label
from .persona import ANALYST_ROLE, ANALYST_RULES

__all__ = [
    "ANALYST_ROLE",
    "ANALYST_RULES",
    "CONTEXT_PROFILES",
    "DEFAULT_PROFILE",
    "resolve_budget",
    "resolve_profile",
    "gate_prediction",
    "scan_text_for_invented_probability",
    "normalize_analyst_response",
    "evaluate_outlook",
    "outlook_pattern_label",
]
