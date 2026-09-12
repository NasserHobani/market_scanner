# -*- coding: utf-8 -*-
"""Orchestrator runtime state — trade counters and last-run metadata."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path("data/research/orchestrator_state.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrchestratorState:
    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else STATE_PATH

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._defaults()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            out = self._defaults()
            out.update(data)
            return out
        except (json.JSONDecodeError, OSError):
            return self._defaults()

    def save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "trades_since_last_run": 0,
            "last_run_at": "",
            "last_dataset_fingerprint": "",
            "weekly_last_run_at": "",
            "last_experiment_id": "",
            "processed_hypothesis_ids": [],
            "processed_failure_patterns": [],
        }

    def increment_trade_counter(self) -> int:
        data = self.load()
        data["trades_since_last_run"] = int(data.get("trades_since_last_run") or 0) + 1
        self.save(data)
        return data["trades_since_last_run"]

    def reset_trade_counter(self, *, fingerprint: str = "", experiment_id: str = "") -> None:
        data = self.load()
        data["trades_since_last_run"] = 0
        data["last_run_at"] = _now()
        if fingerprint:
            data["last_dataset_fingerprint"] = fingerprint
        if experiment_id:
            data["last_experiment_id"] = experiment_id
        self.save(data)
