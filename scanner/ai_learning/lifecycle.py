# -*- coding: utf-8 -*-
"""Explicit learning lifecycle states — lessons are not model training."""
from __future__ import annotations

from enum import Enum
from typing import Any

LIFECYCLE_VERSION = "1.0.0"


class LearningLifecycleState(str, Enum):
    OBSERVED = "OBSERVED"
    EVALUATED = "EVALUATED"
    LEARNED_AS_LESSON = "LEARNED_AS_LESSON"
    HYPOTHESIS_CREATED = "HYPOTHESIS_CREATED"
    RESEARCHED = "RESEARCHED"
    VALIDATED = "VALIDATED"
    CANDIDATE_FOR_PROMOTION = "CANDIDATE_FOR_PROMOTION"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"


# UI labels — never claim "AI learned" for a lesson alone
UI_LABELS_EN = {
    LearningLifecycleState.OBSERVED.value: "Pattern observed",
    LearningLifecycleState.EVALUATED.value: "Evaluated",
    LearningLifecycleState.LEARNED_AS_LESSON.value: "Lesson recorded",
    LearningLifecycleState.HYPOTHESIS_CREATED.value: "Hypothesis generated",
    LearningLifecycleState.RESEARCHED.value: "Research validated",
    LearningLifecycleState.VALIDATED.value: "Evidence validated",
    LearningLifecycleState.CANDIDATE_FOR_PROMOTION.value: "Model candidate",
    LearningLifecycleState.APPROVED.value: "Approved for promotion",
    LearningLifecycleState.DEPLOYED.value: "Model active",
}

UI_LABELS_AR = {
    LearningLifecycleState.OBSERVED.value: "نمط مرصود",
    LearningLifecycleState.EVALUATED.value: "تم التقييم",
    LearningLifecycleState.LEARNED_AS_LESSON.value: "دُرِّس مُسجَّل",
    LearningLifecycleState.HYPOTHESIS_CREATED.value: "فُرضية مُولَّدة",
    LearningLifecycleState.RESEARCHED.value: "بحث مُحقَّق",
    LearningLifecycleState.VALIDATED.value: "دليل مُحقَّق",
    LearningLifecycleState.CANDIDATE_FOR_PROMOTION.value: "نموذج مرشَّح",
    LearningLifecycleState.APPROVED.value: "معتمد للترقية",
    LearningLifecycleState.DEPLOYED.value: "نموذج نشط",
}


def lesson_lifecycle_state(lesson: dict[str, Any]) -> str:
    status = (lesson.get("status") or "NEW").upper()
    if status in ("VALIDATED", "APPROVED"):
        return LearningLifecycleState.VALIDATED.value
    if lesson.get("hypothesis_id"):
        return LearningLifecycleState.HYPOTHESIS_CREATED.value
    return LearningLifecycleState.LEARNED_AS_LESSON.value


def ui_label(state: str, *, lang: str = "en") -> str:
    if lang == "ar":
        return UI_LABELS_AR.get(state, state)
    return UI_LABELS_EN.get(state, state)


def annotate_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    state = lesson_lifecycle_state(lesson)
    return {
        **lesson,
        "lifecycle_state": state,
        "lifecycle_label": ui_label(state),
        "lifecycle_label_ar": ui_label(state, lang="ar"),
        "is_model_training": False,
        "advisory_only": True,
    }
