# -*- coding: utf-8 -*-
"""Structured advisor logging — metadata only, never secrets or payloads."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("scanner.ai_advisor.provider")


def log_request(*, provider: str, model: str, event_id: str = "",
                prompt_version: str = "", attempt: int = 1) -> None:
    log.info(
        "advisor_request",
        extra={
            "provider": provider,
            "model": model,
            "event_id": event_id,
            "prompt_version": prompt_version,
            "attempt": attempt,
        },
    )


def log_response(*, provider: str, model: str, latency_ms: float,
                 success: bool, event_id: str = "") -> None:
    log.info(
        "advisor_response",
        extra={
            "provider": provider,
            "model": model,
            "latency_ms": round(latency_ms, 1),
            "success": success,
            "event_id": event_id,
        },
    )


def log_retry(*, provider: str, reason: str, attempt: int) -> None:
    log.warning(
        "advisor_retry",
        extra={"provider": provider, "reason": reason, "attempt": attempt},
    )


def log_error(*, provider: str, error_type: str, detail: str) -> None:
    safe_msg = detail[:200] if detail else ""
    if "api" in safe_msg.lower() and "key" in safe_msg.lower():
        safe_msg = "authentication error"
    log.error(
        "advisor_error",
        extra={"provider": provider, "error_type": error_type, "detail": safe_msg},
    )


def log_health(*, provider: str, healthy: bool, latency_ms: float | None = None) -> None:
    log.info(
        "advisor_health",
        extra={
            "provider": provider,
            "healthy": healthy,
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
        },
    )


def log_runtime(message: str) -> None:
    log.info("advisor_runtime_event", extra={"event": message})
