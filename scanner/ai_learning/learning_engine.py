# -*- coding: utf-8 -*-
"""Learning engine — orchestrates reflection, lessons, proposals, hypotheses."""
from __future__ import annotations

from typing import Any

from scanner.ai_advisor.evaluation.advisor_dataset import AdvisorEvaluationDataset

from .hypothesis_generator import HypothesisGenerator
from .improvement_candidates import ImprovementCandidates
from .knowledge_proposals import KnowledgeProposals
from .learning_history import LearningHistory
from .learning_lock import learning_cycle_lock
from .lesson_generator import LessonGenerator
from .lesson_repository import LessonRepository
from .pattern_detector import PatternDetector
from .reflection import ReflectionEngine
from .reflection_report import ReflectionReport

LEARNING_VERSION = "1.0.0"


class LearningEngine:
    """Transform completed evaluations into structured lessons and proposals.

    Learning is advisory. Research validates. Humans approve.
    Never modifies Knowledge, Prediction, Optimization, Decision, or Trading.
    """

    def __init__(self,
                 dataset: AdvisorEvaluationDataset | None = None,
                 lessons: LessonRepository | None = None,
                 history: LearningHistory | None = None) -> None:
        self._dataset = dataset or AdvisorEvaluationDataset()
        self._lessons = lessons or LessonRepository()
        self._history = history or LearningHistory()
        self._reflection = ReflectionEngine()
        self._patterns = PatternDetector()
        self._lesson_gen = LessonGenerator()
        self._proposals = KnowledgeProposals()
        self._hypotheses = HypothesisGenerator()
        self._ranking = ImprovementCandidates()
        self._reports = ReflectionReport()

    def run_cycle(self, *,
                  scope: dict[str, Any] | None = None,
                  trade_outcomes: list[dict[str, Any]] | None = None,
                  research_results: list[dict[str, Any]] | None = None,
                  optimization_results: list[dict[str, Any]] | None = None,
                  prediction_results: list[dict[str, Any]] | None = None,
                  period: str = "daily",
                  persist: bool = True) -> dict[str, Any]:
        """Full learning cycle: reflect → detect → generate → propose → rank → report."""
        evaluations = self._dataset.list_all()
        context = {
            "trade_outcomes": trade_outcomes or [],
            "research_results": research_results or [],
            "optimization_results": optimization_results or [],
            "prediction_results": prediction_results or [],
        }

        reflection = self._reflection.reflect(
            evaluations=evaluations,
            scope=scope,
            trade_outcomes=trade_outcomes,
            research_results=research_results,
            optimization_results=optimization_results,
        )

        scoped_evals = reflection.get("evaluations", evaluations)
        patterns = self._patterns.detect(scoped_evals, context)
        lessons = self._lesson_gen.generate(patterns, scoped_evals)
        proposals = self._proposals.generate(lessons)
        hypotheses = self._hypotheses.generate(lessons, patterns)
        candidates = self._ranking.rank(lessons=lessons, proposals=proposals, hypotheses=hypotheses)

        report = self._reports.generate(
            reflection=reflection,
            lessons=lessons,
            proposals=proposals,
            hypotheses=hypotheses,
            candidates=candidates,
            evaluations=evaluations,
            period=period,
        )

        if persist:
            with learning_cycle_lock():
                for lesson in lessons:
                    self._lessons.upsert(lesson)
                for proposal in proposals:
                    self._history.save_proposal(proposal)
                for hypothesis in hypotheses:
                    self._history.save_hypothesis(hypothesis)
                self._history.save_report(report)

        return {
            "learning_version": LEARNING_VERSION,
            "reflection": reflection,
            "patterns": patterns,
            "lessons": lessons,
            "proposals": proposals,
            "hypotheses": hypotheses,
            "candidates": candidates,
            "report": report,
        }

    def reflect(self, scope: dict[str, Any] | None = None) -> dict[str, Any]:
        evaluations = self._dataset.list_all()
        return self._reflection.reflect(evaluations=evaluations, scope=scope)

    def list_lessons(self, status: str = "") -> list[dict[str, Any]]:
        if status:
            return self._lessons.by_status(status)
        return self._lessons.list_all()

    def update_lesson_status(self, lesson_id: str, status: str) -> bool:
        return self._lessons.update_status(lesson_id, status)

    def list_proposals(self) -> list[dict[str, Any]]:
        return self._history.list_proposals()

    def list_hypotheses(self) -> list[dict[str, Any]]:
        return self._history.list_hypotheses()

    def list_reports(self) -> list[dict[str, Any]]:
        return self._history.list_reports()
