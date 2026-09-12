# -*- coding: utf-8 -*-
"""Decision Package — the only input an LLM may receive.

Strongly typed, deterministic, and free of raw market data.
No OHLC, candles, DataFrames, CSV, or raw indicators.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

AI_ADVISOR_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class EvidenceRef:
    """A single groundable fact inside the Decision Package."""

    evidence_id: str
    section: str
    field: str
    label: str
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "section": self.section,
            "field": self.field,
            "label": self.label,
            "value": self.value,
        }


@dataclass(frozen=True)
class DecisionPackage:
    """Immutable, deterministic package sent to the LLM advisor.

    Every field is a pre-computed summary from platform layers.
    The LLM never sees anything outside this structure.
    """

    package_id: str
    event_id: str
    trade: dict[str, Any] = field(default_factory=dict)
    market_context: dict[str, Any] = field(default_factory=dict)
    knowledge_summary: dict[str, Any] = field(default_factory=dict)
    research_summary: dict[str, Any] = field(default_factory=dict)
    similarity_summary: dict[str, Any] = field(default_factory=dict)
    prediction_summary: dict[str, Any] = field(default_factory=dict)
    feature_intelligence: dict[str, Any] = field(default_factory=dict)
    optimization_summary: dict[str, Any] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    evidence_index: tuple[EvidenceRef, ...] = ()
    schema_version: str = AI_ADVISOR_VERSION
    built_at: str = ""
    shadow_mode: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "event_id": self.event_id,
            "trade": dict(self.trade),
            "market_context": dict(self.market_context),
            "knowledge_summary": dict(self.knowledge_summary),
            "research_summary": dict(self.research_summary),
            "similarity_summary": dict(self.similarity_summary),
            "prediction_summary": dict(self.prediction_summary),
            "feature_intelligence": dict(self.feature_intelligence),
            "optimization_summary": dict(self.optimization_summary),
            "statistics": dict(self.statistics),
            "risk": dict(self.risk),
            "confidence": dict(self.confidence),
            "decision": dict(self.decision),
            "execution_metadata": dict(self.execution_metadata),
            "evidence_index": [e.to_dict() for e in self.evidence_index],
            "schema_version": self.schema_version,
            "built_at": self.built_at or _now(),
            "shadow_mode": self.shadow_mode,
        }

    def evidence_ids(self) -> set[str]:
        return {e.evidence_id for e in self.evidence_index}

    def allowed_sections(self) -> set[str]:
        return {
            "trade", "market_context", "knowledge_summary",
            "research_summary", "similarity_summary", "prediction_summary",
            "feature_intelligence", "optimization_summary",
            "statistics", "risk", "confidence", "decision",
            "execution_metadata",
        }


class DecisionPackageBuilder:
    """Assemble a Decision Package from deterministic layer summaries."""

    _FORBIDDEN_KEYS = frozenset({
        "ohlc", "candles", "dataframe", "df", "csv", "raw_indicators",
        "open", "high", "low", "close", "volume_series",
    })

    def build(self, *,
              event_id: str,
              knowledge_context: dict[str, Any] | None = None,
              reasoning_review: dict[str, Any] | None = None,
              similarity_context: dict[str, Any] | None = None,
              research_report: dict[str, Any] | None = None,
              feature_analysis: dict[str, Any] | None = None,
              prediction: dict[str, Any] | None = None,
              optimization: dict[str, Any] | None = None,
              strategy_statistics: dict[str, Any] | None = None,
              guardrails: dict[str, Any] | None = None,
              fused_confidence: dict[str, Any] | None = None) -> DecisionPackage:
        kctx = self._sanitize(knowledge_context or {})
        reasoning = reasoning_review or {}
        reco = kctx.get("recommendation_snapshot") or {}
        market = kctx.get("market_snapshot") or {}

        trade = self._build_trade(kctx, reasoning)
        market_context = self._build_market_context(kctx)
        knowledge_summary = self._build_knowledge_summary(kctx)
        research_summary = self._build_research_summary(research_report)
        similarity_summary = self._build_similarity_summary(similarity_context)
        prediction_summary = self._build_prediction_summary(prediction)
        feature_intel = self._build_feature_intelligence(feature_analysis)
        optimization_summary = self._build_optimization_summary(optimization)
        statistics = self._build_statistics(strategy_statistics or kctx.get("strategy_statistics"))
        risk = self._build_risk(guardrails, reasoning)
        confidence = self._build_confidence(fused_confidence, reasoning, prediction)
        decision = self._build_decision(reasoning, reco)
        execution_metadata = {
            "event_id": event_id,
            "symbol": trade.get("symbol", ""),
            "market": trade.get("market", ""),
            "timeframe": trade.get("timeframe", ""),
            "shadow_mode": True,
            "advisor_role": "reviewer",
            "platform_decides": True,
        }

        sections = {
            "trade": trade,
            "market_context": market_context,
            "knowledge_summary": knowledge_summary,
            "research_summary": research_summary,
            "similarity_summary": similarity_summary,
            "prediction_summary": prediction_summary,
            "feature_intelligence": feature_intel,
            "optimization_summary": optimization_summary,
            "statistics": statistics,
            "risk": risk,
            "confidence": confidence,
            "decision": decision,
            "execution_metadata": execution_metadata,
        }
        evidence_index = tuple(self._index_evidence(sections, reasoning))

        package_id = _stable_id("dpkg", {"event_id": event_id, **sections})

        return DecisionPackage(
            package_id=package_id,
            event_id=event_id,
            trade=trade,
            market_context=market_context,
            knowledge_summary=knowledge_summary,
            research_summary=research_summary,
            similarity_summary=similarity_summary,
            prediction_summary=prediction_summary,
            feature_intelligence=feature_intel,
            optimization_summary=optimization_summary,
            statistics=statistics,
            risk=risk,
            confidence=confidence,
            decision=decision,
            execution_metadata=execution_metadata,
            evidence_index=evidence_index,
            built_at=_now(),
        )

  # ── Section builders ─────────────────────────────────────────────────────

    def _build_trade(self, kctx: dict, reasoning: dict) -> dict[str, Any]:
        reco = kctx.get("recommendation_snapshot") or {}
        return {
            "symbol": kctx.get("symbol") or reco.get("symbol") or "",
            "market": kctx.get("market") or "",
            "timeframe": kctx.get("timeframe") or "",
            "action": reasoning.get("action") or reco.get("action") or "",
            "direction": reasoning.get("direction") or reco.get("side") or "",
            "grade": reco.get("grade") or "",
            "recommendation_confidence": reco.get("confidence"),
        }

    def _build_market_context(self, kctx: dict) -> dict[str, Any]:
        snap = kctx.get("market_snapshot") or {}
        env = kctx.get("market_environment") or {}
        return {
            "trend_direction": snap.get("trend_direction"),
            "regime": env.get("regime"),
            "breadth_pct": env.get("breadth_pct"),
            "volatility_regime": snap.get("volatility_regime") or env.get("volatility_regime"),
        }

    def _build_knowledge_summary(self, kctx: dict) -> dict[str, Any]:
        feat = kctx.get("feature_snapshot") or {}
        return {
            "final_grade": feat.get("final_grade"),
            "final_score": feat.get("final_score"),
            "factor_count": feat.get("factor_count"),
            "memory_gaps": kctx.get("memory_gaps") or [],
        }

    def _build_research_summary(self, report: dict | None) -> dict[str, Any]:
        if not report:
            return {"available": False}
        return {
            "available": True,
            "hypothesis": report.get("hypothesis"),
            "verdict": report.get("verdict"),
            "p_value": report.get("p_value"),
            "effect_size": report.get("effect_size"),
            "sample_size": report.get("sample_size"),
            "confidence_interval": report.get("confidence_interval"),
        }

    def _build_similarity_summary(self, ctx: dict | None) -> dict[str, Any]:
        if not ctx:
            return {"available": False}
        return {
            "available": bool(ctx.get("available", ctx.get("match_count"))),
            "match_count": ctx.get("match_count"),
            "average_win_rate": ctx.get("average_win_rate"),
            "average_r": ctx.get("average_r"),
            "warnings": ctx.get("historical_warnings") or [],
        }

    def _build_prediction_summary(self, pred: dict | None) -> dict[str, Any]:
        if not pred:
            return {"available": False}
        return {
            "available": True,
            "probability": pred.get("probability"),
            "confidence": pred.get("confidence"),
            "model_id": pred.get("model_id"),
            "model_version": pred.get("model_version"),
            "direction": pred.get("direction") or pred.get("prediction"),
        }

    def _build_feature_intelligence(self, analysis: dict | None) -> dict[str, Any]:
        if not analysis:
            return {"available": False}
        return {
            "available": True,
            "drift_detected": analysis.get("drift_detected", False),
            "top_features": (analysis.get("top_features") or [])[:5],
            "quality_score": analysis.get("quality_score"),
        }

    def _build_optimization_summary(self, opt: dict | None) -> dict[str, Any]:
        if not opt:
            return {"available": False}
        return {
            "available": True,
            "best_expectancy": opt.get("best_expectancy"),
            "accepted_strategies": opt.get("accepted_count"),
            "rejected_strategies": opt.get("rejected_count"),
            "walk_forward_pass": opt.get("walk_forward_pass"),
        }

    def _build_statistics(self, stats: dict | None) -> dict[str, Any]:
        if not stats:
            return {"available": False}
        return {
            "available": True,
            "closed_trades": stats.get("closed_trades") or stats.get("closed"),
            "win_rate": stats.get("win_rate"),
            "expectancy": stats.get("expectancy"),
            "profit_factor": stats.get("profit_factor"),
            "reliable": stats.get("reliable", False),
        }

    def _build_risk(self, guardrails: dict | None, reasoning: dict) -> dict[str, Any]:
        contradictions = (reasoning.get("contradictions") or {}).get("items") or []
        warnings = reasoning.get("warnings") or []
        return {
            "guardrail_passed": (guardrails or {}).get("passed", True),
            "violations": (guardrails or {}).get("violations") or [],
            "contradiction_count": len(contradictions),
            "warning_count": len(warnings),
            "warnings": warnings[:5],
        }

    def _build_confidence(self, fused: dict | None, reasoning: dict,
                          prediction: dict | None) -> dict[str, Any]:
        return {
            "fused_score": (fused or {}).get("overall"),
            "fused_components": (fused or {}).get("components") or {},
            "reasoning_confidence": reasoning.get("engine_confidence"),
            "agreement_score": reasoning.get("agreement_score"),
            "prediction_confidence": (prediction or {}).get("confidence"),
        }

    def _build_decision(self, reasoning: dict, reco: dict) -> dict[str, Any]:
        return {
            "verdict": reasoning.get("verdict"),
            "action": reasoning.get("action") or reco.get("action"),
            "direction": reasoning.get("direction") or reco.get("side"),
            "platform_authority": True,
            "advisor_may_override": False,
        }

    def _index_evidence(self, sections: dict[str, Any],
                        reasoning: dict) -> list[EvidenceRef]:
        refs: list[EvidenceRef] = []
        seq = 0

        def add(section: str, field: str, label: str, value: Any) -> None:
            nonlocal seq
            if value is None or value == "" or value == []:
                return
            seq += 1
            refs.append(EvidenceRef(
                evidence_id=f"ev_{seq:03d}",
                section=section,
                field=field,
                label=label,
                value=value,
            ))

        for section, data in sections.items():
            if not isinstance(data, dict):
                continue
            for field, value in data.items():
                if field in ("available",) and value is False:
                    continue
                if isinstance(value, (str, int, float, bool)):
                    add(section, field, f"{section}.{field}", value)

        for item in (reasoning.get("evidence") or {}).get("items") or []:
            eid = item.get("evidence_id") or f"ev_reason_{seq + 1:03d}"
            refs.append(EvidenceRef(
                evidence_id=eid,
                section="reasoning",
                field=item.get("source") or "evidence",
                label=item.get("label") or eid,
                value=item.get("facts") or item.get("direction"),
            ))

        return refs

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Strip forbidden raw-market keys recursively."""
        clean: dict[str, Any] = {}
        for key, value in data.items():
            if key.lower() in self._FORBIDDEN_KEYS:
                continue
            if isinstance(value, dict):
                clean[key] = self._sanitize(value)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                clean[key] = [self._sanitize(v) for v in value]
            else:
                clean[key] = value
        return clean
