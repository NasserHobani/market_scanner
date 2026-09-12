# -*- coding: utf-8 -*-
"""Per-stage and workflow timeout handling."""
from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Generator


class TimeoutError(Exception):
    """Stage or workflow exceeded timeout."""


@dataclass
class TimeoutPolicy:
    stage_timeout_ms: float = 30_000.0
    workflow_timeout_ms: float = 120_000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_timeout_ms": self.stage_timeout_ms,
            "workflow_timeout_ms": self.workflow_timeout_ms,
        }


class TimeoutHandler:
    """Graceful timeout enforcement for stages."""

    def __init__(self, policy: TimeoutPolicy | None = None) -> None:
        self._policy = policy or TimeoutPolicy()

    @property
    def policy(self) -> TimeoutPolicy:
        return self._policy

    def run_with_timeout(self, fn: Callable[[], Any], *,
                         timeout_ms: float | None = None) -> Any:
        timeout = (timeout_ms or self._policy.stage_timeout_ms) / 1000.0
        result: list[Any] = []
        exc: list[Exception] = []

        def target() -> None:
            try:
                result.append(fn())
            except Exception as e:
                exc.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            raise TimeoutError(f"Operation exceeded {timeout_ms}ms timeout")
        if exc:
            raise exc[0]
        if not result:
            raise TimeoutError("Operation produced no result")
        return result[0]
