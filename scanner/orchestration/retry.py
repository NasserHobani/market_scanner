# -*- coding: utf-8 -*-
"""Retry strategy for failed stages."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class RetryPolicy:
    max_retries: int = 2
    backoff_ms: float = 100.0
    backoff_multiplier: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "backoff_ms": self.backoff_ms,
            "backoff_multiplier": self.backoff_multiplier,
        }


class RetryHandler:
    """Retry failed stages — never retry successful stages."""

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    def execute(self, fn: Callable[[], Any], *,
                stage_name: str = "") -> tuple[Any, int]:
        """Run fn with retries. Returns (result, retry_count)."""
        last_exc: Exception | None = None
        retries = 0
        backoff = self._policy.backoff_ms

        for attempt in range(self._policy.max_retries + 1):
            try:
                return fn(), retries
            except Exception as exc:
                last_exc = exc
                if attempt >= self._policy.max_retries:
                    break
                retries += 1
                time.sleep(backoff / 1000.0)
                backoff *= self._policy.backoff_multiplier

        raise RuntimeError(
            f"Stage '{stage_name}' failed after {retries} retries: {last_exc}"
        ) from last_exc
