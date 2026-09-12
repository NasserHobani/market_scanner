# -*- coding: utf-8 -*-
"""Intelligence layer interfaces."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .insight import InsightReport
from .pattern_engine import PatternReport
from .strategy_health import StrategyHealthReport


@runtime_checkable
class PatternProvider(Protocol):
    def discover(self, rows: list[dict]) -> PatternReport: ...


@runtime_checkable
class HealthProvider(Protocol):
    def assess(self, rows: list[dict], **kwargs: Any) -> StrategyHealthReport: ...


@runtime_checkable
class InsightProvider(Protocol):
    def build(self, **kwargs: Any) -> InsightReport: ...


@runtime_checkable
class IntelligenceProvider(Protocol):
    def analyze(self, rows: list[dict], **kwargs: Any) -> dict[str, Any]: ...
