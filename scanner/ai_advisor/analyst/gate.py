# -*- coding: utf-8 -*-
"""بوّابة الاحتمال الإحصائي — الحقيقة من المنصّة لا من ادّعاء النموذج.

═══ لماذا هذه الوحدة موجودة ═══

الموجّه يقول للنموذج صراحةً: «لا تخترع احتمالات»، و«اضبط
``statistical_prediction.available=false``». وهذا **تعليم** لا
**إلزام**. والفرق بينهما هو الفرق بين لافتة «ممنوع الدخول» وبين باب
مقفل.

ونموذج لغويّ يُسأل عن سوق سيميل إلى ملء الفراغ برقم يبدو معقولاً —
«احتمال النجاح 68%» — لأن هذا شكل الجواب الذي رآه في تدريبه. فإن مرّ
هذا الرقم إلى الواجهة صار له في عين القارئ وزن رقم مقيس، وهو ليس كذلك:
لا نموذج وراءه، ولا معايرة، ولا اختبار خارج العيّنة.

وضرر هذا أكبر من ضرر غياب الرقم. الغياب يُبقي القارئ على حذره؛ أما
الرقم المخترَع فينقله من الحذر إلى ثقة لا سند لها — وهي الحالة التي
تُفتح فيها الصفقات الكبيرة.

فهنا يُقفل الباب: ما تقوله المنصّة عن نموذجها هو الحقيقة، وما يقوله
النموذج اللغوي عن نفسه يُقارَن بها ويُسجَّل حين يخالف.

═══ ما تفعله البوّابة ═══

    المنصّة: لا نموذج نشط  →  يُمحى أي احتمال ادّعاه النموذج
    المنصّة: نموذج نشط     →  يُفرَض احتمال المنصّة، ويُلغى تعديل النموذج له

وفي الحالتين تُعاد قائمة المخالفات لتدخل في درجة الهلوسة، فالمخالفة
تُقاس ولا تُبتلع صامتة.
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["gate_prediction", "scan_text_for_invented_probability"]

# نسبة مئوية في نصّ حرّ: «68%» أو «68.5 %» أو «٪68».
_PCT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*[%٪]|[%٪]\s*(\d{1,3}(?:[.,]\d+)?)")

# عبارات تربط الرقم باحتمال نجاح — لا بأيّ نسبة أخرى.
#
# التمييز ضروري: «ارتفع الحجم 40%» ليس ادّعاء احتمال، وحجبه يفقر
# التحليل بلا سبب. فالبحث عن قرينة الاحتمال لا عن الرمز ٪ وحده.
_PROB_CUES = (
    "احتمال", "احتمالية", "فرصة النجاح", "نسبة النجاح", "توقع النجاح",
    "probability", "win rate", "chance of", "likelihood", "odds",
)

# فرق يُتسامح معه بين ما قالته المنصّة وما ردّده النموذج: تقريب العرض
# (0.68 مقابل 68.0%) ليس تحريفاً.
_PROB_TOLERANCE = 0.005


def _as_prob(val: Any) -> float | None:
    """يحوّل إلى احتمال في [0,1]، ويقبل الصيغة المئوية."""
    try:
        p = float(val)
    except (TypeError, ValueError):
        return None
    if p != p:  # NaN
        return None
    if 1.0 < p <= 100.0:
        p /= 100.0
    if not (0.0 <= p <= 1.0):
        return None
    return p


def scan_text_for_invented_probability(text: str) -> list[str]:
    """يلتقط نسبة مئوية مقترنة بقرينة احتمال في نصّ حرّ.

    يُستدعى فقط حين تكون المنصّة بلا نموذج نشط؛ فحينها أي احتمال في
    النصّ مخترَع بالضرورة، إذ لا مصدر له.
    """
    if not text:
        return []
    low = str(text).lower()
    if not any(cue in low for cue in _PROB_CUES):
        return []
    hits: list[str] = []
    for m in _PCT.finditer(str(text)):
        hits.append((m.group(1) or m.group(2) or "").strip())
    return [h for h in hits if h]


def gate_prediction(
    parsed: dict[str, Any] | None,
    platform_prediction: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """يفرض حقيقة المنصّة على حقل ``statistical_prediction``.

    Parameters
    ----------
    parsed:
        استجابة النموذج بعد التطبيع.
    platform_prediction:
        ``package.prediction`` — ما تعرفه المنصّة عن نموذجها الإحصائي.
        غيابه أو ``available=False`` يعني: لا نموذج اجتاز بوابة الجودة.

    Returns
    -------
    (out, violations)
        نسخة مصحَّحة، وقائمة مخالفات بالعربية تدخل في درجة الهلوسة.
    """
    out = dict(parsed or {})
    platform = dict(platform_prediction or {})
    violations: list[str] = []

    claimed = out.get("statistical_prediction")
    if not isinstance(claimed, dict):
        claimed = {}

    platform_active = bool(platform.get("available"))
    platform_prob = _as_prob(platform.get("probability_win"))
    platform_model = platform.get("model_id") or platform.get("model")

    if not platform_active:
        # لا نموذج نشط: كل ما يقوله النموذج عن التنبؤ يُمحى.
        if claimed.get("available"):
            violations.append(
                "ادّعى المستشار توفّر تنبؤ إحصائي بينما لا نموذج نشط في المنصّة."
            )
        stray = _as_prob(claimed.get("probability_win"))
        if stray is not None:
            violations.append(
                f"اختلق المستشار احتمال نجاح ({stray:.0%}) بلا نموذج يسنده."
            )
        # النصّ الحرّ كذلك — الحقل قد يُمحى بينما يبقى الرقم في الخلاصة
        for field in ("summary", "reasoning", "actionable_advice"):
            for hit in scan_text_for_invented_probability(out.get(field, "")):
                violations.append(
                    f"احتمال مخترَع في «{field}»: {hit}% — لا نموذج نشط."
                )
        out["statistical_prediction"] = {
            "available": False,
            "probability_win": None,
            "model": None,
            "calibration": None,
            "oos": None,
            "baseline": None,
        }
        out["prediction_assessment"] = "unavailable"
        return out, violations

    # نموذج نشط: الرقم رقم المنصّة، وأيّ تعديل من النموذج يُلغى ويُسجَّل.
    claimed_prob = _as_prob(claimed.get("probability_win"))
    if platform_prob is not None and claimed_prob is not None:
        if abs(claimed_prob - platform_prob) > _PROB_TOLERANCE:
            violations.append(
                f"عدّل المستشار احتمال النموذج من {platform_prob:.1%} "
                f"إلى {claimed_prob:.1%} — أُعيد إلى قيمة المنصّة."
            )
    elif platform_prob is not None and claimed_prob is None and claimed.get("available"):
        violations.append("أسقط المستشار احتمال النموذج النشط — أُعيد من المنصّة.")

    out["statistical_prediction"] = {
        "available": True,
        "probability_win": platform_prob,
        "model": platform_model or claimed.get("model") or "LightGBM",
        # المعايرة وخارج‑العيّنة وخطّ الأساس من المنصّة حصراً: هذه
        # أرقام قياس، ولا يملك النموذج اللغوي سبيلاً إلى معرفتها.
        "calibration": platform.get("calibration"),
        "oos": platform.get("oos"),
        "baseline": platform.get("baseline"),
    }
    return out, violations
