# -*- coding: utf-8 -*-
"""Research module protocols."""
from __future__ import annotations

from typing import Any, Protocol

from scanner.research.comparison import ComparisonResult
from scanner.research.experiment import Experiment
from scanner.research.report import ResearchReport


class ExperimentRunnerProtocol(Protocol):
    def run(self, *, title: str, rows: list[dict], **kwargs: Any) -> Experiment: ...


class MetricsEngineProtocol(Protocol):
    def compute(self, rows: list[dict]) -> dict[str, Any]: ...


class ComparisonEngineProtocol(Protocol):
    def compare(self, rows_a: list[dict], rows_b: list[dict], **kwargs: Any) -> ComparisonResult: ...


class ResearchEngineProtocol(Protocol):
    def run_experiment(self, *, title: str, rows: list[dict], **kwargs: Any) -> Experiment: ...
    def compare(self, rows_a: list[dict], rows_b: list[dict], **kwargs: Any) -> ComparisonResult: ...
    def statistics(self, rows: list[dict]) -> dict[str, Any]: ...
    def generate_report(self, experiment_id: str) -> ResearchReport: ...
    def history(self, *, limit: int = 50) -> list[Experiment]: ...
