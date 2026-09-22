# -*- coding: utf-8 -*-
"""ازدحام التموضع — عائلةُ شاهدٍ جديدة، وحارسُ مخاطر لا إشارةُ دخول.

═══ السؤال الذي تجيب عنه ═══

المنصّة كلّها تقيس **السعر**: اتجاهه وزخمه وحجمه وانضغاطه. وهذه
كلّها مشتقّةٌ من سلسلةٍ واحدة. فمهما كثرت المؤشّرات، تبقى شاهداً
واحداً بأسماءٍ كثيرة — وهي المادّة ١٧ نفسها.

والتموضع شاهدٌ من مصدرٍ آخر: من يحمل المراكز، وبأيّ رافعة، وكم
يدفع ثمنَ حملها. وهو لا يُشتقّ من الشموع، فلا يُعدّ تكراراً لها.

═══ وما تقوله وما لا تقوله ═══

لا تتنبّأ بالاتجاه. كلّ ما تقوله:

    «هذا الارتفاع مدفوعٌ برافعةٍ مكلفة»   → هشّ
    «هذا الارتفاع مدفوعٌ بشراءٍ فوريّ»     → أمتن

والفرق آليّ لا إحصائيّ: المراكز المدينة تُصفّى قسراً عند الهبوط،
فيتضاعف الهبوط الصغير. وهذا هو المسار السببيّ الوحيد المدّعى هنا.

═══ ولماذا لا تدخل الدرجة ═══

لأنّها لم تُقَس بعد على هذه المنصّة. والقاعدة التي بُنيت عليها
كل إضافةٍ سابقة واحدة: **يُعرَض ثمّ يُقاس ثمّ يُوزَن** — لا
يدخل شيء التسجيل بحجّة أنّه معقول. و``tools_btc_measure.py``
هو ما يقرّر.

═══ والمئين لا العتبة المطلقة ═══

«تمويل فوق 0.05٪» عتبةٌ كُتبت في سوق ٢٠٢١ ولا تصلح لكل نظام.
والمئين يقارن الحالة بتاريخ الرمز نفسه، فيبقى معناه واحداً حين
يتغيّر النظام.
"""
from __future__ import annotations

import time

__all__ = ["read", "STATES", "STATE_LABELS"]

# حالات الازدحام — مرتّبةٌ من الأسوأ للشراء إلى الأفضل
STATES = ("crowded_long", "heating", "neutral", "reset", "unknown")

STATE_LABELS = {
    "crowded_long": "ازدحام شرائي — رافعة مكلفة",
    "heating": "رافعة تتراكم",
    "neutral": "تموضع طبيعي",
    "reset": "تصفية حديثة — الرافعة خفّت",
    "unknown": "غير متاح",
}

#: مئينات القرار. والعتبات هنا على **المئين** لا على المعدّل نفسه.
HOT_PCTILE = 85.0
COLD_PCTILE = 15.0
#: تغيّر المراكز المفتوحة الذي يُسمّى «تراكماً» — ٪ خلال يوم
OI_RISE_PCT = 5.0
OI_DROP_PCT = -5.0

#: أقلّ سجلٍّ يُبنى عليه مئين. وأقلّ منه يعطي رقماً يبدو دقيقاً
#: وهو ترتيبُ عشر قيم.
MIN_FUNDING_SAMPLES = 90       # ثلاثون يوماً × ثلاث دفعات


def _pctile(values: list[float], x: float) -> float | None:
    """موضع ``x`` بين القيم — ٪. و``None`` إن قلّت العيّنة."""
    vals = [v for v in values if v == v]
    if len(vals) < MIN_FUNDING_SAMPLES:
        return None
    below = sum(1 for v in vals if v < x)
    same = sum(1 for v in vals if v == x)
    return round((below + same / 2.0) / len(vals) * 100.0, 1)


def _pct_change(series: list[float], back: int) -> float | None:
    if len(series) <= back:
        return None
    old, new = series[-1 - back], series[-1]
    if not old:
        return None
    return round((new - old) / abs(old) * 100.0, 2)


def read(symbol: str = "BTCUSDT", *, period: str = "4h") -> dict:
    """قراءةُ تموضعٍ كاملة — أو ``ok=False`` مع سببٍ مكتوب.

    ولا ترمي أبداً: التموضع إضافةٌ وصفية، وسقوط صفحة الرمز
    بسببها خسارةٌ صافية.
    """
    try:
        from scanner.adapters import binance_futures as bf
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "why": f"تعذّر التحميل: {str(exc)[:60]}",
                "state": "unknown"}

    try:
        fund = bf.funding_history(symbol)
        oi = bf.open_interest_history(symbol, period=period)
        prem = bf.premium_index(symbol)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "why": f"تعذّر الجلب: {str(exc)[:60]}",
                "state": "unknown"}

    if not fund:
        return {"ok": False, "why": "لا سجلّ تمويل لهذا الرمز "
                                    "(قد لا يكون له عقد دائم)",
                "state": "unknown"}

    rates = [f["rate"] for f in fund]
    now_rate = rates[-1]
    # ═══ السنويّ يُقرأ ولا يُقارَن ═══
    #
    # ‏0.01٪ كل ثماني ساعات تبدو صفراً — وهي ١١٪ سنوياً. والعرض
    # بالصيغتين معاً يمنع الاستهانة بالصغير.
    annual = now_rate * bf.FUNDINGS_PER_DAY * 365 * 100.0

    pct = _pctile(rates, now_rate)
    avg_3d = (sum(rates[-9:]) / len(rates[-9:])) if len(rates) >= 9 else None

    oi_series = [x["oi"] for x in oi]
    per_day = max(1, int(24 / _hours(period)))
    oi_1d = _pct_change(oi_series, per_day)
    oi_7d = _pct_change(oi_series, per_day * 7)

    state, why = _classify(pct, oi_1d)

    return {
        "ok": True,
        "symbol": symbol,
        "state": state,
        "label": STATE_LABELS[state],
        "why": why,
        # التمويل
        "funding": round(now_rate * 100.0, 4),          # ٪ لكل دفعة
        "funding_annual_pct": round(annual, 1),
        "funding_pctile": pct,
        "funding_avg_3d": None if avg_3d is None else round(avg_3d * 100, 4),
        "funding_samples": len(rates),
        "estimated_next": None if not prem else round(
            prem.get("estimated_rate", 0.0) * 100.0, 4),
        # المراكز المفتوحة
        "oi": oi_series[-1] if oi_series else None,
        "oi_change_1d": oi_1d,
        "oi_change_7d": oi_7d,
        "oi_points": len(oi_series),
        "oi_window_days": bf.OI_HISTORY_DAYS,
        # ═══ وحدُّ البيانات يُعلَن مع البيانات ═══
        #
        # ثلاثون يوماً لا تكفي لمئينٍ على المراكز المفتوحة. وعرضُ
        # النسبة بلا هذا القيد يوحي بسياقٍ تاريخيّ لا وجود له.
        "oi_note": f"سجلّ المراكز المفتوحة {bf.OI_HISTORY_DAYS} يوماً "
                   "فقط — حدُّ المنصّة، فلا مئين له",
        "generated_at": int(time.time()),
        # ولا تدخل الدرجة: تُعرَض وتُقاس ثمّ يُنظر
        "scored": False,
    }


def _hours(period: str) -> float:
    try:
        n = float(period[:-1])
    except (TypeError, ValueError):
        return 4.0
    unit = period[-1:].lower()
    return n if unit == "h" else n * 24 if unit == "d" else n / 60.0


def _classify(pct: float | None, oi_1d: float | None) -> tuple[str, str]:
    """الحالة من المئين وتغيّر المراكز — وسببها نصّاً.

    ═══ والغائب لا يُصنَّف ═══

    مئينٌ غائب لقلّة العيّنة يعني «لا أعرف» لا «طبيعي». وعدُّه
    طبيعياً يعطي طمأنينةً لم تُقَس.
    """
    if pct is None:
        return "unknown", "عيّنة التمويل أقصر من أن تُعطي مئيناً"

    rising = oi_1d is not None and oi_1d >= OI_RISE_PCT
    falling = oi_1d is not None and oi_1d <= OI_DROP_PCT

    if pct >= HOT_PCTILE and rising:
        return "crowded_long", (
            f"التمويل في المئين {pct:g} من تاريخه، والمراكز المفتوحة "
            f"{oi_1d:+g}٪ خلال يوم — مراكز شراء مدينة تتراكم. "
            "الهبوط هنا يُصفّيها قسراً فيتضاعف.")
    if pct >= HOT_PCTILE:
        return "heating", (
            f"التمويل في المئين {pct:g} — الشراء يدفع ثمناً مرتفعاً، "
            "لكنّ المراكز المفتوحة لا تتراكم بعد.")
    if pct <= COLD_PCTILE and falling:
        return "reset", (
            f"التمويل في المئين {pct:g} والمراكز المفتوحة {oi_1d:+g}٪ — "
            "تصفيةٌ جرت والرافعة خفّت. أمتن ما يكون التموضع.")
    if pct <= COLD_PCTILE:
        return "reset", (
            f"التمويل في المئين {pct:g} — الشراء لا يدفع علاوة، "
            "وقد يدفع له.")
    return "neutral", f"التمويل في المئين {pct:g} — لا ازدحام في أيّ طرف."
