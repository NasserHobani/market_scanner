# -*- coding: utf-8 -*-
"""Unified Decision Package — full platform context for AI Advisor."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .decision_package import EvidenceRef, _stable_id

UNIFIED_PACKAGE_VERSION = "2.0.0"

_FORBIDDEN_KEYS = frozenset({
    "ohlc", "candles", "dataframe", "df", "csv", "raw_indicators",
    "open", "high", "low", "close", "volume_series",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvidenceTrace:
    """Traceable evidence item with source layer metadata."""

    evidence_id: str
    source_layer: str
    section: str
    field: str
    label: str
    value: Any
    timestamp: str = ""
    confidence: float | None = None
    reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_layer": self.source_layer,
            "section": self.section,
            "field": self.field,
            "label": self.label,
            "value": self.value,
            "timestamp": self.timestamp or _now(),
            "confidence": self.confidence,
            "reference": self.reference,
        }


@dataclass(frozen=True)
class UnifiedDecisionPackage:
    """Immutable unified package — single source of truth for AI Advisor."""

    package_id: str
    event_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    recommendation: dict[str, Any] = field(default_factory=dict)
    knowledge: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)
    similarity: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    feature_intelligence: dict[str, Any] = field(default_factory=dict)
    feature_snapshot: dict[str, Any] = field(default_factory=dict)
    prediction: dict[str, Any] = field(default_factory=dict)
    optimization: dict[str, Any] = field(default_factory=dict)
    decision_ai: dict[str, Any] = field(default_factory=dict)
    evidence_index: tuple[EvidenceTrace, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = UNIFIED_PACKAGE_VERSION
    built_at: str = ""
    shadow_mode: bool = True

    # Legacy-compatible accessors for advisor engine / memory
    @property
    def trade(self) -> dict[str, Any]:
        return {
            "symbol": self.metadata.get("symbol", ""),
            "market": self.metadata.get("market", ""),
            "timeframe": self.metadata.get("timeframe", ""),
            "trade_id": self.metadata.get("trade_id", ""),
            "action": self.recommendation.get("action", ""),
            "direction": self.recommendation.get("direction", ""),
            "grade": self.recommendation.get("grade", ""),
            "recommendation_confidence": self.recommendation.get("confidence"),
        }

    @property
    def risk(self) -> dict[str, Any]:
        guardrails = self.decision_ai.get("guardrails") or {}
        warnings = list(self.reasoning.get("warnings") or [])
        contradictions = self.reasoning.get("contradictions") or []
        if isinstance(contradictions, dict):
            contradictions = contradictions.get("items") or []
        return {
            "guardrail_passed": guardrails.get("passed", True),
            "violations": guardrails.get("violations") or [],
            "contradiction_count": len(contradictions),
            "warning_count": len(warnings),
            "warnings": warnings[:5],
        }

    @property
    def decision(self) -> dict[str, Any]:
        return {
            "verdict": self.reasoning.get("verdict"),
            "action": self.recommendation.get("action"),
            "direction": self.recommendation.get("direction"),
            "platform_authority": True,
            "advisor_may_override": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "event_id": self.event_id,
            "metadata": dict(self.metadata),
            "recommendation": dict(self.recommendation),
            "knowledge": dict(self.knowledge),
            "reasoning": dict(self.reasoning),
            "similarity": dict(self.similarity),
            "research": dict(self.research),
            "feature_intelligence": dict(self.feature_intelligence),
            "feature_snapshot": dict(self.feature_snapshot),
            "prediction": dict(self.prediction),
            "optimization": dict(self.optimization),
            "decision_ai": dict(self.decision_ai),
            "evidence_index": [e.to_dict() for e in self.evidence_index],
            "diagnostics": dict(self.diagnostics),
            "schema_version": self.schema_version,
            "built_at": self.built_at or _now(),
            "shadow_mode": self.shadow_mode,
        }

    def evidence_ids(self) -> set[str]:
        return {e.evidence_id for e in self.evidence_index}

    def allowed_sections(self) -> set[str]:
        return {
            "metadata", "recommendation", "knowledge", "reasoning",
            "similarity", "research", "feature_intelligence", "feature_snapshot",
            "prediction", "optimization", "decision_ai",
            "trade", "risk", "decision", "reasoning",
        }

    def legacy_evidence_refs(self) -> tuple[EvidenceRef, ...]:
        return tuple(
            EvidenceRef(
                evidence_id=e.evidence_id,
                section=e.section,
                field=e.field,
                label=e.label,
                value=e.value,
            )
            for e in self.evidence_index
        )


class UnifiedPackageBuilder:
    """Assemble UnifiedDecisionPackage from platform layer outputs."""

    def build(self, *,
              event_id: str,
              metadata: dict[str, Any] | None = None,
              recommendation: dict[str, Any] | None = None,
              knowledge_context: dict[str, Any] | None = None,
              reasoning_review: dict[str, Any] | None = None,
              similarity_context: dict[str, Any] | None = None,
              research_report: dict[str, Any] | None = None,
              feature_analysis: dict[str, Any] | None = None,
              feature_snapshot: dict[str, Any] | None = None,
              prediction: dict[str, Any] | None = None,
              optimization: dict[str, Any] | None = None,
              decision_ai: dict[str, Any] | None = None,
              guardrails: dict[str, Any] | None = None,
              fused_confidence: dict[str, Any] | None = None) -> UnifiedDecisionPackage:
        from .layer_adapters import (
            adapt_decision_ai,
            adapt_feature_intelligence,
            adapt_feature_snapshot,
            adapt_knowledge,
            adapt_optimization,
            adapt_prediction,
            adapt_reasoning,
            adapt_recommendation,
            adapt_research,
            adapt_similarity,
        )

        meta = dict(metadata or {})
        kctx = self._sanitize(knowledge_context or {})
        reasoning = reasoning_review or {}
        reco_src = recommendation or kctx.get("recommendation_snapshot") or {}

        meta.setdefault("symbol", kctx.get("symbol") or reco_src.get("symbol", ""))
        meta.setdefault("market", kctx.get("market", ""))
        meta.setdefault("timeframe", kctx.get("timeframe", ""))
        meta.setdefault("event_id", event_id)
        meta.setdefault("timestamp", _now())
        meta.setdefault("version", UNIFIED_PACKAGE_VERSION)

        rec_section = adapt_recommendation(reco_src, kctx, reasoning)
        know_section = adapt_knowledge(kctx)
        reason_section = adapt_reasoning(reasoning)
        sim_section = adapt_similarity(similarity_context)
        res_section = adapt_research(research_report)
        feat_section = adapt_feature_intelligence(feature_analysis)
        snap_section = adapt_feature_snapshot(feature_snapshot)
        pred_section = adapt_prediction(prediction)
        opt_section = adapt_optimization(optimization)
        dai_section = adapt_decision_ai(
            decision_ai, guardrails=guardrails, fused_confidence=fused_confidence,
            reasoning=reasoning,
        )

        sections = {
            "recommendation": rec_section,
            "knowledge": know_section,
            "reasoning": reason_section,
            "similarity": sim_section,
            "research": res_section,
            "feature_intelligence": feat_section,
            "feature_snapshot": snap_section,
            "prediction": pred_section,
            "optimization": opt_section,
            "decision_ai": dai_section,
        }
        evidence_index = tuple(self._index_evidence(sections, reasoning))

        payload = {"event_id": event_id, "metadata": meta, **sections}
        package_id = _stable_id("udpkg", payload)

        return UnifiedDecisionPackage(
            package_id=package_id,
            event_id=event_id,
            metadata=meta,
            recommendation=rec_section,
            knowledge=know_section,
            reasoning=reason_section,
            similarity=sim_section,
            research=res_section,
            feature_intelligence=feat_section,
            feature_snapshot=snap_section,
            prediction=pred_section,
            optimization=opt_section,
            decision_ai=dai_section,
            evidence_index=evidence_index,
            built_at=_now(),
        )

    def _index_evidence(self, sections: dict[str, dict],
                        reasoning: dict) -> list[EvidenceTrace]:
        refs: list[EvidenceTrace] = []
        seq = 0
        layer_map = {
            "recommendation": "recommendation",
            "knowledge": "knowledge",
            "reasoning": "reasoning",
            "similarity": "similarity",
            "research": "research",
            "feature_intelligence": "feature_intelligence",
            "feature_snapshot": "feature_snapshot",
            "prediction": "prediction",
            "optimization": "optimization",
            "decision_ai": "decision_ai",
        }

        def add(section: str, field: str, label: str, value: Any,
                layer: str, confidence: float | None = None,
                reference: str = "") -> None:
            nonlocal seq
            if value is None or value == "" or value == []:
                return
            seq += 1
            refs.append(EvidenceTrace(
                evidence_id=f"ev_{seq:03d}",
                source_layer=layer,
                section=section,
                field=field,
                label=label,
                value=value,
                timestamp=_now(),
                confidence=confidence,
                reference=reference or f"{section}.{field}",
            ))

        for section, data in sections.items():
            layer = layer_map.get(section, section)
            if not isinstance(data, dict):
                continue
            for fld, value in data.items():
                if fld in ("available",) and value is False:
                    continue
                if isinstance(value, (str, int, float, bool)):
                    add(section, fld, f"{section}.{fld}", value, layer)
                elif isinstance(value, list) and value and isinstance(value[0], str):
                    add(section, fld, f"{section}.{fld}", value[:5], layer)

        for item in (reasoning.get("evidence") or {}).get("items") or []:
            eid = item.get("evidence_id") or f"ev_reason_{seq + 1:03d}"
            refs.append(EvidenceTrace(
                evidence_id=eid,
                source_layer="reasoning",
                section="reasoning",
                field=item.get("source") or "evidence",
                label=item.get("label") or eid,
                value=item.get("facts") or item.get("direction"),
                timestamp=_now(),
                confidence=item.get("confidence"),
                reference=item.get("trace") or item.get("source") or "",
            ))

        return refs

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if key.lower() in _FORBIDDEN_KEYS:
                continue
            if isinstance(value, dict):
                clean[key] = self._sanitize(value)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                clean[key] = [self._sanitize(v) for v in value]
            else:
                clean[key] = value
        return clean
