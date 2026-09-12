# -*- coding: utf-8 -*-
"""Fusion layer protocols."""
from __future__ import annotations

from typing import Any, Protocol


class PredictionPort(Protocol):
    def get_active_prediction(self, context: dict[str, Any]) -> dict[str, Any]: ...


class FusionHistoryPort(Protocol):
    def append(self, record: dict[str, Any]) -> str: ...
