# -*- coding: utf-8 -*-
"""In-memory TTL cache for dashboard widget payloads."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable


class WidgetCache:
    """Process-local widget cache — avoids recomputing heavy metrics on every request."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def _key(self, widget: str, filters: dict[str, Any]) -> str:
        payload = json.dumps(filters, sort_keys=True, default=str)
        digest = hashlib.md5(payload.encode()).hexdigest()[:12]
        return f"{widget}:{digest}"

    def get(self, widget: str, filters: dict[str, Any]) -> Any | None:
        key = self._key(widget, filters)
        hit = self._store.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        return None

    def set(self, widget: str, filters: dict[str, Any], data: Any, ttl: float) -> None:
        key = self._key(widget, filters)
        self._store[key] = (time.time() + ttl, data)

    def invalidate(self, widget: str | None = None) -> int:
        if widget is None:
            count = len(self._store)
            self._store.clear()
            return count
        prefix = f"{widget}:"
        keys = [k for k in self._store if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        return len(keys)

    def get_or_compute(self, widget: str, filters: dict[str, Any], ttl: float,
                       compute: Callable[[], Any]) -> tuple[Any, bool]:
        cached = self.get(widget, filters)
        if cached is not None:
            return cached, True
        data = compute()
        self.set(widget, filters, data, ttl)
        return data, False


# Widget TTLs (seconds)
TTL_HEALTH = 60
TTL_TRENDS = 60
TTL_SCANNER_SUMMARY = 30
TTL_OPEN_TRADES = 5
TTL_PERFORMANCE = 300  # 5 minutes
TTL_SETTLEMENT = 10

widget_cache = WidgetCache()
