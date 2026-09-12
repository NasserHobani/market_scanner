# -*- coding: utf-8 -*-
"""Optimization experiment persistence."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


OPTIMIZATION_VERSION = "1.0.0"
DEFAULT_STORE = Path("data/optimization/experiments.jsonl")


class OptimizationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OptimizationExperiment:
    """Reproducible optimization experiment."""

    experiment_id: str
    title: str
    method: str = "grid"
    description: str = ""
    parameter_space: dict[str, Any] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=dict)
    status: str = OptimizationStatus.PENDING.value
    version: str = OPTIMIZATION_VERSION
    started_at: str = ""
    ended_at: str = ""
    results: dict[str, Any] = field(default_factory=dict)
    report_id: str = ""
    trade_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "title": self.title,
            "method": self.method,
            "description": self.description,
            "parameter_space": dict(self.parameter_space),
            "configuration": dict(self.configuration),
            "status": self.status,
            "version": self.version,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "results": dict(self.results),
            "report_id": self.report_id,
            "trade_count": self.trade_count,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> OptimizationExperiment:
        return cls(
            experiment_id=row["experiment_id"],
            title=row.get("title") or "",
            method=row.get("method") or "grid",
            description=row.get("description") or "",
            parameter_space=dict(row.get("parameter_space") or {}),
            configuration=dict(row.get("configuration") or {}),
            status=row.get("status") or OptimizationStatus.PENDING.value,
            version=row.get("version") or OPTIMIZATION_VERSION,
            started_at=row.get("started_at") or "",
            ended_at=row.get("ended_at") or "",
            results=dict(row.get("results") or {}),
            report_id=row.get("report_id") or "",
            trade_count=int(row.get("trade_count") or 0),
        )


def new_experiment_id() -> str:
    return f"opt_{uuid.uuid4().hex[:16]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExperimentRegistry:
    """Append-only optimization experiment persistence."""

    def __init__(self, path: Path | str = DEFAULT_STORE) -> None:
        self.path = Path(path)

    def save(self, experiment: OptimizationExperiment) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(experiment.to_dict(), ensure_ascii=False, default=str) + "\n")
        return experiment.experiment_id

    def _read_all(self) -> list[OptimizationExperiment]:
        if not self.path.exists():
            return []
        out: list[OptimizationExperiment] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(OptimizationExperiment.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
        return out

    def load(self, experiment_id: str) -> OptimizationExperiment | None:
        for exp in reversed(self._read_all()):
            if exp.experiment_id == experiment_id:
                return exp
        return None

    def history(self, limit: int = 50) -> list[OptimizationExperiment]:
        return list(reversed(self._read_all()))[:limit]

    def list_all(self, limit: int = 50) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.history(limit)]
