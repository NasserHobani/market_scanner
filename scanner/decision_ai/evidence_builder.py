# -*- coding: utf-8 -*-
"""Unified evidence model — transforms all layer evidence into one structure."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .context_builder import DECISION_AI_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class UnifiedEvidenceItem:
    """Single evidence item with full provenance."""

    evidence_id: str
    source: str
    label: str
    category: str
    direction: str
    confidence: float
    timestamp: str
    version: str
    facts: tuple[str, ...] = ()
    trace: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "label": self.label,
            "category": self.category,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp,
            "version": self.version,
            "facts": list(self.facts),
            "trace": self.trace,
        }


@dataclass
class UnifiedEvidenceBundle:
    """All evidence from all layers in one model."""

    event_id: str
    items: list[UnifiedEvidenceItem] = field(default_factory=list)
    sources_present: list[str] = field(default_factory=list)
    sources_missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "items": [i.to_dict() for i in self.items],
            "sources_present": list(self.sources_present),
            "sources_missing": list(self.sources_missing),
            "item_count": len(self.items),
        }


class EvidenceBuilder:
    """Transform reasoning, similarity, prediction, and research evidence."""

    def build(self, context: dict[str, Any]) -> UnifiedEvidenceBundle:
        event_id = context.get("event_id") or ""
        items: list[UnifiedEvidenceItem] = []
        present: set[str] = set()
        expected = {"reasoning", "similarity", "prediction", "research", "feature_intelligence"}

        items.extend(self._from_reasoning(context.get("reasoning") or {}))
        if items:
            present.add("reasoning")

        sim_items = self._from_similarity(context.get("similarity") or {})
        items.extend(sim_items)
        if sim_items:
            present.add("similarity")

        pred_items = self._from_prediction(context.get("prediction") or {})
        items.extend(pred_items)
        if pred_items:
            present.add("prediction")

        res_items = self._from_research(context.get("research") or {})
        items.extend(res_items)
        if res_items:
            present.add("research")

        fi_items = self._from_feature_intelligence(
            context.get("feature_intelligence") or {})
        items.extend(fi_items)
        if fi_items:
            present.add("feature_intelligence")

        missing = sorted(expected - present)
        return UnifiedEvidenceBundle(
            event_id=event_id,
            items=items,
            sources_present=sorted(present),
            sources_missing=missing,
        )

    def _from_reasoning(self, reasoning: dict[str, Any]) -> list[UnifiedEvidenceItem]:
        items: list[UnifiedEvidenceItem] = []
        evidence = reasoning.get("evidence") or {}
        raw_items = evidence.get("items") if isinstance(evidence, dict) else evidence
        if not isinstance(raw_items, list):
            return items

        ts = _now()
        for ev in raw_items:
            if not isinstance(ev, dict):
                continue
            items.append(UnifiedEvidenceItem(
                evidence_id=ev.get("evidence_id") or f"ev_{uuid.uuid4().hex[:8]}",
                source="reasoning",
                label=ev.get("label") or "",
                category=ev.get("category") or "unknown",
                direction=ev.get("direction") or "neutral",
                confidence=float(ev.get("confidence") or 0.0),
                timestamp=ts,
                version=DECISION_AI_VERSION,
                facts=tuple(ev.get("facts") or ()),
                trace=ev.get("trace") or "",
            ))
        return items

    def _from_similarity(self, similarity: dict[str, Any]) -> list[UnifiedEvidenceItem]:
        if not similarity.get("available"):
            return []

        items: list[UnifiedEvidenceItem] = []
        ts = _now()
        match_count = similarity.get("match_count") or 0
        conf = min(1.0, match_count / 10.0) if match_count else 0.0

        items.append(UnifiedEvidenceItem(
            evidence_id="ev_similarity_matches",
            source="similarity",
            label="Historical match count",
            category="history",
            direction="supports" if match_count >= 3 else "neutral",
            confidence=conf,
            timestamp=ts,
            version=DECISION_AI_VERSION,
            facts=tuple(similarity.get("historical_evidence") or [
                f"match_count={match_count}",
            ]),
            trace="similarity.match_count",
        ))

        if similarity.get("average_win_rate") is not None:
            wr = similarity["average_win_rate"]
            items.append(UnifiedEvidenceItem(
                evidence_id="ev_similarity_win_rate",
                source="similarity",
                label="Historical win rate",
                category="history",
                direction="supports" if wr >= 50 else "contradicts",
                confidence=min(1.0, conf + 0.1),
                timestamp=ts,
                version=DECISION_AI_VERSION,
                facts=(f"avg_win_rate={wr}",),
                trace="similarity.average_win_rate",
            ))

        return items

    def _from_prediction(self, prediction: dict[str, Any]) -> list[UnifiedEvidenceItem]:
        if not prediction:
            return []

        ts = prediction.get("timestamp") or _now()
        conf = float(prediction.get("confidence") or prediction.get("probability") or 0.0)
        pred_val = prediction.get("prediction")
        direction = "supports" if pred_val and float(pred_val) >= 0.5 else "contradicts"

        return [UnifiedEvidenceItem(
            evidence_id="ev_prediction_signal",
            source="prediction",
            label="Model prediction signal",
            category="prediction",
            direction=direction if conf >= 0.5 else "neutral",
            confidence=conf,
            timestamp=ts,
            version=prediction.get("model_version") or DECISION_AI_VERSION,
            facts=(
                f"prediction={pred_val}",
                f"probability={prediction.get('probability')}",
                f"model_id={prediction.get('model_id')}",
                "disclaimer=analytical_signal_only",
            ),
            trace="prediction.signal",
        )]

    def _from_research(self, research: dict[str, Any]) -> list[UnifiedEvidenceItem]:
        if not research:
            return []

        items: list[UnifiedEvidenceItem] = []
        ts = _now()
        conclusions = research.get("conclusions") or []
        if conclusions:
            items.append(UnifiedEvidenceItem(
                evidence_id="ev_research_conclusions",
                source="research",
                label="Research conclusions",
                category="research",
                direction="supports",
                confidence=0.6,
                timestamp=ts,
                version=research.get("methodology", {}).get("version", DECISION_AI_VERSION)
                if isinstance(research.get("methodology"), dict) else DECISION_AI_VERSION,
                facts=tuple(conclusions[:5]),
                trace="research.conclusions",
            ))

        comparison = research.get("comparison") or {}
        if comparison.get("winner"):
            items.append(UnifiedEvidenceItem(
                evidence_id="ev_research_comparison",
                source="research",
                label="Research comparison winner",
                category="research",
                direction="supports",
                confidence=0.55,
                timestamp=ts,
                version=DECISION_AI_VERSION,
                facts=(f"winner={comparison['winner']}",),
                trace="research.comparison.winner",
            ))

        return items

    def _from_feature_intelligence(self, fi: dict[str, Any]) -> list[UnifiedEvidenceItem]:
        if not fi:
            return []

        items: list[UnifiedEvidenceItem] = []
        ts = fi.get("created_at") or _now()
        summary = fi.get("summary") or fi.get("report", {}).get("summary") or {}
        top = summary.get("top_feature")
        if top:
            items.append(UnifiedEvidenceItem(
                evidence_id="ev_feature_top",
                source="feature_intelligence",
                label="Top ranked feature",
                category="feature",
                direction="supports",
                confidence=0.5,
                timestamp=ts,
                version=fi.get("version") or DECISION_AI_VERSION,
                facts=(f"top_feature={top}",),
                trace="feature_intelligence.ranking",
            ))

        ranking = fi.get("ranking") or []
        if ranking and isinstance(ranking, list):
            top_rank = ranking[0] if ranking else {}
            if isinstance(top_rank, dict) and top_rank.get("composite_score"):
                items.append(UnifiedEvidenceItem(
                    evidence_id="ev_feature_composite",
                    source="feature_intelligence",
                    label="Feature composite score",
                    category="feature",
                    direction="supports",
                    confidence=min(1.0, float(top_rank["composite_score"])),
                    timestamp=ts,
                    version=fi.get("version") or DECISION_AI_VERSION,
                    facts=(f"feature={top_rank.get('feature')}",
                           f"score={top_rank.get('composite_score')}"),
                    trace="feature_intelligence.composite",
                ))

        return items
