# -*- coding: utf-8 -*-
"""Contradiction detection — opposing evidence pairs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evidence import Evidence, EvidenceBundle, EvidenceCategory, EvidenceDirection


@dataclass(frozen=True)
class Contradiction:
    """Traceable conflict between two evidence items."""

    contradiction_id: str
    summary: str
    supporting_label: str
    contradicting_label: str
    supporting_id: str
    contradicting_id: str
    severity: str
    categories: tuple[str, ...] = ()
    trace: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "summary": self.summary,
            "supporting_label": self.supporting_label,
            "contradicting_label": self.contradicting_label,
            "supporting_id": self.supporting_id,
            "contradicting_id": self.contradicting_id,
            "severity": self.severity,
            "categories": list(self.categories),
            "trace": self.trace,
        }


@dataclass
class ContradictionReport:
    items: list[Contradiction] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"count": len(self.items), "items": [c.to_dict() for c in self.items]}


# Rule-based contradiction patterns (category pairs + narrative templates)
_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "trend_vs_momentum",
        "if_supports": EvidenceCategory.TREND.value,
        "if_contradicts": EvidenceCategory.MOMENTUM.value,
        "summary": "Trend supports the trade BUT momentum diverges",
        "severity": "high",
    },
    {
        "id": "volume_vs_structure",
        "if_supports": EvidenceCategory.VOLUME.value,
        "if_contradicts": EvidenceCategory.STRUCTURE.value,
        "summary": "Strong volume BUT weak market structure",
        "severity": "medium",
    },
    {
        "id": "trend_vs_risk",
        "if_supports": EvidenceCategory.TREND.value,
        "if_contradicts": EvidenceCategory.RISK.value,
        "summary": "Trending market BUT price near major resistance/supply",
        "severity": "high",
    },
    {
        "id": "regime_vs_history",
        "if_supports": EvidenceCategory.REGIME.value,
        "if_contradicts": EvidenceCategory.HISTORY.value,
        "summary": "Favourable regime BUT historical expectancy is negative",
        "severity": "medium",
    },
    {
        "id": "confluence_vs_risk",
        "if_supports": EvidenceCategory.CONFLUENCE.value,
        "if_contradicts": EvidenceCategory.RISK.value,
        "summary": "Confluence aligns BUT risk location is unfavourable",
        "severity": "medium",
    },
]


class ContradictionEngine:
    """Identifies contradictions from evidence bundle — no black box."""

    def analyze(self, bundle: EvidenceBundle) -> ContradictionReport:
        supports = {e.category: e for e in bundle.supporting()}
        contradicts = {e.category: e for e in bundle.contradicting()}
        found: list[Contradiction] = []

        for pattern in _PATTERNS:
            sup_cat = pattern["if_supports"]
            con_cat = pattern["if_contradicts"]
            sup = supports.get(sup_cat)
            con = contradicts.get(con_cat)
            if sup and con:
                found.append(Contradiction(
                    contradiction_id=f"cx_{pattern['id']}",
                    summary=pattern["summary"],
                    supporting_label=sup.label,
                    contradicting_label=con.label,
                    supporting_id=sup.evidence_id,
                    contradicting_id=con.evidence_id,
                    severity=pattern["severity"],
                    categories=(sup_cat, con_cat),
                    trace=f"{sup.trace} vs {con.trace}",
                ))

        # Direct contradicting evidence on same axis (trend bullish + bearish momentum)
        for e in bundle.contradicting():
            if e.category == EvidenceCategory.MOMENTUM.value:
                trend = supports.get(EvidenceCategory.TREND.value)
                if trend and not any(c.contradiction_id == "cx_trend_vs_momentum" for c in found):
                    found.append(Contradiction(
                        contradiction_id="cx_momentum_direct",
                        summary="Bullish trend BUT bearish momentum/divergence",
                        supporting_label=trend.label,
                        contradicting_label=e.label,
                        supporting_id=trend.evidence_id,
                        contradicting_id=e.evidence_id,
                        severity="high",
                        categories=(EvidenceCategory.TREND.value, EvidenceCategory.MOMENTUM.value),
                        trace=f"{trend.trace} vs {e.trace}",
                    ))

        return ContradictionReport(items=found)
