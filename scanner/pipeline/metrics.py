# -*- coding: utf-8 -*-
"""Pipeline observability metrics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .state import PipelineExecution, StageResult


@dataclass
class PipelineMetrics:
    """Aggregated pipeline execution metrics."""

    total_executions: int = 0
    completed: int = 0
    failed: int = 0
    skipped_stages: int = 0
    total_retries: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    stage_durations: dict[str, float] = field(default_factory=dict)
    stage_failures: dict[str, int] = field(default_factory=dict)
    records_processed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_executions": self.total_executions,
            "completed": self.completed,
            "failed": self.failed,
            "skipped_stages": self.skipped_stages,
            "total_retries": self.total_retries,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "stage_durations": {k: round(v, 2) for k, v in self.stage_durations.items()},
            "stage_failures": dict(self.stage_failures),
            "records_processed": self.records_processed,
        }


class MetricsCollector:
    """Collect and aggregate pipeline metrics from execution history."""

    def from_execution(self, execution: PipelineExecution) -> dict[str, Any]:
        stage_metrics = {
            s.stage: {
                "duration_ms": s.duration_ms,
                "status": s.status,
                "retry_count": s.retry_count,
            }
            for s in execution.stages
        }
        return {
            "execution_id": execution.execution_id,
            "pipeline_type": execution.pipeline_type,
            "status": execution.status,
            "duration_ms": execution.duration_ms,
            "stage_metrics": stage_metrics,
            "records_processed": execution.metrics.get("records_processed", 0),
            "errors": list(execution.errors),
        }

    def aggregate(self, executions: list[PipelineExecution]) -> PipelineMetrics:
        metrics = PipelineMetrics()
        metrics.total_executions = len(executions)
        if not executions:
            return metrics

        durations: list[float] = []
        stage_dur: dict[str, list[float]] = {}

        for ex in executions:
            if ex.status == "completed":
                metrics.completed += 1
            elif ex.status == "failed":
                metrics.failed += 1
            durations.append(ex.duration_ms)
            metrics.records_processed += int(ex.metrics.get("records_processed") or 0)

            for stage in ex.stages:
                if stage.status == "skipped":
                    metrics.skipped_stages += 1
                metrics.total_retries += stage.retry_count
                if stage.status == "failed":
                    metrics.stage_failures[stage.stage] = (
                        metrics.stage_failures.get(stage.stage, 0) + 1
                    )
                if stage.duration_ms > 0:
                    stage_dur.setdefault(stage.stage, []).append(stage.duration_ms)

        metrics.total_duration_ms = sum(durations)
        metrics.avg_duration_ms = metrics.total_duration_ms / len(durations)
        metrics.stage_durations = {
            k: sum(v) / len(v) for k, v in stage_dur.items()
        }
        return metrics

    @staticmethod
    def stage_timing(stage: StageResult) -> dict[str, Any]:
        return {
            "stage": stage.stage,
            "duration_ms": stage.duration_ms,
            "status": stage.status,
            "retry_count": stage.retry_count,
        }
