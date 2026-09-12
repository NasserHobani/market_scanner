# -*- coding: utf-8 -*-
"""Deterministic lesson fingerprints for deduplication."""
from __future__ import annotations

import hashlib
from typing import Any


def lesson_fingerprint(*,
                       failure_type: str = "",
                       pattern_type: str = "",
                       provider: str = "",
                       market: str = "",
                       timeframe: str = "",
                       strategy: str = "") -> str:
    """Stable fingerprint for the same underlying lesson pattern."""
    kind = (failure_type or pattern_type or "unknown").strip().lower()
    parts = [
        kind,
        (provider or "any").strip().lower(),
        (market or "any").strip().lower(),
        (timeframe or "any").strip().lower(),
        (strategy or "any").strip().lower(),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"lfp_{digest[:20]}"


def fingerprint_from_lesson(lesson: dict[str, Any]) -> str:
    if lesson.get("fingerprint"):
        return str(lesson["fingerprint"])
    return lesson_fingerprint(
        failure_type=str(lesson.get("failure_type") or lesson.get("pattern_type") or ""),
        pattern_type=str(lesson.get("pattern_type") or ""),
        provider=str(lesson.get("provider") or (lesson.get("affected_providers") or ["any"])[0]),
        market=str((lesson.get("affected_markets") or ["any"])[0]),
        timeframe=str((lesson.get("affected_timeframes") or ["any"])[0]),
        strategy=str((lesson.get("affected_strategies") or ["any"])[0]),
    )
