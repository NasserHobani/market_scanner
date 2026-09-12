# -*- coding: utf-8 -*-
"""In-memory event bus — no external message broker."""
from __future__ import annotations

from typing import Callable

from .events import DomainEvent
from .interfaces import EventPublisher


class EventBus(EventPublisher):
    """Simple synchronous event bus for domain events."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[DomainEvent], None]]] = {}
        self._history: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self._history.append(event)
        handlers = self._handlers.get(event.event_type, [])
        wildcard = self._handlers.get("*", [])
        for handler in handlers + wildcard:
            handler(event)

    def subscribe(self, event_type: str,
                  handler: Callable[[DomainEvent], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def history(self) -> list[DomainEvent]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
