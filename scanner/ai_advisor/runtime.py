# -*- coding: utf-8 -*-
"""AI Advisor runtime — invokes review during scan/recommendation cycles."""
from __future__ import annotations

import logging
from typing import Any

from .advisor_logging import log_error, log_runtime
from .advisor_service import AIAdvisorService
from .layer_collectors import collect_platform_layers
from .provider_config import load_config, effective_provider_id
from scanner.ai_local.config import load_local_config
from scanner.ai_local.routing import execute_review
from .runtime_history import AdvisorRuntimeHistory
from .runtime_state import AdvisorRuntimeState

log = logging.getLogger("scanner.ai_advisor.runtime")


def _runtime_log(message: str) -> None:
    log.info("advisor_runtime: %s", message)
    log_runtime(message)


def is_advisor_enabled() -> bool:
    cfg = load_config()
    if not cfg.shadow_mode:
        return False
    local = load_local_config()
    mode = local.execution_mode if local.local_enabled else "claude_only"

    if mode in ("local_only", "local_first"):
        return local.local_enabled and local.ollama_enabled
    if mode == "compare":
        claude_ok = cfg.api_key_configured and cfg.claude_enabled
        local_ok = local.local_enabled and local.ollama_enabled
        return claude_ok or local_ok

    pid = effective_provider_id(cfg)
    if pid == "mock":
        return False
    if pid == "claude" and not cfg.api_key_configured:
        return False
    return True


def build_layer_outputs(*, symbol: str, market: str, timeframe: str,
                        recommendation: dict[str, Any] | None,
                        row: dict[str, Any] | None = None,
                        trade_id: str = "",
                        scan_id: str = "",
                        strategy: str = "default") -> dict[str, Any]:
    """Collect full platform context for unified package."""
    cfg = load_config()
    return collect_platform_layers(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        recommendation=recommendation,
        row=row,
        trade_id=trade_id,
        scan_id=scan_id,
        strategy=strategy,
        provider=effective_provider_id(cfg),
    )


def review_recommendation(*,
                          symbol: str,
                          market: str,
                          timeframe: str,
                          recommendation: dict[str, Any] | None,
                          row: dict[str, Any] | None = None,
                          trade_id: str = "",
                          scan_id: str = "",
                          service: AIAdvisorService | None = None,
                          context_profile: str = "fast") -> dict[str, Any] | None:
    """Run AI Advisor review for one recommendation. Never raises."""
    state = AdvisorRuntimeState()
    cfg = load_config()

    if not is_advisor_enabled():
        return None

    local = load_local_config()
    if local.execution_mode == "claude_only" or not local.local_enabled:
        if cfg.default_provider == "claude" and not cfg.api_key_configured:
            current = state.load()
            if int(current.get("successful_reviews") or 0) < 1:
                state.set_status("disconnected")
            return None

    _runtime_log("AI Advisor Started")
    svc = service or AIAdvisorService()

    try:
        layers = build_layer_outputs(
            symbol=symbol, market=market, timeframe=timeframe,
            recommendation=recommendation, row=row,
            trade_id=trade_id, scan_id=scan_id,
        )
        # Compact context profile for automatic/manual paths
        meta = dict(layers.get("metadata") or {})
        meta["context_profile"] = context_profile or "fast"
        layers["metadata"] = meta
        layers["context_profile"] = context_profile or "fast"
        _runtime_log("Decision Package Built")

        result = execute_review(svc, layers, local_cfg=local)
        review_label = result.provider_id or "advisor"
        _runtime_log(f"{review_label} Invoked")

        diagnostics = result.package_diagnostics or getattr(svc._engine, "last_package_diagnostics", {}) or {}

        if not result.accepted:
            state.record_failure(result.error or "validation failed")
            log_error(provider=result.provider_id or cfg.default_provider,
                      error_type="validation", detail="review rejected")
            _runtime_log("Validation Failed — review not saved")
            out: dict[str, Any] = {
                "accepted": False,
                "review_id": result.review_id,
                "error": result.error,
            }
            if result.comparison:
                out["comparison"] = result.comparison
            return out

        metrics = result.metrics or getattr(svc._engine, "last_call_metrics", {}) or {}
        _runtime_log("Grounding Passed")
        _runtime_log("History Saved")
        _runtime_log("Dashboard Updated")

        agreement = result.agreement
        confidence = result.confidence
        if result.comparison and not agreement:
            if result.claude_review:
                agreement = result.claude_review.agreement
                confidence = result.claude_review.confidence
            elif result.local_review:
                agreement = result.local_review.agreement
                confidence = result.local_review.confidence

        state.record_success(
            provider=result.provider_id,
            model=result.model_name,
            review_id=result.review_id,
            latency_ms=metrics.get("latency_ms"),
            prompt_tokens=metrics.get("prompt_tokens"),
            completion_tokens=metrics.get("completion_tokens"),
            total_tokens=metrics.get("total_tokens"),
            estimated_cost=metrics.get("estimated_cost"),
            grounding_score=metrics.get("grounding_score"),
            hallucination_score=metrics.get("hallucination_score"),
            agreement=agreement,
            confidence=confidence,
            package_diagnostics=diagnostics,
        )
        payload: dict[str, Any] = {
            "accepted": True,
            "review_id": result.review_id,
            "metrics": metrics,
            "package_diagnostics": diagnostics,
            "provider": result.provider_id,
            "escalated": result.escalated,
        }
        if result.comparison:
            payload["comparison"] = result.comparison
        return payload
    except Exception as exc:  # noqa: BLE001
        state.record_failure(str(exc))
        log_error(provider=cfg.default_provider, error_type="runtime", detail=str(exc))
        _runtime_log("Claude Request Failed")
        _runtime_log("Decision Engine Continued")
        return None


def review_scan_candidates(candidates: list[dict[str, Any]],
                           *, service: AIAdvisorService | None = None,
                           scan_id: str = "") -> list[dict[str, Any]]:
    """Review multiple ready recommendations from a scan pass."""
    results = []
    for item in candidates:
        if not item.get("ready"):
            continue
        out = review_recommendation(
            symbol=item["symbol"],
            market=item["market"],
            timeframe=item["timeframe"],
            recommendation=item.get("recommendation"),
            row=item.get("row"),
            trade_id=str(item.get("trade_id", "")),
            scan_id=scan_id or str(item.get("scan_id", "")),
            service=service,
            context_profile="fast",
        )
        if out:
            results.append(out)
    return results
