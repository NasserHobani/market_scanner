# -*- coding: utf-8 -*-
"""Analysis result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

ORCHESTRATION_VERSION = "1.0.0"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class StageExecutionResult:
    stage: str
    status: str
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0
    retry_count: int = 0
    cached: bool = False
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
            "cached": self.cached,
            "error": self.error,
            "output_keys": list(self.output_keys),
        }


@dataclass
class MarketAnalysis:
    """Final aggregated market analysis output."""

    analysis_id: str
    symbol: str = ""
    market: str = ""
    timeframe: str = ""
    status: str = AnalysisStatus.COMPLETED.value
    knowledge: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)
    similarity: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    prediction: dict[str, Any] = field(default_factory=dict)
    decision_review: dict[str, Any] = field(default_factory=dict)
    execution_trace: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "status": self.status,
            "knowledge": dict(self.knowledge),
            "reasoning": dict(self.reasoning),
            "similarity": dict(self.similarity),
            "research": dict(self.research),
            "prediction": dict(self.prediction),
            "decision_review": dict(self.decision_review),
            "execution_trace": list(self.execution_trace),
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "version": ORCHESTRATION_VERSION,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
