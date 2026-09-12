# -*- coding: utf-8 -*-
"""طبقات الميزات — فشلُ الالتقاط شيءٌ وغيابُ المعنى شيءٌ آخر.

═══ العطب المقيس ═══

كان مقياس الجودة واحداً: نسبة الميزات الحاضرة من ستّ وثلاثين.
و«جيّدة» تحتاج ‎0.90‎، و«مؤهّلة للتدريب» تحتاج ‎0.70‎.

فقِيست ٣٣٣٣ لقطة حقيقية::

    أعلى تغطية بلغتها لقطةٌ واحدة    0.861
    لقطات «جيّدة»                        0
    لقطات تغطيتها 50–60٪              1751   ← تحت حدّ الأهلية

أعلى تغطية ‎0.861‎ لأنّ **خمس ميزات لا تُحسب أبداً**::

    historical_expectancy · regime · research_signal
    research_confidence   · research_sample_size

فحدّ ‎0.90‎ كان غير قابل للبلوغ بنيوياً — لا لعطبٍ في الالتقاط بل
لأنّ المقام يحوي ما لا وجود له.

والرقم ‎0.556‎ الذي تكرّر ١٧٥١ مرّة ليس صدفة: ‎20/36‎ بالضبط — أي
الميزات الأساسية وحدها، بلا إثراء (تشابه · معرفة · بحث) وبلا
توصية.

═══ والتصنيف ═══

الغياب نوعان، وخلطُهما هو العطب:

**فشل التقاط** — ميزةٌ تُحسب من السعر والحجم وحدهما، فغيابها خلل
حقيقي: تعذّر جلب شموع، أو انهار الحساب. هذه تُقاس وتُحاسَب.

**غير منطبق** — «معدّل فوز الصفقات المشابهة» يغيب لأنّه **لا توجد
صفقات مشابهة بعد**. وهذا ليس خللاً بل حقيقةٌ عن السوق، وهي نفسها
معلومة: إشارةٌ بلا سابقة تختلف عن إشارةٍ لها عشرون سابقة.

فالأولى تُحاسَب في الأهلية، والثانية تُسجَّل ``None`` ويتعلّم منها
النموذج. و‎LightGBM‎ يعالج القيم الغائبة أصلاً — لا يحتاج ملأها.

═══ ولماذا القائمة مقيسة لا مُخمَّنة ═══

الطبقات أدناه من قياس الحضور الفعلي على ٣٣٣٣ لقطة، لا من الحدس.
والنسبة بجانب كل ميزة هي حضورها المقيس يوم التصنيف.
"""
from __future__ import annotations

# ═══ الأساسية — تُحسب من السعر والحجم والبنية وحدها ═══
#
# حضورها المقيس ٨٩–١٠٠٪. وما نقص منها فهو فشل التقاط حقيقي.
CORE_FEATURES: tuple[str, ...] = (
    # اتجاه وزخم — 100٪
    "trend_direction",
    "trend_strength",
    "higher_timeframe_trend",
    "multi_timeframe_alignment",
    "rsi",
    "momentum_state",
    "divergence",
    "momentum_strength",
    # تقلّب وحجم — 100٪ عدا المذكور
    "atr_pct",
    "atr_percentile",          # 89٪
    "rvol",
    "volume_participation",    # 89٪
    "volume_trend",
    # نتيجة المنصّة والتوصية — 100٪
    "score",
    "confidence",
    "grade_enc",
    "side_buy",
    "knowledge_confidence",    # 89٪
)

# ═══ الاختيارية — غيابها معلومة لا خلل ═══
OPTIONAL_FEATURES: dict[str, str] = {
    # بنيةٌ قد لا توجد: لا كلّ شمعةٍ لها كسر بنية أو مستوى دعم
    "bos_count": "no_structure_event",            # 47٪
    "choch_count": "no_structure_event",          # 36٪
    "structure_direction": "no_structure_event",  # 31٪
    "support_distance": "no_level_found",         # 32٪
    "resistance_distance": "no_level_found",      # 25٪
    "volatility_regime": "regime_undetermined",   # 41٪

    # تشابه: تغيب حين لا سابقة — وهذا خبرٌ بذاته
    "match_count": "no_similar_trades",           # 47٪
    "similarity_score": "no_similar_trades",      # 47٪
    "historical_win_rate": "no_similar_trades",   # 36٪
    "historical_expectancy": "no_similar_trades",  # 0٪ — انظر أدناه

    # معرفة
    "knowledge_score": "knowledge_unavailable",   # 47٪
    "detected_pattern_count": "knowledge_unavailable",  # 47٪
    "regime": "knowledge_unavailable",            # 0٪

    # بحث: يحتاج تجربةً مكتملة مصادقاً عليها، ولا تجربة بعد
    "research_signal": "no_validated_research",   # 0٪
    "research_confidence": "no_validated_research",  # 0٪
    "research_sample_size": "no_validated_research",  # 0٪

    # عائد/مخاطرة: للتوصيات القابلة للتنفيذ وحدها
    "risk_reward": "no_actionable_reco",          # 22٪
    "expected_r": "no_actionable_reco",           # 22٪
}

# ═══ الصفر الدائم — يُرصد ولا يُدفَن ═══
#
# خمس ميزات لم تظهر ولا مرّة في ٣٣٣٣ لقطة. وجعلُها اختيارية يرفع
# السقف من ‎0.861‎ إلى ‎1.0‎، لكنّه **لا يصلح مصدرها**:
#
#   historical_expectancy  ← ``avg_r`` في حمولة التشابه يكون
#                            ‎None‎ حين لا يحمل أيّ تطابقٍ
#                            ‎r_multiple‎. وأخواتها تحضر ٣٦–٤٧٪.
#   regime                 ← يحتاج ``market_environment.regime``
#                            من طبقة المعرفة.
#   research_*             ← يحتاج تجربةً مكتملة في مخزن التجارب،
#                            وهو فارغ.
#
# فتُدرَج هنا كي يُنبَّه عليها في الفحص: اختياريّةٌ تبقى صفراً إلى
# الأبد ميزةٌ ميّتة، والعقد يجب أن يعرف الفرق.
KNOWN_DEAD: tuple[str, ...] = (
    "historical_expectancy",
    "regime",
    "research_signal",
    "research_confidence",
    "research_sample_size",
)

# حدّ الأهلية على الأساسية — ‎17‎ من ‎18‎
CORE_MIN_COVERAGE = 0.90


def core_coverage(features: dict) -> float:
    """نسبة الأساسية الحاضرة — وهي وحدها ما يُحاسَب في الأهلية."""
    if not CORE_FEATURES:
        return 0.0
    have = sum(1 for f in CORE_FEATURES if f in (features or {}))
    return round(have / len(CORE_FEATURES), 4)


def missing_core(features: dict) -> list[str]:
    """الأساسية الغائبة — قائمة الأعطاب الحقيقية."""
    return [f for f in CORE_FEATURES if f not in (features or {})]


def optional_gaps(features: dict) -> dict[str, str]:
    """الاختيارية الغائبة وسببُ غيابها — تُحفظ ولا تُسكَت."""
    return {f: why for f, why in OPTIONAL_FEATURES.items()
            if f not in (features or {})}


def is_eligible(features: dict) -> bool:
    return core_coverage(features) >= CORE_MIN_COVERAGE


__all__ = ["CORE_FEATURES", "OPTIONAL_FEATURES", "KNOWN_DEAD",
           "CORE_MIN_COVERAGE", "core_coverage", "missing_core",
           "optional_gaps", "is_eligible"]
