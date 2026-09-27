# -*- coding: utf-8 -*-
"""تشريح الصفقات المحسومة — لماذا ربحت ولماذا خسرت.

المبدأ: **المنصّة تقيس، والنموذج يفسّر ما ثبت.**

    صفقات محسومة
        ↓
    separation.analyze     ← فروق مقيسة + فواصل + تصحيح المقارنات
        ↓
    narrative.build_prompt ← النموذج يرى الجدول لا الصفقات
        ↓
    آليات مقترحة + تجارب تفصل بينها

العكس — أن يرى النموذج صفقة بنتيجتها ويُسأل «لماذا» — يُنتج تفسيراً
بليغاً لنمطٍ قد لا يكون موجوداً، وهو أسوأ من الصمت.
"""
from __future__ import annotations

# ═══ ثلاثة فحوص لا واحد ═══
#
#     anatomy.py     ما جرى لهذه الصفقة ميكانيكياً — أين الخلل؟
#     single.py      هل كان القرار سليماً؟ — والنتيجة محجوبة
#     separation.py  ما يفصل الرابح عن الخاسر في المجموعة
#
# والأوّل أُضيف أخيراً لأنّ بين الاثنين فجوة: «خسرت» تجمع صفقةً
# بلغت ‎+2.3R‎ ثمّ انعكست وصفقةً لم تتحرّك قطّ — وهما عطبان
# مختلفان، ونتيجتهما في الجدول واحدة.

from .anatomy import KIND_LABELS, anatomy, classify, stop_context
from .narrative import SYSTEM_AR, build_prompt, render_report
from .single import (
    OUTCOME_KEYS, TradeCard, build_card, build_single_prompt, render_card,
    verdict_vs_outcome,
)
from .separation import (
    ENTRY_FIELDS, OUTCOME_FIELDS, FactorSeparation, PostmortemReport,
    TagSeparation, analyze, extract_tags, wilson_interval,
)

__all__ = [
    "KIND_LABELS", "anatomy", "classify", "stop_context",
    "ENTRY_FIELDS", "OUTCOME_FIELDS", "FactorSeparation", "PostmortemReport",
    "SYSTEM_AR", "TagSeparation", "analyze", "build_prompt", "extract_tags",
    "render_report", "wilson_interval",
    "OUTCOME_KEYS", "TradeCard", "build_card", "build_single_prompt",
    "render_card", "verdict_vs_outcome",
]
