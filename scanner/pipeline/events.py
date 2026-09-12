# -*- coding: utf-8 -*-
"""Internal domain events for the production pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DomainEvent:
    """Base domain event."""

    event_type: str
    execution_id: str
    event_id: str = ""
    timestamp: str = field(default_factory=_now)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "execution_id": self.execution_id,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }


def knowledge_captured(execution_id: str, event_id: str = "",
                       payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("KnowledgeCaptured", execution_id, event_id,
                       payload=payload or {})


def reasoning_completed(execution_id: str, event_id: str = "",
                        payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("ReasoningCompleted", execution_id, event_id,
                       payload=payload or {})


def intelligence_completed(execution_id: str, event_id: str = "",
                           payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("IntelligenceCompleted", execution_id, event_id,
                       payload=payload or {})


def similarity_completed(execution_id: str, event_id: str = "",
                         payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("SimilarityCompleted", execution_id, event_id,
                       payload=payload or {})


def pipeline_completed(execution_id: str, event_id: str = "",
                       payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("PipelineCompleted", execution_id, event_id,
                       payload=payload or {})


def pipeline_failed(execution_id: str, event_id: str = "",
                    payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("PipelineFailed", execution_id, event_id,
                       payload=payload or {})


def stage_started(execution_id: str, event_id: str = "",
                  payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("StageStarted", execution_id, event_id,
                       payload=payload or {})


def stage_completed(execution_id: str, event_id: str = "",
                    payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("StageCompleted", execution_id, event_id,
                       payload=payload or {})


def stage_failed(execution_id: str, event_id: str = "",
                 payload: dict[str, Any] | None = None) -> DomainEvent:
    return DomainEvent("StageFailed", execution_id, event_id,
                       payload=payload or {})


# Backward-compatible aliases
KnowledgeCaptured = knowledge_captured
ReasoningCompleted = reasoning_completed
IntelligenceCompleted = intelligence_completed
SimilarityCompleted = similarity_completed
PipelineCompleted = pipeline_completed
PipelineFailed = pipeline_failed
StageStarted = stage_started
StageCompleted = stage_completed
StageFailed = stage_failed
