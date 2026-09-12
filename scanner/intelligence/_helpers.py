# -*- coding: utf-8 -*-
"""Shared helpers for intelligence analytics."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from scanner.tracking import LOST, WON, summarize


def closed_trades(rows: Iterable[dict]) -> list[dict]:
    return [r for r in rows if r.get("status") in (WON, LOST)]


def sort_by_time(rows: list[dict]) -> list[dict]:
    def _key(r: dict) -> Any:
        return r.get("closed_at") or r.get("signal_at") or ""
    return sorted(rows, key=_key)


def win_rate(rows: list[dict]) -> float | None:
    if not rows:
        return None
    wins = sum(1 for r in rows if r.get("status") == WON)
    return round(wins / len(rows) * 100, 2)


def avg_r(rows: list[dict]) -> float | None:
    rs = [float(r["r_multiple"]) for r in rows if r.get("r_multiple") is not None]
    return round(sum(rs) / len(rs), 3) if rs else None


def factor_set(row: dict) -> frozenset[str]:
    return frozenset(str(f) for f in (row.get("factors") or []))


def combo_key(factors: frozenset[str]) -> str:
    return "+".join(sorted(factors)) if factors else "none"


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
