# -*- coding: utf-8 -*-
"""Strategy optimization engine orchestrator."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .evaluation import ParameterEvaluator
from .experiment_registry import (
    ExperimentRegistry,
    OptimizationExperiment,
    OptimizationStatus,
    new_experiment_id,
)
from .optimizer import OptimizationMethod, Optimizer
from .parameter_space import ParameterSpace
from .ranking import ParameterRanker
from .report import OptimizationReportGenerator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OptimizationEngine:
    """Coordinate parameter search, evaluation, ranking, and reporting."""

    def __init__(self, *,
                 optimizer: Optimizer | None = None,
                 evaluator: ParameterEvaluator | None = None,
                 ranker: ParameterRanker | None = None,
                 reporter: OptimizationReportGenerator | None = None,
                 registry: ExperimentRegistry | None = None) -> None:
        self._optimizer = optimizer or Optimizer()
        self._evaluator = evaluator or ParameterEvaluator()
        self._ranker = ranker or ParameterRanker()
        self._reporter = reporter or OptimizationReportGenerator()
        self._registry = registry or ExperimentRegistry()
        self._leaderboards: dict[str, dict[str, Any]] = {}

    def optimize(self, rows: list[dict], space: ParameterSpace, *,
                 method: str = OptimizationMethod.GRID.value,
                 title: str = "Strategy Optimization",
                 baseline_params: dict[str, Any] | None = None,
                 top_n: int = 10,
                 **kwargs: Any) -> dict[str, Any]:
        experiment_id = new_experiment_id()
        experiment = OptimizationExperiment(
            experiment_id=experiment_id,
            title=title,
            method=method,
            parameter_space=space.to_dict(),
            configuration={"method": method, **kwargs},
            status=OptimizationStatus.RUNNING.value,
            started_at=_now(),
            trade_count=len(rows),
        )

        try:
            results = self._optimizer.search(
                method, space, self._evaluator, rows, **kwargs)
            ranked = self._ranker.rank(results)
            leaderboard = self._ranker.leaderboard(ranked, top_n=top_n)
            self._leaderboards[experiment_id] = leaderboard

            baseline = None
            if baseline_params:
                baseline = self._evaluator.evaluate(rows, baseline_params)
            elif space.defaults():
                baseline = self._evaluator.evaluate(rows, space.defaults())

            report = self._reporter.generate(
                experiment_id=experiment_id,
                method=method,
                ranked_results=ranked,
                baseline=baseline,
                leaderboard=leaderboard,
                configuration=experiment.configuration,
            )

            experiment.status = OptimizationStatus.COMPLETED.value
            experiment.ended_at = _now()
            experiment.report_id = report["report_id"]
            experiment.results = {
                "best_parameters": report["best_parameters"],
                "best_metrics": report["best_metrics"],
                "oos_metrics": report.get("oos_metrics"),
                "improvement": report.get("improvement"),
                "confidence": report.get("confidence"),
                "leaderboard": leaderboard,
                "total_evaluated": len(ranked),
            }
            self._registry.save(experiment)

            return {
                "experiment_id": experiment_id,
                "status": experiment.status,
                "method": method,
                "report": report,
                "leaderboard": leaderboard,
                "ranked_results": ranked,
            }

        except Exception as exc:
            experiment.status = OptimizationStatus.FAILED.value
            experiment.ended_at = _now()
            experiment.results = {"error": str(exc)}
            self._registry.save(experiment)
            raise

    def evaluate(self, rows: list[dict], params: dict[str, Any]) -> dict[str, Any]:
        return self._evaluator.evaluate(rows, params)

    def leaderboard(self, experiment_id: str) -> dict[str, Any] | None:
        if experiment_id in self._leaderboards:
            return self._leaderboards[experiment_id]
        exp = self._registry.load(experiment_id)
        if exp and exp.results.get("leaderboard"):
            return exp.results["leaderboard"]
        return None

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._registry.list_all(limit)
