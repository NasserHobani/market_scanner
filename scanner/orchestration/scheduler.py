# -*- coding: utf-8 -*-
"""Workflow scheduler — queue and track analysis jobs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisJob:
    job_id: str
    symbol: str
    status: str = JobStatus.QUEUED.value
    params: dict[str, Any] = field(default_factory=dict)
    analysis_id: str = ""
    error: str = ""
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "symbol": self.symbol,
            "status": self.status,
            "params": dict(self.params),
            "analysis_id": self.analysis_id,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class AnalysisScheduler:
    """Simple in-memory job scheduler."""

    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._counter = 0

    def enqueue(self, symbol: str, **params: Any) -> AnalysisJob:
        self._counter += 1
        job = AnalysisJob(
            job_id=f"job_{self._counter:06d}",
            symbol=symbol,
            params=dict(params),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._jobs[job.job_id] = job
        return job

    def run_next(self, runner: Callable[..., Any]) -> AnalysisJob | None:
        for job in self._jobs.values():
            if job.status != JobStatus.QUEUED.value:
                continue
            job.status = JobStatus.RUNNING.value
            try:
                result = runner(symbol=job.symbol, **job.params)
                job.analysis_id = result.analysis_id
                job.status = JobStatus.COMPLETED.value
            except Exception as exc:
                job.status = JobStatus.FAILED.value
                job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc).isoformat()
            return job
        return None

    def list_jobs(self, *, status: str | None = None) -> list[AnalysisJob]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def get_job(self, job_id: str) -> AnalysisJob | None:
        return self._jobs.get(job_id)
