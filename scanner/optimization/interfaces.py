# -*- coding: utf-8 -*-
"""Optimization protocol definitions."""
from __future__ import annotations

from typing import Any, Protocol


class OptimizerProtocol(Protocol):
    def search(self, space: Any, evaluator: Any, rows: list[dict],
               **kwargs: Any) -> list[dict[str, Any]]: ...


class EvaluatorProtocol(Protocol):
    def evaluate(self, rows: list[dict], params: dict[str, Any]) -> dict[str, Any]: ...


class OptimizationEngineProtocol(Protocol):
    def optimize(self, rows: list[dict], space: Any, *,
                 method: str, **kwargs: Any) -> dict[str, Any]: ...

    def evaluate(self, rows: list[dict], params: dict[str, Any]) -> dict[str, Any]: ...
