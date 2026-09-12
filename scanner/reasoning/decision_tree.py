# -*- coding: utf-8 -*-
"""Configurable reasoning flow — ordered decision stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .evidence import EvidenceBundle, EvidenceCategory


StageResult = dict[str, Any]
StageFn = Callable[[dict[str, Any], EvidenceBundle], StageResult]


@dataclass
class DecisionStage:
    """One node in the reasoning tree."""

    name: str
    category: str
    order: int
    description: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "order": self.order,
            "description": self.description,
            "required": self.required,
        }


DEFAULT_STAGES: list[DecisionStage] = [
    DecisionStage("trend", EvidenceCategory.TREND.value, 1,
                  "Assess directional bias"),
    DecisionStage("market_regime", EvidenceCategory.REGIME.value, 2,
                  "Assess macro market regime"),
    DecisionStage("liquidity", EvidenceCategory.LIQUIDITY.value, 3,
                  "Assess execution liquidity"),
    DecisionStage("structure", EvidenceCategory.STRUCTURE.value, 4,
                  "Assess market structure (BOS/CHOCH)"),
    DecisionStage("momentum", EvidenceCategory.MOMENTUM.value, 5,
                  "Assess momentum alignment"),
    DecisionStage("volume", EvidenceCategory.VOLUME.value, 6,
                  "Assess volume participation"),
    DecisionStage("risk", EvidenceCategory.RISK.value, 7,
                  "Assess location risk (S/R, premium)"),
    DecisionStage("historical_similarity", EvidenceCategory.HISTORY.value, 8,
                  "Assess historical performance evidence"),
    DecisionStage("recommendation_review", EvidenceCategory.RECOMMENDATION.value, 9,
                  "Review existing recommendation against evidence"),
]


@dataclass
class DecisionNodeResult:
    stage: str
    category: str
    status: str
    evidence_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "category": self.category,
            "status": self.status,
            "evidence_ids": list(self.evidence_ids),
            "notes": list(self.notes),
        }


@dataclass
class DecisionTreeResult:
    stages: list[DecisionNodeResult] = field(default_factory=list)
    halted_at: str | None = None
    completed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "halted_at": self.halted_at,
            "completed": self.completed,
        }


class DecisionTree:
    """Walks configurable stages and maps evidence to each node."""

    def __init__(self, stages: list[DecisionStage] | None = None) -> None:
        self.stages = sorted(stages or DEFAULT_STAGES, key=lambda s: s.order)

    def run(self, context: dict[str, Any], bundle: EvidenceBundle) -> DecisionTreeResult:
        result = DecisionTreeResult()
        for stage in self.stages:
            items = bundle.by_category(stage.category)
            if not items:
                status = "missing" if stage.required else "skipped"
                node = DecisionNodeResult(
                    stage=stage.name,
                    category=stage.category,
                    status=status,
                    notes=[f"No {stage.category} evidence"],
                )
                result.stages.append(node)
                if stage.required and status == "missing":
                    result.completed = False
                    result.halted_at = stage.name
                    break
                continue

            supports = sum(1 for e in items if e.direction == "supports")
            contradicts = sum(1 for e in items if e.direction == "contradicts")
            if contradicts > supports:
                status = "conflicted"
            elif supports > 0:
                status = "passed"
            else:
                status = "neutral"

            result.stages.append(DecisionNodeResult(
                stage=stage.name,
                category=stage.category,
                status=status,
                evidence_ids=[e.evidence_id for e in items],
                notes=[e.label for e in items],
            ))

            if status == "conflicted" and stage.required:
                result.completed = False
                result.halted_at = stage.name
                break

        return result
