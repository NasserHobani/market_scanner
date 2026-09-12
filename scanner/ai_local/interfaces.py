# -*- coding: utf-8 -*-
"""Local AI interfaces — future training hooks (AIA-06: inference only)."""
from __future__ import annotations

from typing import Any, Protocol


class LocalReviewStoreProtocol(Protocol):
    def append(self, record: dict[str, Any]) -> None: ...

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]: ...


class ComparisonStoreProtocol(Protocol):
    def save(self, record: dict[str, Any]) -> str: ...

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]: ...
