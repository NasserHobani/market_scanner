# -*- coding: utf-8 -*-
"""Deterministic exhaustive grid search."""
from __future__ import annotations

from typing import Any

from .evaluation import ParameterEvaluator
from .parameter_space import ParameterSpace


class GridSearchOptimizer:
    """Exhaustive deterministic search over parameter space."""

    def search(self, space: ParameterSpace, evaluator: ParameterEvaluator,
               rows: list[dict], **kwargs: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for params in space.grid_combinations():
            results.append(evaluator.evaluate(rows, params))
        return results
