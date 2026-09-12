# -*- coding: utf-8 -*-
"""Training job persistence."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

JOBS_PATH = Path("data/predictive/training_jobs.jsonl")
STATE_PATH = Path("data/predictive/training_state.json")


class TrainingJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_PROMOTED = "NOT_PROMOTED"


@dataclass
class TrainingJob:
    job_id: str
    trigger_type: str
    status: str = TrainingJobStatus.PENDING.value
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    dataset_id: str = ""
    model_id: str = ""
    error: str = ""
    reason: str = ""
    promotion_status: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "trigger_type": self.trigger_type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "dataset_id": self.dataset_id,
            "model_id": self.model_id,
            "error": self.error,
            "reason": self.reason,
            "promotion_status": self.promotion_status,
            "metrics": dict(self.metrics),
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> TrainingJob:
        return cls(
            job_id=row["job_id"],
            trigger_type=row.get("trigger_type", "manual"),
            status=row.get("status", TrainingJobStatus.PENDING.value),
            created_at=row.get("created_at", ""),
            started_at=row.get("started_at", ""),
            completed_at=row.get("completed_at", ""),
            dataset_id=row.get("dataset_id", ""),
            model_id=row.get("model_id", ""),
            error=row.get("error", ""),
            reason=row.get("reason", ""),
            promotion_status=row.get("promotion_status", ""),
            metrics=dict(row.get("metrics") or {}),
            duration_ms=float(row.get("duration_ms") or 0),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_job_id() -> str:
    return f"tjob_{uuid.uuid4().hex[:16]}"


class TrainingJobStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else JOBS_PATH

    def append(self, job: TrainingJob) -> str:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not job.created_at:
            job.created_at = _now()
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(job.to_dict(), ensure_ascii=False, default=str) + "\n")
        return job.job_id

    def list_all(self) -> list[TrainingJob]:
        if not self._path.exists():
            return []
        jobs: dict[str, TrainingJob] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                j = TrainingJob.from_dict(json.loads(line))
                jobs[j.job_id] = j
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> TrainingJob | None:
        for j in self.list_all():
            if j.job_id == job_id:
                return j
        return None


class TrainingState:
    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else STATE_PATH

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._defaults()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            out = self._defaults()
            out.update(data)
            return out
        except (json.JSONDecodeError, OSError):
            return self._defaults()

    def save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "trades_since_last_training": 0,
            "last_training_at": "",
            "last_dataset_id": "",
            "last_dataset_fingerprint": "",
            "active_model_id": "",
            "candidate_model_ids": [],
        }

    def increment_trade_counter(self) -> int:
        data = self.load()
        data["trades_since_last_training"] = int(data.get("trades_since_last_training") or 0) + 1
        self.save(data)
        return data["trades_since_last_training"]

    def reset_trade_counter(self, *, dataset_id: str = "", fingerprint: str = "",
                            model_id: str = "", promotion_status: str = "") -> None:
        data = self.load()
        data["trades_since_last_training"] = 0
        data["last_training_at"] = _now()
        if dataset_id:
            data["last_dataset_id"] = dataset_id
        if fingerprint:
            data["last_dataset_fingerprint"] = fingerprint
        if model_id and promotion_status == "ACTIVE":
            data["active_model_id"] = model_id
        elif model_id and promotion_status == "CANDIDATE_FOR_PROMOTION":
            candidates = list(data.get("candidate_model_ids") or [])
            if model_id not in candidates:
                candidates.append(model_id)
            data["candidate_model_ids"] = candidates[-10:]
        self.save(data)
