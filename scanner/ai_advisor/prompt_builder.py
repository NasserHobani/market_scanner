# -*- coding: utf-8 -*-
"""Versioned, immutable advisor prompt templates."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .decision_package import DecisionPackage
from .unified_package import UnifiedDecisionPackage

# Package types accepted by prompt builder and validator (duck-typed protocol).
AdvisorPackage = DecisionPackage | UnifiedDecisionPackage

DEFAULT_PROMPT_VERSION = "advisor_prompt_v4"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PromptTemplate:
    """Immutable prompt template definition."""

    version: str
    created_at: str
    description: str
    rules: tuple[str, ...]
    system_prompt: str
    instructions: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "description": self.description,
            "rules": list(self.rules),
            "system_prompt": self.system_prompt,
            "instructions": self.instructions,
        }


@dataclass
class AdvisorPrompt:
    """Rendered prompt ready for an LLM provider."""

    version: str
    system_prompt: str
    user_prompt: str
    package_id: str
    event_id: str
    rules: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "package_id": self.package_id,
            "event_id": self.event_id,
            "rules": list(self.rules),
            "metadata": dict(self.metadata),
        }


# ── Immutable template registry ──────────────────────────────────────────────

_RULES = (
    "You are an AI Advisor in SHADOW MODE.",
    "You review decisions. You never make them.",
    "You must NOT change BUY, SELL, STOP, TARGET, or any calculation.",
    "You only receive a Decision Package. No raw market data exists.",
    "Every claim must reference an evidence_id from the package.",
    "Return JSON only. No markdown. No prose outside JSON.",
    "Never invent indicators, prices, statistics, probabilities, or history.",
    "If information is missing, say so explicitly in missing_information.",
)

_SYSTEM = """\
You are the CS Edge AI Advisor operating in Shadow Mode.

Your role is REVIEWER, not trading engine.
The platform makes all decisions. You comment on them.

You receive a Decision Package containing deterministic summaries
from Knowledge, Research, Similarity, Prediction, Feature Intelligence,
Optimization, Statistics, Risk, and Confidence layers.

You must answer:
1. Do you agree with the platform decision?
2. Why or why not?
3. What evidence supports the decision?
4. What evidence contradicts it?
5. What risks exist?
6. What information is missing?
7. What experiment would you run?

Respond with JSON matching the required schema exactly.
"""

_INSTRUCTIONS_V1 = """\
Review the Decision Package below.
Assess agreement with the platform decision.
Ground every statement in evidence_ids from the package.
Flag any unsupported claims as hallucinations.
"""

_INSTRUCTIONS_V2 = """\
Review the Decision Package below with extra scrutiny on risk.
Prioritize contradictions between layers.
Rate your confidence in your own review (0-100).
Suggest one experiment to resolve the biggest uncertainty.
"""

_INSTRUCTIONS_V3 = """\
Review the Decision Package below for multi-layer coherence.
Compare prediction, similarity, and research signals.
Identify the weakest link in the evidence chain.
Propose a concrete experiment with expected outcome.
"""

from .analyst.persona import ANALYST_SYSTEM, ANALYST_INSTRUCTIONS, ANALYST_RULES  # noqa: E402

TEMPLATES: dict[str, PromptTemplate] = {
    "advisor_prompt_v1": PromptTemplate(
        version="advisor_prompt_v1",
        created_at="2026-08-09T00:00:00+00:00",
        description="Initial advisor review prompt — agreement and evidence grounding.",
        rules=_RULES,
        system_prompt=_SYSTEM,
        instructions=_INSTRUCTIONS_V1,
    ),
    "advisor_prompt_v2": PromptTemplate(
        version="advisor_prompt_v2",
        created_at="2026-08-09T00:00:00+00:00",
        description="Risk-focused review with self-confidence rating.",
        rules=_RULES + ("Rate your own review confidence.",),
        system_prompt=_SYSTEM,
        instructions=_INSTRUCTIONS_V2,
    ),
    "advisor_prompt_v3": PromptTemplate(
        version="advisor_prompt_v3",
        created_at="2026-08-09T00:00:00+00:00",
        description="Multi-layer coherence review with experiment proposal.",
        rules=_RULES + ("Identify the weakest evidence link.",),
        system_prompt=_SYSTEM,
        instructions=_INSTRUCTIONS_V3,
    ),
    "advisor_prompt_v4": PromptTemplate(
        version="advisor_prompt_v4",
        created_at="2026-08-13T00:00:00+00:00",
        description="AIA-13 Arabic Senior Market Analyst — advisory outlook + evidence.",
        rules=ANALYST_RULES,
        system_prompt=ANALYST_SYSTEM,
        instructions=ANALYST_INSTRUCTIONS,
    ),
}


class PromptBuilder:
    """Build versioned advisor prompts from Decision Packages."""

    def __init__(self, templates: dict[str, PromptTemplate] | None = None) -> None:
        self._templates = templates or TEMPLATES

    def list_versions(self) -> list[str]:
        return sorted(self._templates.keys())

    def get_template(self, version: str) -> PromptTemplate:
        if version not in self._templates:
            # Graceful fallback when settings point at a missing version
            if version.startswith("advisor_prompt_v") and "advisor_prompt_v4" in self._templates:
                return self._templates["advisor_prompt_v4"]
            raise KeyError(f"Unknown prompt version: {version}")
        return self._templates[version]

    def build(self, package: AdvisorPackage, *,
              version: str = DEFAULT_PROMPT_VERSION,
              context_profile: str = "",
              compact: bool = True) -> AdvisorPrompt:
        """يبني الموجّه.

        ``compact=True`` (الافتراضي) يرسل **سياق المحلّل المضغوط** بدل
        تفريغ الحزمة الكاملة. والحزمة تبقى مرجع المنصّة الداخلي كما هي
        — التغيير في طبقة العرض للنموذج وحدها.

        ``compact=False`` يُبقي السلوك القديم للاختبارات التي تقارن
        الصيغتين، ولتشخيص فرق الجودة بينهما.
        """
        template = self.get_template(version)
        schema = _response_schema_for_package(package, version=version)
        fusion_block = _format_prediction_fusion_instructions(package)

        if compact:
            return self._build_compact(
                package, template=template, version=version,
                context_profile=context_profile, schema=schema,
                fusion_block=fusion_block,
            )

        pkg_json = _format_package(package)
        evidence_count = len(getattr(package, "evidence_index", ()))
        profile_note = ""
        if context_profile:
            profile_note = (
                f"\n## Context Profile\n"
                f"Profile: {context_profile}. Prefer the highest-signal evidence; "
                f"do not invent detail to fill gaps.\n"
            )

        user_prompt = (
            f"{template.instructions}\n\n"
            f"{fusion_block}\n"
            f"{profile_note}\n"
            f"## Unified Decision Package\n"
            f"Package ID: {package.package_id}\n"
            f"Event ID: {package.event_id}\n"
            f"Shadow Mode: {package.shadow_mode}\n\n"
            f"```json\n{pkg_json}\n```\n\n"
            f"## Evidence Index ({evidence_count} items)\n"
            f"{_format_evidence_index(package)}\n\n"
            f"## Required JSON Response Schema\n"
            f"{schema}\n"
        )

        return AdvisorPrompt(
            version=version if version in self._templates else template.version,
            system_prompt=template.system_prompt,
            user_prompt=user_prompt,
            package_id=package.package_id,
            event_id=package.event_id,
            rules=list(template.rules),
            metadata={
                "template_description": template.description,
                "evidence_count": evidence_count,
                "package_type": type(package).__name__,
                "context_profile": context_profile or "",
                "built_at": _now(),
            },
        )


def _build_compact(self, package, *, template, version: str,
                   context_profile: str, schema: str,
                   fusion_block: str) -> AdvisorPrompt:
    """موجّه من سياق المحلّل المضغوط.

    ═══ ترتيب العمليات مقصود ═══

    يُقاس **الغلاف** أولاً (التعليمات، كتلة التنبؤ، مخطّط الجواب،
    موجّه النظام)، ثمّ يُترجَم السياق في ما تبقّى من الميزانية.

    والعكس كان هو العطب: كانت الميزانية تُحسب على الحزمة وحدها، فيدخل
    الغلاف — وهو نحو 40٪ من الموجّه — بلا حساب. فيُعلَن «1414 رمزاً
    داخل ميزانية 1500» بينما المُرسَل 2964.
    """
    from .analyst_context import compile_context, resolve_profile
    from .analyst_context.scaffolding import (
        INSTRUCTIONS_AR, SCHEMA_AR, SYSTEM_AR, prediction_block, quality_block,
    )
    from .analyst_context.tokens import estimate_text_tokens

    prof = resolve_profile(context_profile or "STANDARD")

    pred = dict(getattr(package, "prediction", {}) or {})
    snap = dict(getattr(package, "feature_snapshot", {}) or {})
    try:
        _cov = float(snap.get("coverage")) if snap.get("coverage") is not None else None
    except (TypeError, ValueError):
        _cov = None
    degraded = bool((_cov is not None and _cov < 50.0)
                    or str(snap.get("quality") or "").upper() in ("FAILED", "POOR"))

    blocks = [
        INSTRUCTIONS_AR,
        prediction_block(
            bool(pred.get("available")),
            probability=pred.get("probability_win"),
            model=pred.get("model_id") or pred.get("model") or "",
            calibration=pred.get("calibration"),
        ),
    ]
    qb = quality_block(degraded)
    if qb:
        blocks.append(qb)

    header = "\n\n".join(blocks) + "\n\n## إحاطة السوق\n"
    footer = f"\n\n{SCHEMA_AR}\n"
    overhead = (estimate_text_tokens(header) + estimate_text_tokens(footer)
                + estimate_text_tokens(SYSTEM_AR))

    ctx = compile_context(
        package, profile=prof.name,
        system_prompt="",                 # محسوب ضمن الغلاف
        prompt_overhead_tokens=overhead,
    )

    user_prompt = header + ctx.render() + footer
    total = estimate_text_tokens(user_prompt) + estimate_text_tokens(SYSTEM_AR)

    return AdvisorPrompt(
        version=version if version in self._templates else template.version,
        system_prompt=SYSTEM_AR,
        user_prompt=user_prompt,
        package_id=package.package_id,
        event_id=package.event_id,
        rules=list(template.rules),
        metadata={
            "template_description": template.description,
            "evidence_count": len(ctx.evidence),
            "evidence_before": ctx.metrics.get("evidence_before", 0),
            "package_type": type(package).__name__,
            "context_profile": prof.name,
            "compact": True,
            "context_fingerprint": ctx.fingerprint,
            "analysis_type": ctx.analysis_type,
            "estimated_input_tokens": total,
            "prompt_overhead_tokens": overhead,
            "budget_max": prof.hard_max_tokens,
            "within_budget": total <= prof.hard_max_tokens,
            "context_metrics": dict(ctx.metrics),
            "built_at": _now(),
        },
    )


PromptBuilder._build_compact = _build_compact


_RESPONSE_SCHEMA = """\
{
  "agreement": "agree" | "disagree" | "partial",
  "confidence": 0-100,
  "summary": "one sentence",
  "reasoning": "why you agree or disagree",
  "prediction_assessment": "supported" | "contradicted" | "mixed" | "unavailable",
  "supporting_evidence": [{"evidence_id": "...", "section": "...", "field": "...", "note": "..."}],
  "contradicting_evidence": [{"evidence_id": "...", "section": "...", "field": "...", "note": "..."}],
  "risks": ["..."],
  "missing_information": ["..."],
  "suggested_experiment": {"hypothesis": "...", "method": "...", "expected_outcome": "..."},
  "shadow_mode_acknowledged": true
}"""

_RESPONSE_SCHEMA_V4 = """\
{
  "language": "ar",
  "agreement": "agree" | "disagree" | "partial",
  "confidence": 0-100,
  "summary": "خلاصة عربية موجزة",
  "reasoning": "تفسير عربي مهني مبني على evidence_id فقط",
  "prediction_assessment": "supported" | "contradicted" | "mixed" | "unavailable",
  "supporting_evidence": [{"evidence_id": "...", "section": "...", "field": "...", "note": "..."}],
  "contradicting_evidence": [{"evidence_id": "...", "section": "...", "field": "...", "note": "..."}],
  "risks": ["..."],
  "missing_information": ["..."],
  "suggested_experiment": {"hypothesis": "...", "method": "...", "expected_outcome": "..."},
  "shadow_mode_acknowledged": true,
  "recommendation": {"action": "buy|sell|wait|watch|avoid", "confidence": 0-100},
  "current_market_view": {"direction": "bullish|bearish|sideways|unclear", "confidence": 0-100},
  "near_term_outlook": {"horizon_days": 7, "direction": "bullish|bearish|sideways|unclear", "confidence": 0-100},
  "positive_signals": ["..."],
  "negative_signals": ["..."],
  "what_to_watch": ["..."],
  "invalidation_conditions": ["..."],
  "actionable_advice": "ماذا أفعل الآن؟",
  "data_quality_note": "ملاحظة جودة البيانات إن وُجدت",
  "statistical_prediction": {"available": false, "probability_win": null, "model": null},
  "advisor_assessment": {"agreement": "agree|partial|disagree", "confidence": 0-100},
  "scenarios": {
    "bullish": "السيناريو الصاعد — أدلة فقط من الحزمة",
    "base": "السيناريو الأساسي الأكثر ترجيحًا",
    "bearish": "السيناريو الهابط / إبطال الصعود"
  }
}"""


def _format_prediction_fusion_instructions(package: AdvisorPackage) -> str:
    pred = getattr(package, "prediction", None) or {}
    if not pred or not pred.get("available"):
        return (
            "## Statistical Prediction Layer\n"
            "Prediction is UNAVAILABLE (no ACTIVE model passed quality gates).\n"
            "Evaluate platform decision using other evidence layers only.\n"
            "Set prediction_assessment to \"unavailable\".\n"
            "Set statistical_prediction.available=false.\n"
            "Do NOT invent probabilities.\n"
            "In Arabic summary say: التنبؤ الإحصائي غير متاح حاليًا لعدم وجود نموذج اجتاز بوابة الجودة."
        )
    pw = pred.get("probability_win")
    pct = f"{float(pw) * 100:.1f}%" if pw is not None else "unknown"
    label = pred.get("prediction", "WIN/LOSS")
    model = pred.get("model_id") or pred.get("model") or "LightGBM"
    return (
        "## Statistical Prediction Layer (LightGBM — read-only)\n"
        f"Model: {model}\n"
        f"The ACTIVE statistical model estimates: {label} with {pct} win probability.\n"
        "Evaluate whether available evidence supports, contradicts, or is insufficient "
        "to validate this statistical prediction.\n"
        "Do NOT invent probabilities.\n"
        "Do NOT modify the statistical probability.\n"
        "Do NOT treat your confidence score as statistical probability.\n"
        "Your confidence is LLM review confidence only.\n"
        f"Set statistical_prediction.available=true, probability_win={pw}, model=\"{model}\"."
    )


def _response_schema_for_package(package: AdvisorPackage, *, version: str = "") -> str:
    if version == "advisor_prompt_v4" or (version or "").endswith("v4"):
        return _RESPONSE_SCHEMA_V4
    return _RESPONSE_SCHEMA


def _format_package(package: AdvisorPackage) -> str:
    import json
    return json.dumps(package.to_dict(), indent=2, default=str)


def _format_evidence_index(package: AdvisorPackage) -> str:
    lines = []
    for ref in package.evidence_index:
        layer = getattr(ref, "source_layer", "") or ""
        prefix = f"[{layer}] " if layer else ""
        lines.append(
            f"- {ref.evidence_id}: {prefix}[{ref.section}.{ref.field}] "
            f"{ref.label} = {ref.value!r}"
        )
    return "\n".join(lines) if lines else "(no indexed evidence)"
