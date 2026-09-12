# -*- coding: utf-8 -*-
"""Experiment model and persistence."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


RESEARCH_VERSION = "1.0.0"
DEFAULT_STORE = Path("data/research/experiments.jsonl")


class ExperimentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Experiment:
    """Reproducible research experiment."""

    experiment_id: str
    title: str
    description: str = ""
    hypothesis: dict[str, Any] = field(default_factory=dict)
    dataset: dict[str, Any] = field(default_factory=dict)
    configuration: dict[str, Any] = field(default_factory=dict)
    status: str = ExperimentStatus.PENDING.value
    version: str = RESEARCH_VERSION
    started_at: str = ""
    ended_at: str = ""
    results: dict[str, Any] = field(default_factory=dict)
    report_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "title": self.title,
            "description": self.description,
            "hypothesis": dict(self.hypothesis),
            "dataset": dict(self.dataset),
            "configuration": dict(self.configuration),
            "status": self.status,
            "version": self.version,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "results": dict(self.results),
            "report_id": self.report_id,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Experiment:
        return cls(
            experiment_id=row["experiment_id"],
            title=row.get("title") or "",
            description=row.get("description") or "",
            hypothesis=dict(row.get("hypothesis") or {}),
            dataset=dict(row.get("dataset") or {}),
            configuration=dict(row.get("configuration") or {}),
            status=row.get("status") or ExperimentStatus.PENDING.value,
            version=row.get("version") or RESEARCH_VERSION,
            started_at=row.get("started_at") or "",
            ended_at=row.get("ended_at") or "",
            results=dict(row.get("results") or {}),
            report_id=row.get("report_id") or "",
        )


def new_experiment_id() -> str:
    return f"rex_{uuid.uuid4().hex[:16]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExperimentStore:
    """Append-only experiment persistence."""

    def __init__(self, path: Path | str = DEFAULT_STORE) -> None:
        self.path = Path(path)

    def save(self, experiment: Experiment) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(experiment.to_dict(), ensure_ascii=False, default=str) + "\n")
        return experiment.experiment_id

    def _read_all(self) -> list[Experiment]:
        if not self.path.exists():
            return []
        out: list[Experiment] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Experiment.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def load(self, experiment_id: str) -> Experiment:
        for ex in self._read_all():
            if ex.experiment_id == experiment_id:
                return ex
        raise KeyError(f"experiment not found: {experiment_id}")

    def history(self, *, limit: int = 50) -> list[Experiment]:
        rows = self._read_all()
        rows.sort(key=lambda e: e.started_at or "", reverse=True)
        return rows[:limit]
