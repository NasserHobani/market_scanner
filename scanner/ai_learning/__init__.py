# -*- coding: utf-8 -*-
"""AI Learning & Reflection Engine — advisory continuous learning."""
from __future__ import annotations

from typing import Any

from .hypothesis_generator import HypothesisGenerator, HYPOTHESIS_VERSION
from .improvement_candidates import ImprovementCandidates, RANKING_VERSION
from .knowledge_proposals import KnowledgeProposals, PROPOSAL_VERSION
from .learning_engine import LearningEngine, LEARNING_VERSION
from .learning_history import LearningHistory, HISTORY_SCHEMA_VERSION
from .lesson_generator import LessonGenerator, LESSON_VERSION
from .lesson_repository import LessonRepository, LESSON_SCHEMA_VERSION, LESSON_STATUSES
from .pattern_detector import PatternDetector, PATTERN_VERSION
from .reflection import ReflectionEngine, REFLECTION_VERSION
from .reflection_report import ReflectionReport, REPORT_VERSION


class LearningService:
    """Public API for the AI Learning & Reflection Engine."""

    def __init__(self,
                 engine: LearningEngine | None = None) -> None:
        self._engine = engine or LearningEngine()

    def run_cycle(self, **kwargs) -> dict[str, Any]:
        return self._engine.run_cycle(**kwargs)

    def reflect(self, scope: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._engine.reflect(scope)

    def lessons(self, status: str = "") -> list[dict[str, Any]]:
        return self._engine.list_lessons(status)

    def proposals(self) -> list[dict[str, Any]]:
        return self._engine.list_proposals()

    def hypotheses(self) -> list[dict[str, Any]]:
        return self._engine.list_hypotheses()

    def reports(self) -> list[dict[str, Any]]:
        return self._engine.list_reports()

    def update_lesson_status(self, lesson_id: str, status: str) -> bool:
        return self._engine.update_lesson_status(lesson_id, status)

    def to_ui_model(self) -> dict[str, Any]:
        lessons = self._engine.list_lessons()
        proposals = self._engine.list_proposals()
        hypotheses = self._engine.list_hypotheses()
        reports = self._engine.list_reports()
        candidates = ImprovementCandidates().rank(
            lessons=lessons, proposals=proposals, hypotheses=hypotheses,
        )
        return {
            "available": True,
            "version": LEARNING_VERSION,
            "advisory_only": True,
            **ReflectionReport().to_ui_model(
                lessons=lessons,
                proposals=proposals,
                hypotheses=hypotheses,
                candidates=candidates,
                reports=reports,
            ),
        }


__all__ = [
    "HISTORY_SCHEMA_VERSION",
    "HYPOTHESIS_VERSION",
    "LearningEngine",
    "LearningHistory",
    "LearningService",
    "LEARNING_VERSION",
    "LESSON_SCHEMA_VERSION",
    "LESSON_STATUSES",
    "LESSON_VERSION",
    "LessonGenerator",
    "LessonRepository",
    "PATTERN_VERSION",
    "PatternDetector",
    "PROPOSAL_VERSION",
    "KnowledgeProposals",
    "RANKING_VERSION",
    "REFLECTION_VERSION",
    "REPORT_VERSION",
    "ReflectionEngine",
    "ReflectionReport",
    "HypothesisGenerator",
    "ImprovementCandidates",
]
