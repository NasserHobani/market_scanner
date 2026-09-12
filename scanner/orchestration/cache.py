# -*- coding: utf-8 -*-
"""Stage cache for deterministic stages."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .workflow import CACHEABLE_STAGES


@dataclass
class CacheEntry:
    key: str
    stage: str
    value: dict[str, Any]
    created_at: float
    model_version: str = ""
    ttl_seconds: float = 3600.0

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


class StageCache:
    """Cache deterministic stage outputs.

    Cacheable: knowledge, similarity, research, feature_intelligence.
    Prediction cached only when model_version matches.
    """

    def __init__(self, *, ttl_seconds: float = 3600.0) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds

    def _make_key(self, stage: str, context_key: str) -> str:
        raw = f"{stage}:{context_key}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]

    @staticmethod
    def context_key(data: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]

    def get(self, stage: str, context_key: str, *,
            model_version: str = "") -> dict[str, Any] | None:
        key = self._make_key(stage, context_key)
        entry = self._store.get(key)
        if entry is None or entry.expired:
            if entry:
                del self._store[key]
            return None
        if stage == "prediction" and model_version:
            if entry.model_version != model_version:
                return None
        return dict(entry.value)

    def put(self, stage: str, context_key: str, value: dict[str, Any], *,
            model_version: str = "") -> None:
        if stage not in CACHEABLE_STAGES and stage != "prediction":
            return
        key = self._make_key(stage, context_key)
        self._store[key] = CacheEntry(
            key=key,
            stage=stage,
            value=dict(value),
            created_at=time.time(),
            model_version=model_version,
            ttl_seconds=self._ttl,
        )

    def invalidate(self, stage: str | None = None) -> int:
        if stage is None:
            count = len(self._store)
            self._store.clear()
            return count
        keys = [k for k, v in self._store.items() if v.stage == stage]
        for k in keys:
            del self._store[k]
        return len(keys)

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._store),
            "stages": list({e.stage for e in self._store.values()}),
        }
