# -*- coding: utf-8 -*-
"""Optimizer base and factory."""
from __future__ import annotations

from enum import Enum
from typing import Any

from .evaluation import ParameterEvaluator
from .grid_search import GridSearchOptimizer
from .parameter_space import ParameterSpace
from .random_search import RandomSearchOptimizer
from .walk_forward_optimizer import WalkForwardOptimizer


class OptimizationMethod(str, Enum):
    GRID = "grid"
    RANDOM = "random"
    WALK_FORWARD = "walk_forward"


class Optimizer:
    """Factory for optimization strategies."""

    def __init__(self) -> None:
        self._grid = GridSearchOptimizer()
        self._random = RandomSearchOptimizer()
        self._walk_forward = WalkForwardOptimizer()

    def search(self, method: str, space: ParameterSpace,
               evaluator: ParameterEvaluator, rows: list[dict],
               **kwargs: Any) -> list[dict[str, Any]]:
        if method == OptimizationMethod.GRID.value:
            return self._grid.search(space, evaluator, rows, **kwargs)
        if method == OptimizationMethod.RANDOM.value:
            return self._random.search(space, evaluator, rows, **kwargs)
        if method == OptimizationMethod.WALK_FORWARD.value:
            return self._walk_forward.search(space, evaluator, rows, **kwargs)
        raise ValueError(f"Unknown method: {method}")
