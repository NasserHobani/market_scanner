# -*- coding: utf-8 -*-
"""Persistent evaluation dataset — versioned, append-only."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVALUATION_SCHEMA_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdvisorEvaluationDataset:
    """Every closed-trade evaluation is stored as a versioned record."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[3] / "data" / "advisor_evaluations.jsonl"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, record: dict[str, Any]) -> str:
        evaluation_id = record.get("evaluation_id") or f"eval_{uuid.uuid4().hex[:16]}"
        full = {
            "evaluation_id": evaluation_id,
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "evaluated_at": _now(),
            **record,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(full, default=str) + "\n")
        return evaluation_id

    def load(self, evaluation_id: str) -> dict[str, Any] | None:
        for record in self._iter():
            if record.get("evaluation_id") == evaluation_id:
                return record
        return None

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._iter())

    def by_trade(self, trade_id: str) -> list[dict[str, Any]]:
        return [r for r in self._iter() if r.get("trade_id") == trade_id]

    def by_provider(self, provider: str) -> list[dict[str, Any]]:
        return [r for r in self._iter() if r.get("provider") == provider]

    def since(self, iso_date: str) -> list[dict[str, Any]]:
        return [r for r in self._iter() if (r.get("execution_date") or "") >= iso_date]

    def count(self) -> int:
        return sum(1 for _ in self._iter())

    def _iter(self):
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)
