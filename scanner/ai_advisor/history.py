# -*- coding: utf-8 -*-
"""Advisor review history — queryable audit trail."""
from __future__ import annotations

from typing import Any

from .memory import AdvisorMemory


class AdvisorHistory:
    """Query interface over advisor memory records."""

    def __init__(self, memory: AdvisorMemory | None = None) -> None:
        self._memory = memory or AdvisorMemory()

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._memory.list_recent(limit)

    def by_event(self, event_id: str) -> list[dict[str, Any]]:
        return [r for r in self._memory.list_recent(1000)
                if r.get("event_id") == event_id]

    def by_provider(self, provider_id: str) -> list[dict[str, Any]]:
        return [r for r in self._memory.list_recent(1000)
                if r.get("provider_id") == provider_id]

    def accepted(self, limit: int = 50) -> list[dict[str, Any]]:
        return [r for r in self._memory.list_recent(limit * 2)
                if r.get("accepted")][:limit]

    def rejected(self, limit: int = 50) -> list[dict[str, Any]]:
        return [r for r in self._memory.list_recent(limit * 2)
                if r.get("rejected")][:limit]

    def summary(self) -> dict[str, Any]:
        records = self._memory.list_recent(10000)
        return {
            "total": len(records),
            "accepted": sum(1 for r in records if r.get("accepted")),
            "rejected": sum(1 for r in records if r.get("rejected")),
            "providers": list({r.get("provider_id") for r in records}),
        }
