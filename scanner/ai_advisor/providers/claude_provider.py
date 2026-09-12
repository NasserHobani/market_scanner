# -*- coding: utf-8 -*-
"""Production Anthropic Claude provider for AI Advisor."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..advisor_logging import log_error, log_health, log_request, log_response, log_retry
from ..decision_package import DecisionPackage
from ..prompt_builder import AdvisorPrompt
from ..provider_config import AIAdvisorConfig, load_config
from ..response_parser import ResponseParser, ResponseParseError
from .base import LLMProvider, ProviderMetadata

PROVIDER_VERSION = "1.0.0"

_RETRYABLE_ERRORS = (
    "timeout", "rate_limit", "overloaded", "529", "503", "502", "500",
    "connection", "temporary",
)


class ProviderError(Exception):
    """Non-retryable provider failure."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class HealthState:
    healthy: bool = False
    latency_ms: float | None = None
    last_success: str | None = None
    last_failure: str | None = None
    total_requests: int = 0
    total_failures: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""
    model_name: str = ""
    provider_version: str = PROVIDER_VERSION

    @property
    def average_response_time_ms(self) -> float | None:
        successes = self.total_requests - self.total_failures
        if successes <= 0:
            return None
        return round(self.total_latency_ms / successes, 1)

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_failures / self.total_requests * 100, 1)

    def record_success(self, latency_ms: float) -> None:
        from datetime import datetime, timezone
        self.healthy = True
        self.latency_ms = latency_ms
        self.last_success = datetime.now(timezone.utc).isoformat()
        self.total_requests += 1
        self.total_latency_ms += latency_ms

    def record_failure(self, error: str) -> None:
        from datetime import datetime, timezone
        self.healthy = False
        self.last_failure = datetime.now(timezone.utc).isoformat()
        self.last_error = error[:200]
        self.total_requests += 1
        self.total_failures += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "provider_id": "claude",
            "model_name": self.model_name,
            "latency_ms": self.latency_ms,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "total_requests": self.total_requests,
            "average_response_time_ms": self.average_response_time_ms,
            "error_rate": self.error_rate,
            "provider_version": self.provider_version,
            "mode": "production",
        }


@dataclass
class ClaudeProvider(LLMProvider):
    """Production Claude provider — never couples platform to Anthropic directly.

    All configuration comes from AIAdvisorConfig.
    API key loaded from ANTHROPIC_API_KEY environment variable only.
    """

    _config: AIAdvisorConfig = field(default_factory=load_config)
    _health: HealthState = field(default_factory=HealthState)
    _client_factory: Callable[[], Any] | None = field(default=None, repr=False)
    last_usage: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._health.model_name = self._config.effective_model()
        self._meta = ProviderMetadata(
            provider_id="claude",
            display_name="Claude",
            vendor="anthropic",
            model_family="claude",
            supports_json=True,
            supports_streaming=False,
            description="Anthropic Claude — production AI Advisor provider",
        )

    @property
    def provider_id(self) -> str:
        return "claude"

    @property
    def metadata(self) -> ProviderMetadata:
        return self._meta

    def provider_name(self) -> str:
        return "claude"

    def model_name(self) -> str:
        return self._config.effective_model()

    def supported_features(self) -> dict[str, bool]:
        return {
            "json_mode": True,
            "shadow_mode": self._config.shadow_mode,
            "grounding": self._config.grounding_required,
            "experiments": self._config.allow_experiments,
            "streaming": False,
            "multi_model": True,
        }

    def analyze(self, prompt: AdvisorPrompt, *,
                package: DecisionPackage) -> dict[str, Any]:
        if not self._config.claude_enabled:
            raise ProviderError("Claude provider is disabled in settings")
        if not self._api_key():
            raise ProviderError("ANTHROPIC_API_KEY not configured")

        max_attempts = max(1, self._config.retry_count + 1)
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            log_request(
                provider="claude",
                model=self.model_name(),
                event_id=package.event_id,
                prompt_version=prompt.version,
                attempt=attempt,
            )
            start = time.monotonic()
            try:
                raw_text = self._call_api(prompt)
                parsed = self._parse_json(raw_text)
                latency = (time.monotonic() - start) * 1000
                self._health.record_success(latency)
                log_response(
                    provider="claude", model=self.model_name(),
                    latency_ms=latency, success=True, event_id=package.event_id,
                )
                return parsed
            except (json.JSONDecodeError, ResponseParseError) as exc:
                if attempt < max_attempts:
                    log_retry(provider="claude", reason="invalid_json", attempt=attempt)
                    last_error = exc
                    continue
                self._health.record_failure("invalid_json")
                log_error(provider="claude", error_type="json", detail="invalid JSON response")
                raise ProviderError(f"Invalid JSON from Claude: {exc}") from exc
            except ProviderError as exc:
                last_error = exc
                if not exc.retryable or attempt >= max_attempts:
                    self._health.record_failure(str(exc))
                    log_error(provider="claude", error_type="provider", detail=str(exc))
                    raise
                log_retry(provider="claude", reason=str(exc), attempt=attempt)
            except Exception as exc:
                retryable = self._is_retryable(exc)
                last_error = exc
                if retryable and attempt < max_attempts:
                    log_retry(provider="claude", reason=type(exc).__name__, attempt=attempt)
                    continue
                self._health.record_failure(str(exc))
                log_error(provider="claude", error_type=type(exc).__name__, detail=str(exc))
                raise ProviderError(str(exc), retryable=retryable) from exc

        raise ProviderError(str(last_error or "unknown error"))

    def health(self) -> dict[str, Any]:
        result = self._health.to_dict()
        result["api_key_configured"] = bool(self._api_key())
        result["enabled"] = self._config.claude_enabled
        if not self._config.claude_enabled:
            result["healthy"] = False
            result["mode"] = "disabled"
        elif not self._api_key():
            result["healthy"] = False
            result["mode"] = "no_api_key"
        return result

    def test_connection(self) -> dict[str, Any]:
        """Run health check with a minimal JSON request."""
        if not self._api_key():
            return {
                "connected": False,
                "error": "ANTHROPIC_API_KEY not configured",
                "latency_ms": None,
                "model": self.model_name(),
                "provider_version": PROVIDER_VERSION,
            }

        start = time.monotonic()
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self.model_name(),
                max_tokens=32,
                temperature=0,
                system="Respond with JSON only. No markdown.",
                messages=[{"role": "user", "content": '{"status":"ok"}'}],
            )
            text = self._extract_text(response)
            self._parse_json(text)
            latency = (time.monotonic() - start) * 1000
            self._health.record_success(latency)
            log_health(provider="claude", healthy=True, latency_ms=latency)
            return {
                "connected": True,
                "latency_ms": round(latency, 1),
                "model": self.model_name(),
                "provider_version": PROVIDER_VERSION,
            }
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            self._health.record_failure(str(exc))
            log_health(provider="claude", healthy=False, latency_ms=latency)
            log_error(provider="claude", error_type="connection_test", detail=str(exc))
            return {
                "connected": False,
                "error": self._safe_error(str(exc)),
                "latency_ms": round(latency, 1),
                "model": self.model_name(),
                "provider_version": PROVIDER_VERSION,
            }

    def _call_api(self, prompt: AdvisorPrompt) -> str:
        client = self._get_client()
        system = prompt.system_prompt
        if self._config.strict_json:
            system += "\n\nYou MUST respond with valid JSON only. No markdown fences. No prose."

        try:
            response = client.messages.create(
                model=self.model_name(),
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=system,
                messages=[{"role": "user", "content": prompt.user_prompt}],
                timeout=self._config.timeout,
            )
        except TypeError:
            response = client.messages.create(
                model=self.model_name(),
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=system,
                messages=[{"role": "user", "content": prompt.user_prompt}],
            )
        self._capture_usage(response)
        return self._extract_text(response)

    def _capture_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            self.last_usage = {}
            return
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        self.last_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _get_client(self) -> Any:
        if self._client_factory:
            return self._client_factory()
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError(
                "anthropic package not installed — pip install anthropic",
                retryable=False,
            ) from exc
        return anthropic.Anthropic(api_key=self._api_key())

    @staticmethod
    def _api_key() -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "").strip()

    @staticmethod
    def _extract_text(response: Any) -> str:
        if hasattr(response, "content") and response.content:
            block = response.content[0]
            if hasattr(block, "text"):
                return str(block.text)
        if isinstance(response, dict):
            content = response.get("content", [])
            if content and isinstance(content[0], dict):
                return str(content[0].get("text", ""))
        return str(response)

    def _parse_json(self, text: str) -> dict[str, Any]:
        return ResponseParser().parse(text)

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(token in msg for token in _RETRYABLE_ERRORS)

    @staticmethod
    def _safe_error(message: str) -> str:
        if "api" in message.lower() and "key" in message.lower():
            return "Authentication failed"
        return message[:200]
