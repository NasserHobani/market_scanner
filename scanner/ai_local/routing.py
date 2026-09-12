# -*- coding: utf-8 -*-
"""Execution routing — claude_only / local_only / local_first / compare."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from scanner.ai_advisor.advisor_service import AIAdvisorService
from scanner.ai_advisor.provider_config import load_config
from scanner.ai_advisor.review import AdvisorReview
from scanner.ai_advisor.unified_package import UnifiedDecisionPackage

from .comparisons import ComparisonStore
from .config import LocalAIConfig, load_local_config
from .history import LocalAIHistory


@dataclass
class ReviewExecutionResult:
    accepted: bool
    review_id: str
    provider_id: str
    model_name: str
    agreement: str = ""
    confidence: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    package_diagnostics: dict[str, Any] = field(default_factory=dict)
    comparison: dict[str, Any] | None = None
    local_review: AdvisorReview | None = None
    claude_review: AdvisorReview | None = None
    escalated: bool = False
    error: str = ""


def package_fingerprint(package: UnifiedDecisionPackage) -> str:
    meta = getattr(package, "metadata", {}) or {}
    payload = {
        "package_id": package.package_id,
        "event_id": package.event_id,
        "symbol": meta.get("symbol", ""),
        "timeframe": meta.get("timeframe", ""),
        "version": getattr(package, "schema_version", "") or getattr(package, "package_version", ""),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    return f"pkg_{digest}"


def _persist_local_review(review: AdvisorReview, metrics: dict[str, Any],
                          package: UnifiedDecisionPackage,
                          *, validation_passed: bool) -> None:
    meta = getattr(package, "metadata", {}) or {}
    LocalAIHistory().append({
        "review_id": review.review_id,
        "provider": review.provider_id,
        "model": review.model_name,
        "symbol": meta.get("symbol", ""),
        "timeframe": meta.get("timeframe", ""),
        "package_fingerprint": package_fingerprint(package),
        "agreement": review.agreement,
        "confidence": review.confidence,
        "latency_ms": metrics.get("latency_ms", 0),
        "prompt_tokens": metrics.get("prompt_tokens", 0),
        "completion_tokens": metrics.get("completion_tokens", 0),
        "total_tokens": metrics.get("total_tokens", 0),
        "validation_passed": validation_passed,
        "grounding_score": metrics.get("grounding_score", 0),
        "hallucination_score": metrics.get("hallucination_score", 0),
    })


def _should_escalate(review: AdvisorReview, metrics: dict[str, Any],
                     local_cfg: LocalAIConfig) -> tuple[bool, str]:
    if not review.accepted:
        if local_cfg.escalate_on_validation_failure:
            return True, "validation_failed"
        return True, "validation_failed"
    if local_cfg.escalate_on_grounding_failure:
        gs = float(metrics.get("grounding_score") or 0)
        if gs < local_cfg.escalate_grounding_below:
            return True, "grounding_low"
    if review.confidence < local_cfg.escalate_min_confidence:
        return True, "confidence_low"
    return False, ""


def _persist_fusion(package: UnifiedDecisionPackage, review: AdvisorReview,
                    metrics: dict[str, Any], *, escalated: bool = False,
                    escalation_reason: str = "") -> dict[str, Any]:
    """Run fusion analysis and append to history — never blocks review."""
    try:
        from scanner.ai_fusion.fusion_engine import FusionEngine
        from scanner.ai_fusion.fusion_history import FusionHistory

        llm_resp = dict(review.raw_response or {})
        llm_resp.setdefault("agreement", review.agreement)
        llm_resp.setdefault("confidence", review.confidence)
        llm_resp.setdefault("reasoning", review.reasoning)
        llm_resp.setdefault("summary", review.summary)
        llm_resp.setdefault("risks", review.risks)
        llm_resp.setdefault("supporting_evidence", [e.to_dict() for e in review.supporting_evidence])
        llm_resp.setdefault("contradicting_evidence", [e.to_dict() for e in review.contradicting_evidence])

        engine = FusionEngine()
        fusion = engine.fuse(
            package=package,
            llm_response=llm_resp,
            review_id=review.review_id,
            provider=review.provider_id,
            model=review.model_name,
        )
        m = dict(metrics)
        m["escalated"] = escalated
        m["escalation_reason"] = escalation_reason
        record = engine.build_history_record(fusion, package=package, metrics=m)
        FusionHistory().append(record)
        return fusion.to_dict()
    except Exception:  # noqa: BLE001
        return {}


def _result_from_review(svc: AIAdvisorService, review: AdvisorReview,
                        package: UnifiedDecisionPackage, *,
                        escalated: bool = False,
                        escalation_reason: str = "") -> ReviewExecutionResult:
    metrics = dict(getattr(svc._engine, "last_call_metrics", {}) or {})
    diag = dict(getattr(svc._engine, "last_package_diagnostics", {}) or {})
    if review.provider_id == "ollama":
        _persist_local_review(review, metrics, package, validation_passed=review.accepted)
    fusion = _persist_fusion(package, review, metrics,
                             escalated=escalated, escalation_reason=escalation_reason)
    return ReviewExecutionResult(
        accepted=review.accepted,
        review_id=review.review_id,
        provider_id=review.provider_id,
        model_name=review.model_name,
        agreement=review.agreement,
        confidence=review.confidence,
        metrics={**metrics, "fusion": fusion},
        package_diagnostics=diag,
        # كانت تُستقبَل ولا تُمرَّر، فيبقى ``escalated`` على False دائماً.
        # وأثره ليس عرضياً: التصعيد من المحلّي إلى Claude لا يُسجَّل، فلا
        # يمكن قياس كم مرّة يعجز النموذج المحلّي — وهو الرقم الذي يقرّر
        # هل يستحقّ نموذج أكبر أم لا.
        escalated=escalated,
    )


def execute_review(svc: AIAdvisorService, layers: dict[str, Any],
                   *, local_cfg: LocalAIConfig | None = None) -> ReviewExecutionResult:
    """Build package once, route per execution mode. Never modifies platform decision."""
    local_cfg = local_cfg or load_local_config()
    cfg = load_config()
    event_id = layers["event_id"]
    layer_kwargs = {k: v for k, v in layers.items() if k != "event_id"}

    package = svc.build_package(event_id, **layer_kwargs)
    fp = package_fingerprint(package)
    mode = local_cfg.execution_mode

    if mode == "claude_only" or not local_cfg.local_enabled:
        review = svc.review(package, provider_id="claude",
                            prompt_version=cfg.prompt_version)
        return _result_from_review(svc, review, package)

    if mode == "local_only":
        try:
            review = svc.review(package, provider_id="ollama",
                                prompt_version=cfg.prompt_version)
            return _result_from_review(svc, review, package)
        except Exception as exc:  # noqa: BLE001
            return ReviewExecutionResult(
                accepted=False, review_id="", provider_id="ollama",
                model_name=local_cfg.local_default_model,
                error=str(exc)[:200],
            )

    if mode == "local_first":
        try:
            local_review = svc.review(package, provider_id="ollama",
                                      prompt_version=cfg.prompt_version)
            local_res = _result_from_review(svc, local_review, package)
            escalate, reason = _should_escalate(local_review, local_res.metrics, local_cfg)
            if not escalate and local_review.accepted:
                return local_res
            if not local_cfg.escalate_on_provider_error and not local_review.accepted:
                return local_res
            claude_review = svc.review(package, provider_id="claude",
                                       prompt_version=cfg.prompt_version)
            out = _result_from_review(svc, claude_review, package,
                                      escalated=True, escalation_reason=reason)
            out.local_review = local_review
            out.claude_review = claude_review
            out.error = reason
            return out
        except Exception as exc:  # noqa: BLE001
            if not local_cfg.escalate_on_provider_error:
                return ReviewExecutionResult(
                    accepted=False, review_id="", provider_id="ollama",
                    model_name=local_cfg.local_default_model, error=str(exc)[:200],
                )
            try:
                claude_review = svc.review(package, provider_id="claude",
                                           prompt_version=cfg.prompt_version)
                out = _result_from_review(svc, claude_review, package,
                                          escalated=True, escalation_reason=str(exc)[:200])
                return out
            except Exception as exc2:  # noqa: BLE001
                return ReviewExecutionResult(
                    accepted=False, review_id="", provider_id="ollama",
                    model_name=local_cfg.local_default_model,
                    error=f"{exc}; escalate failed: {exc2}"[:200],
                )

    if mode == "compare":
        claude_review: AdvisorReview | None = None
        local_review: AdvisorReview | None = None
        claude_metrics: dict[str, Any] = {}
        local_metrics: dict[str, Any] = {}
        errors: list[str] = []

        try:
            claude_review = svc.review(package, provider_id="claude",
                                       prompt_version=cfg.prompt_version)
            claude_metrics = dict(getattr(svc._engine, "last_call_metrics", {}) or {})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"claude: {exc}")

        try:
            local_review = svc.review(package, provider_id="ollama",
                                      prompt_version=cfg.prompt_version)
            local_metrics = dict(getattr(svc._engine, "last_call_metrics", {}) or {})
            if local_review:
                _persist_local_review(local_review, local_metrics, package,
                                      validation_passed=local_review.accepted)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ollama: {exc}")

        meta = getattr(package, "metadata", {}) or {}
        cmp_rec = {
            "package_fingerprint": fp,
            "symbol": meta.get("symbol", ""),
            "timeframe": meta.get("timeframe", ""),
            "claude_review_id": claude_review.review_id if claude_review else "",
            "local_review_id": local_review.review_id if local_review else "",
            "claude_agreement": claude_review.agreement if claude_review else "",
            "local_agreement": local_review.agreement if local_review else "",
            "claude_confidence": claude_review.confidence if claude_review else None,
            "local_confidence": local_review.confidence if local_review else None,
            "claude_latency_ms": claude_metrics.get("latency_ms"),
            "local_latency_ms": local_metrics.get("latency_ms"),
            "claude_tokens": claude_metrics.get("total_tokens"),
            "local_tokens": local_metrics.get("total_tokens"),
            "claude_estimated_cost": claude_metrics.get("estimated_cost"),
            "errors": errors,
        }
        cid = ComparisonStore().save(cmp_rec)

        primary = claude_review if claude_review and claude_review.accepted else local_review
        if primary:
            out = _result_from_review(svc, primary, package)
            out.comparison = {**cmp_rec, "comparison_id": cid}
            out.claude_review = claude_review
            out.local_review = local_review
            if claude_review and claude_review.review_id != primary.review_id:
                _persist_fusion(package, claude_review, claude_metrics)
            if local_review and local_review.review_id != primary.review_id:
                _persist_fusion(package, local_review, local_metrics)
            return out

        return ReviewExecutionResult(
            accepted=False,
            review_id="",
            provider_id="compare",
            model_name="",
            comparison={**cmp_rec, "comparison_id": cid},
            claude_review=claude_review,
            local_review=local_review,
            error="; ".join(errors) or "compare failed",
        )

    review = svc.review(package, provider_id="claude", prompt_version=cfg.prompt_version)
    return _result_from_review(svc, review, package)
