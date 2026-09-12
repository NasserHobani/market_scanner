# -*- coding: utf-8 -*-
"""AI Advisor Evaluation Framework — measures advisor quality after trades close."""
from __future__ import annotations

from typing import Any

from .advisor_dataset import AdvisorEvaluationDataset, EVALUATION_SCHEMA_VERSION
from .advisor_metrics import AdvisorMetrics, CALIBRATION_BUCKETS
from .advisor_report import AdvisorReport
from .benchmark import ProviderBenchmark
from .evaluation_engine import EvaluationEngine, EVALUATION_VERSION
from .leaderboard import ProviderLeaderboard
from .monthly_report import MonthlyReport
from .scheduler import EvaluationScheduler
from .weekly_report import WeeklyReport


class AdvisorEvaluationService:
    """Public API for AI Advisor quality evaluation."""

    def __init__(self,
                 dataset: AdvisorEvaluationDataset | None = None,
                 memory=None) -> None:
        from scanner.ai_advisor.memory import AdvisorMemory
        self._dataset = dataset or AdvisorEvaluationDataset()
        self._memory = memory or AdvisorMemory()
        self._engine = EvaluationEngine(dataset=self._dataset, memory=self._memory)
        self._metrics = AdvisorMetrics()
        self._leaderboard = ProviderLeaderboard()
        self._benchmark = ProviderBenchmark()
        self._report = AdvisorReport()
        self._scheduler = EvaluationScheduler(dataset=self._dataset, engine=self._engine)

    def evaluate_trade(self, *, trade_id: str,
                       trade_result: dict[str, Any],
                       review_id: str = "") -> dict[str, Any]:
        return self._engine.evaluate_by_review_id(
            trade_id=trade_id, review_id=review_id, trade_result=trade_result,
        )

    def metrics(self) -> dict[str, Any]:
        return self._engine.recompute_metrics()

    def leaderboard(self) -> list[dict[str, Any]]:
        return self._leaderboard.compute(self._dataset.list_all())

    def benchmark(self, provider_a: str, provider_b: str) -> dict[str, Any]:
        return self._benchmark.compare(
            self._dataset.list_all(), provider_a=provider_a, provider_b=provider_b,
        )

    def daily_report(self) -> dict[str, Any]:
        return self._scheduler.run_daily()

    def weekly_report(self) -> dict[str, Any]:
        return self._scheduler.run_weekly()

    def monthly_report(self) -> dict[str, Any]:
        return self._scheduler.run_monthly()

    def to_ui_model(self) -> dict[str, Any]:
        records = self._dataset.list_all()
        return {
            "available": True,
            "version": EVALUATION_VERSION,
            "schema_version": EVALUATION_SCHEMA_VERSION,
            **self._report.to_ui_model(records),
        }


__all__ = [
    "AdvisorEvaluationDataset",
    "AdvisorEvaluationService",
    "AdvisorMetrics",
    "AdvisorReport",
    "CALIBRATION_BUCKETS",
    "EVALUATION_SCHEMA_VERSION",
    "EVALUATION_VERSION",
    "EvaluationEngine",
    "EvaluationScheduler",
    "MonthlyReport",
    "ProviderBenchmark",
    "ProviderLeaderboard",
    "WeeklyReport",
]
