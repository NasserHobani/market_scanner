# -*- coding: utf-8 -*-
"""Deterministic workflow definition."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStage(str, Enum):
    LOAD_MARKET = "load_market"
    KNOWLEDGE = "knowledge"
    REASONING = "reasoning"
    SIMILARITY = "similarity"
    RESEARCH = "research"
    PREDICTION = "prediction"
    DECISION_AI = "decision_ai"
    AGGREGATION = "aggregation"


DEFAULT_STAGE_ORDER: list[str] = [
    WorkflowStage.LOAD_MARKET.value,
    WorkflowStage.KNOWLEDGE.value,
    WorkflowStage.REASONING.value,
    WorkflowStage.SIMILARITY.value,
    WorkflowStage.RESEARCH.value,
    WorkflowStage.PREDICTION.value,
    WorkflowStage.DECISION_AI.value,
    WorkflowStage.AGGREGATION.value,
]

CACHEABLE_STAGES = frozenset({
    WorkflowStage.KNOWLEDGE.value,
    WorkflowStage.SIMILARITY.value,
    WorkflowStage.RESEARCH.value,
})

OPTIONAL_STAGES = frozenset({
    WorkflowStage.RESEARCH.value,
    WorkflowStage.PREDICTION.value,
    WorkflowStage.DECISION_AI.value,
})


@dataclass
class WorkflowDefinition:
    """Workflow configuration."""

    name: str = "market_analysis"
    stages: list[str] = field(default_factory=lambda: list(DEFAULT_STAGE_ORDER))
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stages": list(self.stages),
            "version": self.version,
        }
