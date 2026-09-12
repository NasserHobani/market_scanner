# -*- coding: utf-8 -*-
"""Immutable execution context shared across all stages."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .result import ORCHESTRATION_VERSION, _now


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable context passed through the analysis workflow."""

    analysis_id: str
    symbol: str = ""
    market: str = ""
    timeframe: str = ""
    event_id: str = ""
    scan_source: dict[str, Any] = field(default_factory=dict)
    trade_rows: tuple[dict, ...] = ()
    knowledge: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, Any] = field(default_factory=dict)
    similarity: dict[str, Any] = field(default_factory=dict)
    research: dict[str, Any] = field(default_factory=dict)
    prediction: dict[str, Any] = field(default_factory=dict)
    decision_review: dict[str, Any] = field(default_factory=dict)
    feature_intelligence: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    stage_outputs: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ORCHESTRATION_VERSION

    def with_updates(self, **kwargs: Any) -> ExecutionContext:
        return replace(self, **kwargs)

    def with_stage_output(self, stage: str, output: dict[str, Any]) -> ExecutionContext:
        outputs = dict(self.stage_outputs)
        outputs[stage] = output
        return replace(self, stage_outputs=outputs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "event_id": self.event_id,
            "scan_source": dict(self.scan_source),
            "trade_rows": list(self.trade_rows),
            "knowledge": dict(self.knowledge),
            "reasoning": dict(self.reasoning),
            "similarity": dict(self.similarity),
            "research": dict(self.research),
            "prediction": dict(self.prediction),
            "decision_review": dict(self.decision_review),
            "feature_intelligence": dict(self.feature_intelligence),
            "metadata": dict(self.metadata),
            "stage_outputs": dict(self.stage_outputs),
            "schema_version": self.schema_version,
        }
