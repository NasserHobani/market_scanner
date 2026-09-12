# -*- coding: utf-8 -*-
"""Reflection reports — daily, weekly, monthly learning reports."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from scanner.ai_advisor.evaluation.leaderboard import ProviderLeaderboard

REPORT_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReflectionReport:
    """Generate learning reports with lessons, failures, proposals, experiments."""

    def __init__(self) -> None:
        self._leaderboard = ProviderLeaderboard()

    def generate(self, *,
                 reflection: dict[str, Any],
                 lessons: list[dict[str, Any]],
                 proposals: list[dict[str, Any]],
                 hypotheses: list[dict[str, Any]],
                 candidates: list[dict[str, Any]],
                 evaluations: list[dict[str, Any]],
                 period: str = "daily") -> dict[str, Any]:
        filtered_evals = self._filter_period(evaluations, period)
        provider_comparison = self._leaderboard.compute(filtered_evals)

        top_lessons = sorted(lessons, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
        top_failures = reflection.get("failures", {})
        top_successes = reflection.get("successes", {})

        return {
            "report_id": f"lrpt_{period}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "period": period,
            "report_version": REPORT_VERSION,
            "generated_at": _now(),
            "sample_size": reflection.get("sample_size", 0),
            "accuracy": reflection.get("accuracy"),
            "top_lessons": top_lessons,
            "top_failures": top_failures,
            "top_successes": top_successes,
            "recurring_problems": self._recurring_problems(reflection, lessons),
            "new_proposals": [p for p in proposals if p.get("status") == "NEW"][:10],
            "suggested_experiments": hypotheses[:10],
            "provider_comparison": provider_comparison,
            "improvement_candidates": candidates[:10],
            "scope": reflection.get("scope", {}),
        }

    def daily(self, **kwargs) -> dict[str, Any]:
        return self.generate(period="daily", **kwargs)

    def weekly(self, **kwargs) -> dict[str, Any]:
        return self.generate(period="weekly", **kwargs)

    def monthly(self, **kwargs) -> dict[str, Any]:
        return self.generate(period="monthly", **kwargs)

    def to_ui_model(self, *,
                    lessons: list[dict[str, Any]],
                    proposals: list[dict[str, Any]],
                    hypotheses: list[dict[str, Any]],
                    candidates: list[dict[str, Any]],
                    reports: list[dict[str, Any]]) -> dict[str, Any]:
        cards = []
        for lesson in lessons[-20:]:
            cards.append(self._lesson_card(lesson))
        return {
            "lessons": lessons[-20:],
            "lesson_cards": cards,
            "top_insights": candidates[:5],
            "knowledge_proposals": proposals[-10:],
            "suggested_experiments": hypotheses[-10:],
            "reflection_timeline": [
                {
                    "report_id": r.get("report_id"),
                    "period": r.get("period"),
                    "generated_at": r.get("generated_at"),
                    "accuracy": r.get("accuracy"),
                    "sample_size": r.get("sample_size"),
                    "top_lesson_count": len(r.get("top_lessons", [])),
                }
                for r in reports[-10:]
            ],
        }

    @staticmethod
    def _lesson_card(lesson: dict[str, Any]) -> dict[str, Any]:
        from .lifecycle import annotate_lesson, ui_label, lesson_lifecycle_state

        conf = lesson.get("confidence_summary") or {}
        examples = lesson.get("trade_examples") or []
        rs = [float(ex["r_multiple"]) for ex in examples if ex.get("r_multiple") is not None]
        wins = sum(1 for ex in examples if str(ex.get("outcome", "")).upper() in ("WON", "WIN")
                   or (ex.get("r_multiple") is not None and float(ex["r_multiple"]) > 0))
        state = lesson_lifecycle_state(lesson)
        return {
            "lesson_id": lesson.get("lesson_id"),
            "pattern": lesson.get("title_ar") or lesson.get("title"),
            "pattern_en": lesson.get("title"),
            "failure_type": lesson.get("failure_type") or lesson.get("pattern_type"),
            "title_ar": lesson.get("title_ar"),
            "description_ar": lesson.get("description_ar") or lesson.get("description"),
            "sample_size": lesson.get("sample_size", 0),
            "win_rate": round(wins / len(examples) * 100, 1) if examples else None,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
            "affected_symbols": lesson.get("affected_symbols") or [],
            "affected_markets": lesson.get("affected_markets") or [],
            "affected_timeframes": lesson.get("affected_timeframes") or [],
            "provider": lesson.get("provider") or (lesson.get("affected_providers") or [""])[0],
            "confidence_avg": conf.get("avg"),
            "recommendation": lesson.get("recommendation_ar") or lesson.get("recommendation"),
            "recommendation_strength": lesson.get("recommendation_strength"),
            "is_failure": lesson.get("is_failure", True),
            "lifecycle_state": state,
            "lifecycle_label": ui_label(state),
            "lifecycle_label_ar": ui_label(state, lang="ar"),
            "is_model_training": False,
            "lesson": annotate_lesson(lesson),
        }

    @staticmethod
    def _filter_period(evaluations: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
        if period == "daily":
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return [e for e in evaluations if (e.get("execution_date") or "").startswith(today)]
        if period == "weekly":
            since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            return [e for e in evaluations if (e.get("execution_date") or "") >= since]
        if period == "monthly":
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
            return [e for e in evaluations if (e.get("execution_date") or "") >= since]
        return evaluations

    @staticmethod
    def _recurring_problems(reflection: dict[str, Any],
                            lessons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        failure_reasons = reflection.get("failures", {}).get("top_reasons", [])
        lesson_types = {}
        for lesson in lessons:
            pt = lesson.get("pattern_type", "unknown")
            lesson_types[pt] = lesson_types.get(pt, 0) + 1

        problems = []
        for reason in failure_reasons:
            problems.append({
                "type": reason.get("reason"),
                "count": reason.get("count"),
                "source": "reflection",
            })
        for ptype, count in sorted(lesson_types.items(), key=lambda x: x[1], reverse=True)[:5]:
            problems.append({
                "type": ptype,
                "count": count,
                "source": "lessons",
            })
        return problems[:10]
