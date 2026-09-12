# -*- coding: utf-8 -*-
"""Append-only local AI review history."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "local_ai_history.jsonl"


class LocalAIHistory:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else _path()

    def append(self, record: dict[str, Any]) -> None:
        rec = dict(record)
        rec.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(out) >= limit:
                break
        return out

    def count(self) -> int:
        if not self._path.exists():
            return 0
        return sum(1 for ln in self._path.read_text(encoding="utf-8").splitlines() if ln.strip())
