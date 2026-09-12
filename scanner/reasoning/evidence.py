# -*- coding: utf-8 -*-
"""Evidence primitives — structured facts with provenance."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceDirection(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    MISSING = "missing"


class EvidenceCategory(str, Enum):
    TREND = "trend"
    REGIME = "regime"
    LIQUIDITY = "liquidity"
    VOLUME = "volume"
    STRUCTURE = "structure"
    MOMENTUM = "momentum"
    RISK = "risk"
    CONFLUENCE = "confluence"
    HISTORY = "history"
    RECOMMENDATION = "recommendation"
    PATTERN = "pattern"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Evidence:
    """Single reasoning fact derived from knowledge — not a raw indicator."""

    evidence_id: str
    label: str
    category: str
    direction: str
    weight: float
    strength: str
    confidence: float
    source: str
    facts: tuple[str, ...] = ()
    trace: str = ""
    raw_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "label": self.label,
            "category": self.category,
            "direction": self.direction,
            "weight": round(self.weight, 4),
            "strength": self.strength,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "facts": list(self.facts),
            "trace": self.trace,
            "raw_key": self.raw_key,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Evidence:
        return cls(
            evidence_id=row["evidence_id"],
            label=row["label"],
            category=row["category"],
            direction=row["direction"],
            weight=float(row.get("weight") or 0.0),
            strength=row.get("strength") or EvidenceStrength.UNKNOWN.value,
            confidence=float(row.get("confidence") or 0.0),
            source=row.get("source") or "unknown",
            facts=tuple(row.get("facts") or ()),
            trace=row.get("trace") or "",
            raw_key=row.get("raw_key") or "",
        )


@dataclass
class EvidenceBundle:
    """Collected evidence for one reasoning pass."""

    items: list[Evidence] = field(default_factory=list)
    event_id: str = ""

    def supporting(self) -> list[Evidence]:
        return [e for e in self.items if e.direction == EvidenceDirection.SUPPORTS.value]

    def contradicting(self) -> list[Evidence]:
        return [e for e in self.items if e.direction == EvidenceDirection.CONTRADICTS.value]

    def neutral(self) -> list[Evidence]:
        return [e for e in self.items if e.direction == EvidenceDirection.NEUTRAL.value]

    def missing(self) -> list[Evidence]:
        return [e for e in self.items if e.direction == EvidenceDirection.MISSING.value]

    def by_category(self, category: str) -> list[Evidence]:
        return [e for e in self.items if e.category == category]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "count": len(self.items),
            "supporting": len(self.supporting()),
            "contradicting": len(self.contradicting()),
            "items": [e.to_dict() for e in self.items],
        }
