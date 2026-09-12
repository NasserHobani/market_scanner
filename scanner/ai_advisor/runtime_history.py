# -*- coding: utf-8 -*-
"""Advisor runtime history — append-only advisor_history.jsonl."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_SCHEMA_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdvisorRuntimeHistory:
    """Store successful advisor reviews with token accounting."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[2] / "data" / "advisor_history.jsonl"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, record: dict[str, Any]) -> str:
        review_id = record.get("review_id") or f"adv_{uuid.uuid4().hex[:16]}"
        full = {
            "review_id": review_id,
            "schema_version": HISTORY_SCHEMA_VERSION,
            "timestamp": record.get("timestamp") or _now(),
            **record,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(full, default=str) + "\n")
        return review_id

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        return records[-limit:]

    def count(self) -> int:
        if not self._path.exists():
            return 0
        return sum(1 for line in self._path.open(encoding="utf-8") if line.strip())

    def last(self) -> dict[str, Any] | None:
        recent = self.list_recent(1)
        return recent[0] if recent else None
