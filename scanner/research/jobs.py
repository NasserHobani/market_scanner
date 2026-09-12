# -*- coding: utf-8 -*-
"""Research job persistence — append-only jobs.jsonl."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


JOBS_PATH = Path("data/research/jobs.jsonl")
LOCK_PATH = Path("data/research/.research_lock")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class ResearchJob:
    job_id: str
    trigger_type: str
    status: str = JobStatus.PENDING.value
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    hypothesis_id: str = ""
    dataset_fingerprint: str = ""
    experiment_id: str = ""
    error: str = ""
    reason: str = ""
    configuration: dict[str, Any] = field(default_factory=dict)
    sample_counts: dict[str, Any] = field(default_factory=dict)
    progress_stage: str = ""
    duration_ms: float = 0.0
    automatic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "trigger_type": self.trigger_type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "hypothesis_id": self.hypothesis_id,
            "dataset_fingerprint": self.dataset_fingerprint,
            "experiment_id": self.experiment_id,
            "error": self.error,
            "reason": self.reason,
            "configuration": dict(self.configuration),
            "sample_counts": dict(self.sample_counts),
            "progress_stage": self.progress_stage,
            "duration_ms": self.duration_ms,
            "automatic": self.automatic,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> ResearchJob:
        return cls(
            job_id=row["job_id"],
            trigger_type=row.get("trigger_type", "manual"),
            status=row.get("status", JobStatus.PENDING.value),
            created_at=row.get("created_at", ""),
            started_at=row.get("started_at", ""),
            completed_at=row.get("completed_at", ""),
            hypothesis_id=row.get("hypothesis_id", ""),
            dataset_fingerprint=row.get("dataset_fingerprint", ""),
            experiment_id=row.get("experiment_id", ""),
            error=row.get("error", ""),
            reason=row.get("reason", ""),
            configuration=dict(row.get("configuration") or {}),
            sample_counts=dict(row.get("sample_counts") or {}),
            progress_stage=row.get("progress_stage", ""),
            duration_ms=float(row.get("duration_ms") or 0),
            automatic=bool(row.get("automatic", True)),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return f"rjob_{uuid.uuid4().hex[:16]}"


class JobStore:
    """Append-only job store with in-memory index for updates."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else JOBS_PATH

    def append(self, job: ResearchJob) -> str:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not job.created_at:
            job.created_at = _now()
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(job.to_dict(), ensure_ascii=False, default=str) + "\n")
        return job.job_id

    def list_all(self) -> list[ResearchJob]:
        if not self._path.exists():
            return []
        jobs: dict[str, ResearchJob] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                j = ResearchJob.from_dict(json.loads(line))
                jobs[j.job_id] = j
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> ResearchJob | None:
        for j in self.list_all():
            if j.job_id == job_id:
                return j
        return None

    def update(self, job: ResearchJob) -> None:
        self.append(job)

    def find_duplicate(self, *, hypothesis_id: str, fingerprint: str,
                       configuration: dict[str, Any]) -> ResearchJob | None:
        cfg_key = json.dumps(configuration, sort_keys=True, default=str)
        for j in self.list_all():
            if j.status not in (JobStatus.COMPLETED.value, JobStatus.RUNNING.value):
                continue
            if j.hypothesis_id == hypothesis_id and j.dataset_fingerprint == fingerprint:
                jcfg = json.dumps(j.configuration, sort_keys=True, default=str)
                if jcfg == cfg_key:
                    return j
        return None

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for j in self.list_all():
            counts[j.status] = counts.get(j.status, 0) + 1
        return counts

    def running_for_strategy(self, strategy_key: str) -> ResearchJob | None:
        for j in self.list_all():
            if j.status != JobStatus.RUNNING.value:
                continue
            if j.configuration.get("strategy_key", "default") == strategy_key:
                return j
        return None
