# -*- coding: utf-8 -*-
"""Review metadata — type (automatic/manual), recommendation snapshot, fingerprint."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

META_SCHEMA_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recommendation_fingerprint(recommendation: dict[str, Any] | None) -> str:
    """Stable hash for cache invalidation when recommendation changes."""
    if not recommendation:
        return "empty"
    keys = (
        recommendation.get("action"),
        recommendation.get("side"),
        recommendation.get("grade"),
        recommendation.get("confidence"),
        recommendation.get("entry"),
        recommendation.get("stop"),
        recommendation.get("r_target"),
        recommendation.get("rr"),
    )
    raw = json.dumps(keys, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ReviewMetaStore:
    """Append-only index: review_id → metadata not in core history."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[3] / "data" / "advisor_review_meta.jsonl"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] | None = None

    def save(self, *, review_id: str, review_type: str = "automatic",
             symbol: str = "", market: str = "", timeframe: str = "",
             recommendation: dict[str, Any] | None = None,
             fingerprint: str = "") -> None:
        record = {
            "review_id": review_id,
            "schema_version": META_SCHEMA_VERSION,
            "review_type": review_type,
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "recommendation": recommendation or {},
            "fingerprint": fingerprint or recommendation_fingerprint(recommendation),
            "saved_at": _now(),
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        if self._cache is not None:
            self._cache[review_id] = record

    def get(self, review_id: str) -> dict[str, Any] | None:
        return self._index().get(review_id)

    def _index(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        out: dict[str, dict[str, Any]] = {}
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                rid = rec.get("review_id", "")
                if rid:
                    out[rid] = rec
        self._cache = out
        return out
