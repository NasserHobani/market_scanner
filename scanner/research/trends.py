# -*- coding: utf-8 -*-
"""Performance trends: equity, rolling expectancy, degradation."""
from __future__ import annotations

from typing import Iterable

from scanner.tracking import LOST, WON, summarize


def _closed_sorted(rows: list[dict]) -> list[dict]:
    closed = [r for r in rows if r.get("status") in (WON, LOST)]
    closed.sort(key=lambda r: (r.get("closed_at") or r.get("signal_at") or ""))
    return closed


def equity_curve(rows: Iterable[dict]) -> list[dict]:
    closed = _closed_sorted(list(rows))
    cum = 0.0
    peak = 0.0
    out = []
    for i, row in enumerate(closed, 1):
        r = float(row.get("r_multiple") or 0.0)
        cum += r
        peak = max(peak, cum)
        out.append({
            "index": i,
            "cumulative_r": round(cum, 3),
            "drawdown_r": round(peak - cum, 3),
            "r": round(r, 3),
        })
    return out


def rolling_expectancy(rows: Iterable[dict], window: int) -> list[dict]:
    closed = _closed_sorted(list(rows))
    rs = [float(r.get("r_multiple") or 0.0) for r in closed]
    out = []
    for i in range(window, len(rs) + 1):
        chunk = rs[i - window:i]
        out.append({
            "index": i,
            "window": window,
            "expectancy": round(sum(chunk) / len(chunk), 3),
        })
    return out


def bucketed_metrics(rows: Iterable[dict], *, bucket_size: int = 10) -> list[dict]:
    """Bucket closed trades for trend lines."""
    closed = _closed_sorted(list(rows))
    out = []
    for start in range(0, len(closed), bucket_size):
        chunk = closed[start:start + bucket_size]
        s = summarize(chunk)
        if not s["closed"]:
            continue
        out.append({
            "bucket": start // bucket_size + 1,
            "closed": s["closed"],
            "expectancy": s.get("expectancy"),
            "profit_factor": s.get("profit_factor"),
            "win_rate": s.get("win_rate"),
        })
    return out


def degradation_verdict(rows: Iterable[dict]) -> dict:
    """Rule-based trend alert."""
    closed = _closed_sorted(list(rows))
    rs = [float(r.get("r_multiple") or 0.0) for r in closed]
    if len(rs) < 30:
        return {"level": "none", "message": "عيّنة قصيرة — لا حكم اتجاه بعد", "rolling_30": None, "rolling_50": None}
    r30 = sum(rs[-30:]) / 30
    r50 = sum(rs[-50:]) / 50 if len(rs) >= 50 else sum(rs) / len(rs)
    level = "none"
    message = "مستقر"
    if r30 < 0 and len(rs) >= 30:
        level = "warn"
        message = "توقّع آخر 30 صفقة سالب"
    if r30 < r50 - 0.15:
        level = "warn" if level == "none" else level
        message = "تراجع: آخر 30 أضعف من آخر 50"
    if r30 < 0 and r50 < 0:
        level = "critical"
        message = "تدهور: آخر 30 و50 صفقة سالبتان"
    return {
        "level": level,
        "message": message,
        "rolling_30": round(r30, 3),
        "rolling_50": round(r50, 3),
    }


def trends_payload(rows: Iterable[dict]) -> dict:
    return {
        "equity": equity_curve(rows),
        "rolling_30": rolling_expectancy(rows, 30),
        "rolling_50": rolling_expectancy(rows, 50),
        "buckets": bucketed_metrics(rows),
        "degradation": degradation_verdict(rows),
    }
