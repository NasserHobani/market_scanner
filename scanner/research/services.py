# -*- coding: utf-8 -*-
"""Public research service API."""
from __future__ import annotations

from typing import Any

from scanner.research.comparison import ComparisonResult
from scanner.research.experiment import Experiment, ExperimentStore
from scanner.research.hypothesis import Hypothesis
from scanner.research.research_engine import ResearchEngine
from scanner.research.report import ResearchReport
from scanner.research.statistics import summarize_differences


class ResearchService:
    """Public facade for quant research capabilities."""

    def __init__(self, engine: ResearchEngine | None = None,
                 store: ExperimentStore | None = None) -> None:
        self._store = store or ExperimentStore()
        self._engine = engine or ResearchEngine(store=self._store)

    def run_experiment(self, *,
                       title: str,
                       rows: list[dict],
                       hypothesis: Hypothesis | dict | None = None,
                       description: str = "",
                       dataset_config: dict[str, Any] | None = None,
                       configuration: dict[str, Any] | None = None) -> Experiment:
        return self._engine.run_experiment(
            title=title,
            rows=rows,
            hypothesis=hypothesis,
            description=description,
            dataset_config=dataset_config,
            configuration=configuration,
        )

    def compare(self, group_a: list[dict], group_b: list[dict], *,
                label_a: str = "A", label_b: str = "B",
                comparison_type: str = "group_vs_group") -> ComparisonResult:
        return self._engine.compare(
            group_a, group_b,
            label_a=label_a, label_b=label_b,
            comparison_type=comparison_type,
        )

    def statistics(self, rows: list[dict]) -> dict[str, Any]:
        return self._engine.statistics(rows)

    def generate_report(self, experiment_id: str) -> ResearchReport:
        return self._engine.generate_report(experiment_id)

    def history(self, *, limit: int = 50) -> list[Experiment]:
        return self._engine.history(limit=limit)

    def compare_metrics(self, metrics_a: dict[str, Any],
                        metrics_b: dict[str, Any], *,
                        label_a: str = "A",
                        label_b: str = "B") -> dict[str, Any]:
        """Compare pre-computed metric dicts."""
        return summarize_differences(metrics_a, metrics_b,
                                     label_a=label_a, label_b=label_b)
