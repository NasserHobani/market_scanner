# -*- coding: utf-8 -*-
"""Map evidence_id prefixes to platform deep-links."""
from __future__ import annotations

from typing import Any

_SECTION_ROUTES: dict[str, str] = {
    "similarity": "/ai/?tab=reviews&section=similarity",
    "prediction": "/ai/?tab=prediction",
    "research": "/research/",
    "knowledge": "/ai/?tab=overview",
    "reasoning": "/ai/?tab=decision",
    "decision_ai": "/ai/?tab=decision",
    "feature_intelligence": "/ai/?tab=features",
    "optimization": "/optimization/",
    "recommendation": "/scanner/",
}

_PREFIX_MAP: list[tuple[str, str]] = [
    ("ev_similarity", "similarity"),
    ("ev_prediction", "prediction"),
    ("ev_research", "research"),
    ("ev_knowledge", "knowledge"),
    ("ev_reasoning", "reasoning"),
    ("ev_decision", "decision_ai"),
    ("ev_feature", "feature_intelligence"),
    ("ev_optim", "optimization"),
    ("ev_reco", "recommendation"),
]


def resolve_section(evidence_id: str, section: str = "") -> str:
    if section and section in _SECTION_ROUTES:
        return section
    eid = (evidence_id or "").lower()
    for prefix, sec in _PREFIX_MAP:
        if eid.startswith(prefix):
            return sec
    if section:
        return section
    return "reasoning"


def evidence_link(evidence_id: str, *, section: str = "",
                  symbol: str = "", market: str = "crypto",
                  timeframe: str = "4h") -> dict[str, Any]:
    """Return link metadata for a clickable evidence citation."""
    sec = resolve_section(evidence_id, section)
    base = _SECTION_ROUTES.get(sec, "/ai/?tab=reviews")
    if symbol and market:
        sym_url = f"/symbol/{market}/{symbol}/?tf={timeframe}"
        if sec in ("similarity", "knowledge", "reasoning", "recommendation"):
            href = sym_url
        else:
            href = base
    else:
        href = base
    return {
        "evidence_id": evidence_id,
        "section": sec,
        "href": href,
        "label": _section_label(sec),
    }


def enrich_evidence_list(items: list[dict[str, Any]] | None, *,
                        symbol: str = "", market: str = "",
                        timeframe: str = "") -> list[dict[str, Any]]:
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        eid = item.get("evidence_id", "")
        sec = item.get("section", "")
        link = evidence_link(eid, section=sec, symbol=symbol, market=market,
                             timeframe=timeframe)
        out.append({**item, **link})
    return out


def _section_label(section: str) -> str:
    labels = {
        "similarity": "محرك التشابه",
        "prediction": "التنبؤ",
        "research": "البحث",
        "knowledge": "المعرفة",
        "reasoning": "التفكير",
        "decision_ai": "قرار الذكاء",
        "feature_intelligence": "جودة الميزات",
        "optimization": "التحسين",
        "recommendation": "التوصية",
    }
    return labels.get(section, section)
