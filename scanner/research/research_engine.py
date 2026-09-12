# -*- coding: utf-8 -*-
"""Research engine — top-level orchestrator for quant research."""
from __future__ import annotations

from typing import Any

from scanner.research.comparison import ComparisonEngine, ComparisonResult
from scanner.research.dataset import DatasetBuilder
from scanner.research.experiment import Experiment, ExperimentStore
from scanner.research.experiment_runner import ExperimentRunner
from scanner.research.hypothesis import Hypothesis
from scanner.research.metrics import MetricsEngine
from scanner.research.report import ResearchReport
from scanner.research.statistics import summarize_differences


class ResearchEngine:
    """Central research laboratory orchestrator."""

    def __init__(self,
                 store: ExperimentStore | None = None,
                 runner: ExperimentRunner | None = None,
                 metrics: MetricsEngine | None = None,
                 comparison: ComparisonEngine | None = None,
                 datasets: DatasetBuilder | None = None) -> None:
        self._store = store or ExperimentStore()
        self._metrics = metrics or MetricsEngine()
        self._comparison = comparison or ComparisonEngine(self._metrics)
        self._datasets = datasets or DatasetBuilder()
        self._runner = runner or ExperimentRunner(
            store=self._store,
            dataset_builder=self._datasets,
            metrics=self._metrics,
            comparison=self._comparison,
        )

    def run_experiment(self, *,
                       title: str,
                       rows: list[dict],
                       hypothesis: Hypothesis | dict | None = None,
                       description: str = "",
                       dataset_config: dict[str, Any] | None = None,
                       configuration: dict[str, Any] | None = None) -> Experiment:
        return self._runner.run(
            title=title,
            rows=rows,
            hypothesis=hypothesis,
            description=description,
            dataset_config=dataset_config,
            configuration=configuration,
        )

    def compare(self, rows_a: list[dict], rows_b: list[dict], *,
                label_a: str = "A", label_b: str = "B",
                comparison_type: str = "group_vs_group") -> ComparisonResult:
        return self._comparison.compare(
            rows_a, rows_b,
            label_a=label_a, label_b=label_b,
            comparison_type=comparison_type,
        )

    def statistics(self, rows: list[dict]) -> dict[str, Any]:
        return self._metrics.compute(rows)

    def generate_report(self, experiment_id: str) -> ResearchReport:
        from scanner.research.report import ResearchReport
        experiment = self._store.load(experiment_id)
        report_data = experiment.results.get("report")
        if not report_data:
            raise KeyError(f"no report for experiment: {experiment_id}")
        return ResearchReport(
            report_id=report_data["report_id"],
            experiment_id=experiment_id,
            title=report_data.get("title") or experiment.title,
            dataset_summary=report_data.get("dataset_summary") or {},
            methodology=report_data.get("methodology") or {},
            metrics=report_data.get("metrics") or {},
            comparison=report_data.get("comparison"),
            conclusions=report_data.get("conclusions") or [],
            warnings=report_data.get("warnings") or [],
            limitations=report_data.get("limitations") or [],
            generated_at=report_data.get("generated_at") or "",
        )

    def history(self, *, limit: int = 50) -> list[Experiment]:
        return self._store.history(limit=limit)

    def load_experiment(self, experiment_id: str) -> Experiment:
        return self._store.load(experiment_id)
