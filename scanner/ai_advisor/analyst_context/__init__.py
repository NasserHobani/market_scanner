# -*- coding: utf-8 -*-
"""‏AIA-13.1 — سياق المحلّل المضغوط.

المبدأ: **لا تُرسل بيانات أكثر، أرسل البيانات الصحيحة.**

    UnifiedDecisionPackage   ← مرجع المنصّة الكامل (تتبّع، تدقيق، حفظ)
            ↓
    AnalystContextCompiler   ← ينتقي ما يغيّر حكم محلّل
            ↓
    CompactAnalystContext    ← إحاطة عربية مضغوطة
            ↓
    PromptBuilder → Qwen / Claude
"""
from __future__ import annotations

from .analyst_context import (
    ANALYST_CONTEXT_VERSION, CompactAnalystContext, EvidenceItem,
)
from .analyst_metrics import RequestMetrics, Stopwatch
from .compiler import COMPILER_VERSION, ContextTooLarge, compile_context
from .context_fingerprint import context_fingerprint, package_context_key
from .context_profiles import PROFILES, Profile, resolve_profile
from .evidence_selector import select_evidence
from .tokens import estimate_prompt_tokens, estimate_text_tokens

__all__ = [
    "ANALYST_CONTEXT_VERSION",
    "COMPILER_VERSION",
    "CompactAnalystContext",
    "ContextTooLarge",
    "EvidenceItem",
    "PROFILES",
    "Profile",
    "RequestMetrics",
    "Stopwatch",
    "compile_context",
    "context_fingerprint",
    "estimate_prompt_tokens",
    "estimate_text_tokens",
    "package_context_key",
    "resolve_profile",
    "select_evidence",
]
