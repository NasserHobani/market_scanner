# -*- coding: utf-8 -*-
"""Append-only fusion history."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_PATH = Path("data/ai_fusion_history.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FusionHistory:
    """Persist fusion reviews — append-only."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else HISTORY_PATH

    def append(self, record: dict[str, Any]) -> str:
        rid = record.get("fusion_id") or f"fusion_{uuid.uuid4().hex[:16]}"
        row = {**record, "fusion_id": rid, "timestamp": record.get("timestamp") or _now()}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return rid

    def list_all(self, *, limit: int = 500) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows[-limit:]

    def count(self) -> int:
        if not self._path.exists():
            return 0
        return sum(1 for line in self._path.open(encoding="utf-8") if line.strip())
