# -*- coding: utf-8 -*-
"""Experiment runner — prepare, run, collect, store, report."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scanner.research.comparison import ComparisonEngine
from scanner.research.dataset import Dataset, DatasetBuilder
from scanner.research.experiment import (
    Experiment,
    ExperimentStatus,
    ExperimentStore,
    RESEARCH_VERSION,
    _now,
    new_experiment_id,
)
from scanner.research.hypothesis import Hypothesis, HypothesisEngine
from scanner.research.metrics import MetricsEngine
from scanner.research.report import ReportGenerator


class ExperimentRunner:
    """Orchestrate a single experiment lifecycle."""

    def __init__(self,
                 store: ExperimentStore | None = None,
                 dataset_builder: DatasetBuilder | None = None,
                 hypothesis_engine: HypothesisEngine | None = None,
                 metrics: MetricsEngine | None = None,
                 comparison: ComparisonEngine | None = None,
                 reporter: ReportGenerator | None = None) -> None:
        self._store = store or ExperimentStore()
        self._datasets = dataset_builder or DatasetBuilder()
        self._hypothesis = hypothesis_engine or HypothesisEngine()
        self._metrics = metrics or MetricsEngine()
        self._comparison = comparison or ComparisonEngine(self._metrics)
        self._reporter = reporter or ReportGenerator()

    def run(self, *,
            title: str,
            rows: list[dict],
            hypothesis: Hypothesis | dict[str, Any] | None = None,
            description: str = "",
            dataset_config: dict[str, Any] | None = None,
            configuration: dict[str, Any] | None = None) -> Experiment:
        if isinstance(hypothesis, dict):
            hypothesis = Hypothesis.from_dict(hypothesis)

        experiment = Experiment(
            experiment_id=new_experiment_id(),
            title=title,
            description=description,
            hypothesis=hypothesis.to_dict() if hypothesis else {},
            configuration=configuration or {},
            status=ExperimentStatus.RUNNING.value,
            version=RESEARCH_VERSION,
            started_at=_now(),
        )

        try:
            dataset = self._prepare_dataset(rows, dataset_config or {})
            experiment.dataset = dataset.to_dict()

            results: dict[str, Any] = {"metrics": {}}
            hypothesis_eval = None
            comparison_result = None

            if hypothesis:
                treatment, baseline = self._hypothesis.split(dataset.rows, hypothesis)
                hypothesis_eval = self._hypothesis.evaluate(dataset.rows, hypothesis)
                results["hypothesis_eval"] = hypothesis_eval
                results["metrics"]["treatment"] = self._metrics.compute(treatment)
                results["metrics"]["baseline"] = self._metrics.compute(baseline)
                comparison_result = self._comparison.compare(
                    treatment, baseline,
                    label_a=hypothesis.treatment_label,
                    label_b=hypothesis.baseline_label,
                    comparison_type="hypothesis_test",
                )
                results["comparison"] = comparison_result.to_dict()
            else:
                results["metrics"]["all"] = self._metrics.compute(dataset.rows)

            report = self._reporter.generate(
                experiment_id=experiment.experiment_id,
                title=title,
                dataset_summary=dataset.to_dict(),
                methodology={
                    "version": RESEARCH_VERSION,
                    "hypothesis": hypothesis.to_dict() if hypothesis else None,
                    "dataset_config": dataset_config or {},
                    "configuration": configuration or {},
                },
                metrics=results["metrics"],
                comparison=comparison_result.to_dict() if comparison_result else None,
                hypothesis_eval=hypothesis_eval,
            )
            results["report"] = report.to_dict()
            experiment.results = results
            experiment.report_id = report.report_id
            experiment.status = ExperimentStatus.COMPLETED.value
            experiment.ended_at = _now()
        except Exception as exc:
            experiment.status = ExperimentStatus.FAILED.value
            experiment.ended_at = _now()
            experiment.results = {"error": str(exc)}
            raise
        finally:
            self._store.save(experiment)

        return experiment

    def _prepare_dataset(self, rows: list[dict],
                         config: dict[str, Any]) -> Dataset:
        dataset = self._datasets.from_rows(rows, label=config.get("label", "all_trades"))

        if config.get("completed_only"):
            dataset = self._datasets.completed(dataset)
        if config.get("market"):
            dataset = self._datasets.by_market(dataset, config["market"])
        if config.get("timeframe"):
            dataset = self._datasets.by_timeframe(dataset, config["timeframe"])
        if config.get("factor"):
            dataset = self._datasets.by_factor(dataset, config["factor"])
        if config.get("regime"):
            dataset = self._datasets.by_regime(dataset, config["regime"])
        if config.get("winners_only"):
            dataset = self._datasets.winners(dataset)
        if config.get("losers_only"):
            dataset = self._datasets.losers(dataset)
        if config.get("similarity_event_ids"):
            dataset = self._datasets.by_similarity_group(
                dataset, config["similarity_event_ids"])

        return dataset
