# -*- coding: utf-8 -*-
"""Pipeline execution state primitives."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


PIPELINE_VERSION = "2.1.0"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class PipelineType(str, Enum):
    SCAN = "scan"
    TRADE = "trade"
    REBUILD_TRADE = "rebuild_trade"
    REBUILD_MARKET = "rebuild_market"


class StageName(str, Enum):
    KNOWLEDGE = "knowledge"
    SIMILARITY = "similarity"
    REASONING = "reasoning"
    INTELLIGENCE = "intelligence"
    PERSIST = "persist"


@dataclass
class StageResult:
    stage: str
    status: str
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0
    retry_count: int = 0
    error: str | None = None
    output_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 2),
            "retry_count": self.retry_count,
            "error": self.error,
            "output_keys": list(self.output_keys),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> StageResult:
        return cls(
            stage=row["stage"],
            status=row["status"],
            started_at=row.get("started_at") or "",
            completed_at=row.get("completed_at") or "",
            duration_ms=float(row.get("duration_ms") or 0),
            retry_count=int(row.get("retry_count") or 0),
            error=row.get("error"),
            output_keys=list(row.get("output_keys") or []),
        )


@dataclass
class PipelineExecution:
    execution_id: str
    pipeline_type: str
    pipeline_version: str = PIPELINE_VERSION
    status: str = PipelineStatus.PENDING.value
    event_id: str = ""
    strategy_id: str = "default"
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0
    stages: list[StageResult] = field(default_factory=list)
    knowledge_ids: dict[str, Any] = field(default_factory=dict)
    similarity_summary: dict[str, Any] | None = None
    reasoning_review: dict[str, Any] | None = None
    intelligence_report: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "pipeline_type": self.pipeline_type,
            "pipeline_version": self.pipeline_version,
            "status": self.status,
            "event_id": self.event_id,
            "strategy_id": self.strategy_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 2),
            "stages": [s.to_dict() for s in self.stages],
            "knowledge_ids": dict(self.knowledge_ids),
            "similarity_summary": self.similarity_summary,
            "reasoning_review": self.reasoning_review,
            "intelligence_report": self.intelligence_report,
            "errors": list(self.errors),
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> PipelineExecution:
        return cls(
            execution_id=row["execution_id"],
            pipeline_type=row["pipeline_type"],
            pipeline_version=row.get("pipeline_version") or PIPELINE_VERSION,
            status=row.get("status") or PipelineStatus.PENDING.value,
            event_id=row.get("event_id") or "",
            strategy_id=row.get("strategy_id") or "default",
            started_at=row.get("started_at") or "",
            completed_at=row.get("completed_at") or "",
            duration_ms=float(row.get("duration_ms") or 0),
            stages=[StageResult.from_dict(s) for s in (row.get("stages") or [])],
            knowledge_ids=dict(row.get("knowledge_ids") or {}),
            similarity_summary=row.get("similarity_summary"),
            reasoning_review=row.get("reasoning_review"),
            intelligence_report=row.get("intelligence_report"),
            errors=list(row.get("errors") or []),
            metrics=dict(row.get("metrics") or {}),
            metadata=dict(row.get("metadata") or {}),
        )
