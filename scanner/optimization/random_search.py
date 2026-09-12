# -*- coding: utf-8 -*-
"""Deterministic seeded random search."""
from __future__ import annotations

from typing import Any

from .evaluation import ParameterEvaluator
from .parameter_space import ParameterSpace


class RandomSearchOptimizer:
    """Repeatable seeded random parameter search."""

    def search(self, space: ParameterSpace, evaluator: ParameterEvaluator,
               rows: list[dict], *, n_samples: int = 20, seed: int = 42,
               **kwargs: Any) -> list[dict[str, Any]]:
        samples = space.random_sample(n_samples, seed=seed)
        return [evaluator.evaluate(rows, params) for params in samples]
