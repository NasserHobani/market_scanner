# -*- coding: utf-8 -*-
"""Advisor runtime state — Disconnected / Connected / Running / Failed / Disabled."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_STATUSES = ("disconnected", "connected", "running", "failed", "disabled")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdvisorRuntimeState:
    """Persistent runtime status for dashboard."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[2] / "data" / "advisor_runtime_state.json"
        self._path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._default()
        try:
            with open(self._path, encoding="utf-8") as f:
                return {**self._default(), **json.load(f)}
        except (json.JSONDecodeError, OSError):
            return self._default()

    def save(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({**self.load(), **state, "updated_at": _now()}, f, indent=2)

    def set_status(self, status: str, **extra: Any) -> None:
        if status not in RUNTIME_STATUSES:
            status = "failed"
        self.save({"status": status, **extra})

    def record_success(self, **metrics: Any) -> None:
        current = self.load()
        count = int(current.get("successful_reviews", 0)) + 1
        self.save({
            "status": "running",
            "successful_reviews": count,
            "last_review_at": _now(),
            "last_error": "",
            **metrics,
        })

    def record_failure(self, error: str) -> None:
        self.save({"status": "failed", "last_error": error[:200], "last_failure_at": _now()})

    @staticmethod
    def _default() -> dict[str, Any]:
        return {
            "status": "disconnected",
            "successful_reviews": 0,
            "last_review_at": "",
            "last_error": "",
        }
