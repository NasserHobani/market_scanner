# -*- coding: utf-8 -*-
"""Scheduler entry points — no cron, architecture only."""
from __future__ import annotations

from typing import Any

from .advisor_dataset import AdvisorEvaluationDataset
from .advisor_report import AdvisorReport
from .evaluation_engine import EvaluationEngine
from .monthly_report import MonthlyReport
from .weekly_report import WeeklyReport


class EvaluationScheduler:
    """Scheduler-ready entry points for daily, weekly, monthly jobs."""

    def __init__(self,
                 dataset: AdvisorEvaluationDataset | None = None,
                 engine: EvaluationEngine | None = None) -> None:
        self._dataset = dataset or AdvisorEvaluationDataset()
        self._engine = engine or EvaluationEngine(dataset=self._dataset)
        self._daily = AdvisorReport()
        self._weekly = WeeklyReport()
        self._monthly = MonthlyReport()

    def run_daily(self) -> dict[str, Any]:
        records = self._dataset.list_all()
        report = self._daily.generate(records, period="daily")
        metrics = self._engine.recompute_metrics()
        return {
            "job": "daily",
            "status": "completed",
            "report": report,
            "metrics": metrics,
        }

    def run_weekly(self) -> dict[str, Any]:
        records = self._dataset.list_all()
        report = self._weekly.generate(records)
        return {
            "job": "weekly",
            "status": "completed",
            "report": report,
        }

    def run_monthly(self) -> dict[str, Any]:
        records = self._dataset.list_all()
        report = self._monthly.generate(records)
        return {
            "job": "monthly",
            "status": "completed",
            "report": report,
        }
