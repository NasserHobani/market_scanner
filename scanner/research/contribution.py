# -*- coding: utf-8 -*-
"""Feature/factor contribution analysis."""
from __future__ import annotations

from typing import Iterable

from scanner.tracking import LOST, WON, summarize

FACTOR_LABELS = {
    "htf": "الفريم الأعلى",
    "candles": "نماذج الشموع",
    "pattern": "النموذج السعري",
    "elliott": "موجات إليوت",
    "confluence": "عناصر الالتقاء",
    "price_action": "حركة السعر",
    "score": "الدرجة",
    "sweep": "اصطياد سيولة",
    "breakout": "اختراق حجمي",
}


def _closed(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("status") in (WON, LOST)]


def _has_factor(row: dict, factor: str) -> bool:
    factors = row.get("factors") or []
    return factor in factors


def factor_contributions(rows: Iterable[dict], *, min_n: int = 3) -> list[dict]:
    """Marginal expectancy: with factor vs without."""
    rows = list(rows)
    closed = _closed(rows)
    if not closed:
        return []
    all_factors: set[str] = set()
    for row in closed:
        for f in (row.get("factors") or []):
            all_factors.add(str(f))

    out = []
    total = len(closed)
    for key in sorted(all_factors):
        with_rows = [r for r in closed if _has_factor(r, key)]
        without_rows = [r for r in closed if not _has_factor(r, key)]
        if len(with_rows) < min_n:
            continue
        sw = summarize(with_rows)
        s_wo = summarize(without_rows) if without_rows else {"expectancy": None}
        exp_with = sw.get("expectancy") or 0.0
        exp_without = s_wo.get("expectancy") if s_wo.get("expectancy") is not None else 0.0
        delta = round(exp_with - exp_without, 3)
        if delta > 0.05:
            verdict = "helps"
        elif delta < -0.05:
            verdict = "hurts"
        else:
            verdict = "neutral"
        label = FACTOR_LABELS.get(key, key)
        out.append({
            "factor": key,
            "label": label,
            "frequency_pct": round(len(with_rows) / total * 100, 1),
            "closed": sw["closed"],
            "expectancy": exp_with,
            "expectancy_without": s_wo.get("expectancy"),
            "marginal_delta": delta,
            "total_r": sw.get("total_r"),
            "verdict": verdict,
        })
    out.sort(key=lambda x: x["marginal_delta"], reverse=True)
    return out
