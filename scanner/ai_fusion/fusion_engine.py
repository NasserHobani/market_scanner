# -*- coding: utf-8 -*-
"""Fusion orchestrator — package + prediction + LLM + agreement."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from scanner.ai_advisor.unified_package import UnifiedDecisionPackage

from .agreement_analyzer import analyze as analyze_agreement
from .confidence_policy import separate_confidences
from .fusion_policy import apply_policy
from .fusion_result import FusionResult
from .llm_assessment import extract_llm_assessment
from .prediction_adapter import PredictionAdapter


def package_fingerprint(package: UnifiedDecisionPackage) -> str:
    meta = package.metadata or {}
    payload = {
        "package_id": package.package_id,
        "event_id": package.event_id,
        "symbol": meta.get("symbol", ""),
        "timeframe": meta.get("timeframe", ""),
        "schema_version": package.schema_version,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    return f"pkg_{digest}"


class FusionEngine:
    """Multi-layer fusion — observable, advisory, shadow-mode only."""

    def __init__(self, adapter: PredictionAdapter | None = None) -> None:
        self._adapter = adapter or PredictionAdapter()

    def enrich_package_prediction(self, context: dict[str, Any]) -> dict[str, Any]:
        """ACTIVE-only prediction section for UDP."""
        return self._adapter.to_udp_section(context)

    def fuse(self, *,
             package: UnifiedDecisionPackage,
             llm_response: dict[str, Any] | None = None,
             review_id: str = "",
             provider: str = "",
             model: str = "",
             raw_prediction: dict[str, Any] | None = None) -> FusionResult:
        reco = package.recommendation or {}
        platform_action = reco.get("action") or reco.get("direction") or ""
        platform_conf = reco.get("confidence")

        prediction = raw_prediction or package.prediction or {}
        if not prediction.get("available") and raw_prediction is None:
            prediction = {"available": False, "reason": prediction.get("reason", "no_active_model")}

        llm = extract_llm_assessment(llm_response)
        agreement = analyze_agreement(
            platform_action=platform_action,
            prediction=prediction if prediction.get("available") else {"available": False},
            llm_assessment=llm,
            platform_confidence=float(platform_conf) if platform_conf is not None else None,
        )
        policy = apply_policy(agreement)
        conf_sep = separate_confidences(
            recommendation=reco,
            prediction=prediction if prediction.get("available") else {},
            llm_response=llm,
        )

        return FusionResult(
            fusion_state=agreement["fusion_state"],
            platform_action=platform_action,
            platform_confidence=conf_sep.get("platform_confidence"),
            prediction_available=bool(prediction.get("available")),
            prediction=prediction,
            llm_assessment=llm,
            confidence_separation=conf_sep,
            agreement=agreement,
            policy=policy,
            package_fingerprint=package_fingerprint(package),
            review_id=review_id,
            provider=provider,
            model=model,
        )

    def build_history_record(self, fusion: FusionResult, *,
                             package: UnifiedDecisionPackage,
                             metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = package.metadata or {}
        pred = fusion.prediction or {}
        llm = fusion.llm_assessment or {}
        m = metrics or {}
        return {
            "symbol": meta.get("symbol", ""),
            "timeframe": meta.get("timeframe", ""),
            "review_id": fusion.review_id,
            "provider": fusion.provider,
            "model": fusion.model,
            "platform_action": fusion.platform_action,
            "platform_confidence": fusion.platform_confidence,
            "prediction_available": fusion.prediction_available,
            "prediction_model_id": pred.get("model_id"),
            "prediction_probability": pred.get("probability_win"),
            "prediction_label": pred.get("prediction"),
            "llm_agreement": llm.get("agreement"),
            "llm_confidence": llm.get("confidence"),
            "llm_prediction_assessment": llm.get("prediction_assessment"),
            "fusion_state": fusion.fusion_state,
            "advisory": fusion.policy.get("advisory"),
            "evidence_count": len(package.evidence_index or ()),
            "package_fingerprint": fusion.package_fingerprint,
            "latency_ms": m.get("latency_ms"),
            "prompt_tokens": m.get("prompt_tokens"),
            "completion_tokens": m.get("completion_tokens"),
            "total_tokens": m.get("total_tokens"),
            "estimated_cost": m.get("estimated_cost"),
            "escalated": m.get("escalated", False),
            "escalation_reason": m.get("escalation_reason", ""),
        }
