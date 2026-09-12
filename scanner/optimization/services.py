# -*- coding: utf-8 -*-
"""Public optimization service API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .evaluation import ParameterEvaluator
from .experiment_registry import ExperimentRegistry
from .optimization_engine import OptimizationEngine
from .optimizer import OptimizationMethod
from .parameter_space import Parameter, ParameterSpace, ParameterType
from .ranking import ParameterRanker


class OptimizationService:
    """Public facade for strategy parameter optimization.

    No UI, no REST API, no LLM, no trade execution — optimization only.
    """

    def __init__(self, engine: OptimizationEngine | None = None,
                 registry: ExperimentRegistry | None = None,
                 **engine_kwargs: Any) -> None:
        self._registry = registry or ExperimentRegistry()
        self._engine = engine or OptimizationEngine(registry=self._registry, **engine_kwargs)

    def optimize(self, rows: list[dict], space: ParameterSpace, *,
                 method: str = OptimizationMethod.GRID.value,
                 title: str = "Strategy Optimization",
                 baseline_params: dict[str, Any] | None = None,
                 top_n: int = 10,
                 **kwargs: Any) -> dict[str, Any]:
        """Run parameter optimization over trade rows."""
        return self._engine.optimize(
            rows, space,
            method=method,
            title=title,
            baseline_params=baseline_params,
            top_n=top_n,
            **kwargs,
        )

    def evaluate(self, rows: list[dict], params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single parameter set."""
        return self._engine.evaluate(rows, params)

    def leaderboard(self, experiment_id: str) -> dict[str, Any] | None:
        """Get leaderboard for a completed optimization."""
        return self._engine.leaderboard(experiment_id)

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        """List past optimization experiments."""
        return self._engine.history(limit)

    @staticmethod
    def build_space(**kwargs: Any) -> ParameterSpace:
        """Convenience builder for common strategy parameter spaces."""
        space = ParameterSpace()
        if "min_score_range" in kwargs:
            low, high, step = kwargs["min_score_range"]
            space.add(Parameter(
                name="min_score", param_type=ParameterType.INTEGER.value,
                low=low, high=high, step=step, default=low))
        if "require_htf" in kwargs:
            space.add(Parameter(
                name="require_htf", param_type=ParameterType.BOOLEAN.value,
                default=kwargs["require_htf"]))
        if "min_grade_choices" in kwargs:
            space.add(Parameter(
                name="min_grade", param_type=ParameterType.CATEGORICAL.value,
                choices=tuple(kwargs["min_grade_choices"]), default=kwargs["min_grade_choices"][0]))
        if "min_confidence_range" in kwargs:
            low, high, step = kwargs["min_confidence_range"]
            space.add(Parameter(
                name="min_confidence", param_type=ParameterType.NUMERIC.value,
                low=low, high=high, step=step, default=low))
        for key, val in kwargs.get("fixed", {}).items():
            space.fixed[key] = val
        return space
