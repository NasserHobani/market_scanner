# -*- coding: utf-8 -*-
"""غلاف الموجّه المضغوط — التعليمات والمخطّط.

═══ لماذا كان لا بدّ من ضغط الغلاف أيضاً ═══

بعد ضغط بيانات الحزمة، بقي **الغلاف الثابت** 1079 رمزاً:

    موجّه النظام      280
    تعليمات القالب    281
    كتلة التنبؤ       103
    مخطّط الجواب      415
    ─────────────────────
                     1079

وميزانية ‏FAST هدفها 1200. أي أن الإحاطة السوقية — وهي **الغرض** —
كانت تحصل على 121 رمزاً. فلا معنى لضغط البيانات وحدها: الحدّ يُخرق من
الحشو الثابت الذي يُدفع ثمنه في كل مراجعة، وهي عشرات المرّات في المسح.

═══ ما ضُغط وكيف ═══

**المخطّط** كان يعدّد كل قيمة ممكنة لكل حقل مع أمثلة. والنموذج لا
يحتاج شرح ``"bullish"``؛ يحتاج أسماء الحقول وقيمها المسموحة. فاختُصر
إلى سطر واحد لكل حقل.

**التعليمات وموجّه النظام** كانا يتقاطعان: كلاهما يقول «أنت محلّل
أسواق يكتب بالعربية». فوُحّدا.

**كتلة التنبؤ** في حالة الغياب كانت ثماني أسطر تقول شيئاً واحداً.

والعقد مع المدقّق محفوظ: الحقول العشرة الإلزامية
(``REQUIRED_FIELDS``) كلّها مذكورة صراحةً، فلا يتغيّر شيء في التحقّق
ولا في التقييم.
"""
from __future__ import annotations

__all__ = ["SYSTEM_AR", "INSTRUCTIONS_AR", "SCHEMA_AR",
           "prediction_block", "quality_block"]

# ‏280 رمزاً ← ~120. ما حُذف: تكرار «لا تنفّذ صفقات» ثلاث مرّات،
# وشرح ما هو التحليل الفنّي.
SYSTEM_AR = """\
أنت محلّل أسواق مالية أوّل في منصّة CS Edge. تكتب بالعربية المهنية.
تحلّل ما يصلك من حقائق مقيسة ولا تخترع ما لم يصلك؛ الغائب تقوله غائباً.
رأيك استشاري: لا تنفّذ صفقة ولا تعدّل وقفاً ولا هدفاً ولا استراتيجية.
تتجنّب اليقين الزائف — تقول «أرجّح» و«السيناريو الأكثر ترجيحاً».
تُخرج JSON صالحاً فقط، بلا نصّ قبله أو بعده."""

# ‏281 ← ~90
INSTRUCTIONS_AR = """\
حلّل الإحاطة أدناه. إن كان نوع الطلب «تحليل سوق» فلا توافق قراراً ولا
تخالفه — صف الوضع الراهن. وإن كان مراجعة قرار فقيّمه بالأدلّة.
استشهد بمعرّفات الأدلّة كما وردت ([ev_00x]) ولا تخترع معرّفاً."""

# ‏415 ← ~170. كل حقل إلزامي مذكور؛ القيم المسموحة بلا شرح.
SCHEMA_AR = """\
أعِد JSON بهذه الحقول حصراً:
agreement: agree|disagree|partial|insufficient
confidence: 0-100 (ثقتك أنت، لا احتمالاً إحصائياً)
summary: جملة عربية واحدة
reasoning: فقرة عربية
recommendation: {action: buy|sell|wait|watch|avoid|insufficient, confidence: 0-100}
current_market_view: {direction: bullish|bearish|sideways|unclear, confidence: 0-100}
near_term_outlook: {horizon_days: 3-7, direction: كما أعلاه, confidence: 0-100}
supporting_evidence: [نصوص عربية مع [ev_id]]
contradicting_evidence: [مثلها]
risks: [] · what_to_watch: [] · invalidation_conditions: []
missing_information: []
suggested_experiment: {hypothesis, method, expected_outcome}
shadow_mode_acknowledged: true"""


def prediction_block(available: bool, *, probability=None, model: str = "",
                     calibration=None) -> str:
    """كتلة التنبؤ — سطران بدل ثمانية عند الغياب."""
    if not available:
        return ("التنبؤ الإحصائي: غير متاح (لا نموذج اجتاز بوابة الجودة). "
                "لا تذكر احتمالاً رقمياً ولا تشتقّه؛ "
                "اضبط statistical_prediction.available=false.")
    bits = [f"نموذج {model or 'LightGBM'}"]
    if probability is not None:
        bits.append(f"احتمال النجاح {float(probability) * 100:.1f}%")
    if calibration:
        bits.append(f"المعايرة {calibration}")
    return ("التنبؤ الإحصائي: " + " · ".join(bits)
            + ". قيّمه كدليل ولا تعدّل الرقم؛ ثقتك شيء وهذا الاحتمال شيء آخر.")


def quality_block(degraded: bool) -> str:
    """تعليمة الجودة المنخفضة — تُضاف فقط حين تنطبق.

    تُفصَل عن السياق عمداً: هذه **تعليمة سلوك** لا حقيقة سوق، ومكانها
    مع التعليمات لا مع البيانات.
    """
    if not degraded:
        return ""
    return ("تنبيه: تغطية البيانات منخفضة. إن لم تكفِ الأدلّة لحكم "
            "موثوق فاختر agreement=insufficient و action=insufficient "
            "بدل الترجيح — الاعتراف بعدم الكفاية أصدق من رأي بلا سند.")
