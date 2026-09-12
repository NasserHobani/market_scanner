# -*- coding: utf-8 -*-
"""Evaluation framework protocols."""
from __future__ import annotations

from typing import Any, Protocol


class EvaluationDatasetProtocol(Protocol):
    def save(self, record: dict[str, Any]) -> str: ...
    def load(self, evaluation_id: str) -> dict[str, Any] | None: ...
    def list_all(self) -> list[dict[str, Any]]: ...


class EvaluationEngineProtocol(Protocol):
    def evaluate_closed_trade(self, *, trade_id: str,
                              trade_result: dict[str, Any],
                              memory_record: dict[str, Any],
                              decision_package: dict[str, Any] | None = None) -> dict[str, Any]: ...


class MetricsComputerProtocol(Protocol):
    def compute(self, records: list[dict[str, Any]]) -> dict[str, Any]: ...


class ReportGeneratorProtocol(Protocol):
    def generate(self, records: list[dict[str, Any]], *,
                 period: str = "daily") -> dict[str, Any]: ...
