# -*- coding: utf-8 -*-
"""مؤشّرات الزخم — ‏Stochastic RSI.

═══ ما هو، وما ليس هو ═══

‏Stochastic RSI **ليس** ستوكاستيك السعر ولا RSI. هو ستوكاستيك
مطبَّق على **قيم RSI نفسها**:

    ١) احسب RSI بطول ‎rsi_length‎
    ٢) اسأل: أين يقع RSI الآن ضمن مداه في آخر ‎stoch_length‎ شمعة؟
    ٣) نعّم الجواب بمتوسّطٍ بسيط طوله ‎k‎  ← الخطّ ‎%K‎
    ٤) نعّم ‎%K‎ بمتوسّطٍ طوله ‎d‎          ← الخطّ ‎%D‎

والخطأ الشائع أن يُحسب ستوكاستيك على السعر ويُسمّى StochRSI —
والفرق ليس اسمياً: مؤشّر ستيرمان وكرول (١٩٩٤) وُضع لأنّ RSI نادراً
ما يبلغ ٣٠ أو ٧٠ على الأطر القصيرة، فيبقى «بلا إشارة» شهوراً.
وقياسُه ضمن مداه هو يجعله يبلغ طرفيه كثيراً.

═══ ولهذا هو حسّاس، وهذا عيبه لا ميزته ═══

‏StochRSI يصل إلى ١٠٠ و٠ عشرات المرّات في الشهر. فقراءة «تشبّع
شرائي» منه لا تعني قمّة: في اتّجاهٍ صاعد قويّ يبقى فوق ٨٠ أسابيع،
ومن باع عندها باع أوّل الحركة.

فهو مؤشّر **توقيتٍ داخل اتّجاهٍ معروف**، لا مؤشّر انعكاس. وهذه
الوحدة تحسبه وتصفه، ولا تفتي بما يعنيه.

═══ ولا يدخل التقييم ═══

النقاط والتوصية لا تمسّهما هذه الوحدة. وسبب ذلك مقيس: من ٢١ سبباً
تُصدره الاستراتيجية اختُبرت كلّها على الصفقات المحسومة، فبدا ٦
منها ذا دلالة فردية، ولم ينجُ **ولا واحد** من تصحيح بنياميني–هوخبرغ
للاختبارات المتعدّدة. فإضافة عاملين جديدين بلا قياسٍ تُضعف ما بُني.

و‏``tools_osc_measure.py`` يقيس: هل تفرّق حالتهما عند الدخول بين
الرابح والخاسر فعلاً؟ فإن أثبتا فرقاً يتجاوز الصدفة دخلا بدليل.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .pine import rsi, sma

__all__ = ["stoch_rsi", "stoch_rsi_state", "macd_state"]


def stoch_rsi(src: pd.Series, rsi_length: int = 14, stoch_length: int = 14,
              k: int = 3, d: int = 3) -> pd.DataFrame:
    """‏%K و‎%D‎ بمقياس ٠–١٠٠، مع عمود ‎raw‎ قبل التنعيم.

    الإعدادات الافتراضية (١٤‏/١٤‏/٣‏/٣) هي إعدادات TradingView —
    فمن يقارن الشاشة بشارته يجب أن يرى الرقم نفسه، لا رقماً
    «أفضل» يخالفه.
    """
    src = src.astype(float)
    r = rsi(src, rsi_length)

    lo = r.rolling(stoch_length, min_periods=stoch_length).min()
    hi = r.rolling(stoch_length, min_periods=stoch_length).max()

    # ═══ المقام صفراً ═══
    #
    # ‏RSI ثابت تماماً خلال النافذة (سوقٌ راكد، أو رمزٌ لا يتداول)
    # يجعل ‎hi == lo‎. والقسمة تُنتج ‎inf‎ أو ‎nan‎ حسب البسط —
    # ورقمٌ لا نهائي يمرّ في JSON كـ ``NaN`` فيكسر الرسم صامتاً.
    #
    # والصواب هنا ليس صفراً ولا مئة: لا معنى للموضع ضمن مدىً
    # معدوم. فيُترك ‎NaN‎ ويُحذف من الرسم.
    span = (hi - lo).replace(0.0, np.nan)
    raw = (r - lo) / span * 100.0

    k_line = sma(raw, k)
    d_line = sma(k_line, d)

    return pd.DataFrame({"raw": raw, "k": k_line, "d": d_line},
                        index=src.index)


# ═══ الحدود ═══
#
# ٨٠‏/٢٠ لا ٧٠‏/٣٠: مدى StochRSI ممتلئ الأطراف بطبيعته، والحدّان
# الأضيق يُنتجان إشارةً كل بضع شمعات.
OVERBOUGHT = 80.0
OVERSOLD = 20.0


def _f(value) -> float | None:
    """رقمٌ نظيف أو ‎None‎ — لا ‎NaN‎ يعبر إلى الواجهة."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(out) else out


def stoch_rsi_state(frame: pd.DataFrame) -> dict:
    """يصف آخر **شمعتين مغلقتين** — لا الجارية.

    ═══ لماذا يُسقط الأخيرة ═══
    #
    الشمعة الجارية تتغيّر حتى تُغلق. و‎%K‎ محسوبٌ عليها يعبر ‎%D‎
    ثمّ يرتدّ قبل الإغلاق مراراً — فالاختبار الخلفي يبدو ممتازاً
    والتطبيق عاجزاً. وهذه هي القاعدة التي يمشي عليها النظام كلّه.

    والتقاطع يحتاج شمعتين: الحالة الآن، والحالة قبلها.
    """
    if frame is None or len(frame) < 3:
        return {"k": None, "d": None, "zone": "unknown", "cross": "none",
                "text": "بيانات غير كافية"}

    # ‎-2‎ لا ‎-1‎: الأخيرة جارية
    k_now, d_now = _f(frame["k"].iloc[-2]), _f(frame["d"].iloc[-2])
    k_prev, d_prev = _f(frame["k"].iloc[-3]), _f(frame["d"].iloc[-3])

    if k_now is None or d_now is None:
        return {"k": None, "d": None, "zone": "unknown", "cross": "none",
                "text": "غير محسوب بعد"}

    zone = ("overbought" if k_now >= OVERBOUGHT else
            "oversold" if k_now <= OVERSOLD else "middle")

    cross = "none"
    if None not in (k_prev, d_prev):
        if k_prev <= d_prev and k_now > d_now:
            cross = "up"
        elif k_prev >= d_prev and k_now < d_now:
            cross = "down"

    zone_ar = {"overbought": "منطقة التشبّع الشرائي",
               "oversold": "منطقة التشبّع البيعي",
               "middle": "المنطقة الوسطى"}[zone]

    if cross == "up":
        text = f"‏%K عبر %D صعوداً من {zone_ar}"
    elif cross == "down":
        text = f"‏%K عبر %D هبوطاً من {zone_ar}"
    else:
        text = f"‏%K فوق %D في {zone_ar}" if k_now > d_now \
            else f"‏%K تحت %D في {zone_ar}"

    # ═══ التحذير الذي يمنع القراءة الخاطئة ═══
    #
    # «تشبّع شرائي» تُقرأ «بِع». وفي اتّجاهٍ صاعد قويّ يبقى فوق ٨٠
    # أسابيع — ومن باع عندها باع أوّل الحركة.
    note = ""
    if zone == "overbought":
        note = "والتشبّع الشرائي يدوم في الاتّجاه الصاعد — ليس أمر بيع"
    elif zone == "oversold":
        note = "والتشبّع البيعي يدوم في الاتّجاه الهابط — ليس أمر شراء"

    return {"k": round(k_now, 1), "d": round(d_now, 1), "zone": zone,
            "cross": cross, "text": text, "note": note}


def macd_state(frame: pd.DataFrame) -> dict:
    """يصف MACD من آخر شمعتين مغلقتين.

    والمدرّج أهمّ من الخطّ: تقلّصه يسبق التقاطع، فيقول «الزخم يخفّ»
    قبل أن يقول الخطّ «انعكس».
    """
    if frame is None or len(frame) < 3:
        return {"macd": None, "signal": None, "hist": None,
                "cross": "none", "text": "بيانات غير كافية"}

    line, sig = _f(frame["macd"].iloc[-2]), _f(frame["signal"].iloc[-2])
    hist, hist_prev = _f(frame["hist"].iloc[-2]), _f(frame["hist"].iloc[-3])
    line_p, sig_p = _f(frame["macd"].iloc[-3]), _f(frame["signal"].iloc[-3])

    if line is None or sig is None or hist is None:
        return {"macd": None, "signal": None, "hist": None,
                "cross": "none", "text": "غير محسوب بعد"}

    cross = "none"
    if None not in (line_p, sig_p):
        if line_p <= sig_p and line > sig:
            cross = "up"
        elif line_p >= sig_p and line < sig:
            cross = "down"

    side = "فوق الصفر" if line > 0 else "تحت الصفر"
    if cross == "up":
        text = f"تقاطع صعودي {side}"
    elif cross == "down":
        text = f"تقاطع هبوطي {side}"
    elif hist_prev is not None and abs(hist) < abs(hist_prev):
        # التقلّص يُقال بصيغته: يخفّ لا ينعكس
        text = (f"المدرّج يتقلّص {'فوق' if hist > 0 else 'تحت'} الصفر — "
                "الزخم يخفّ")
    else:
        text = f"المدرّج يتمدّد {'فوق' if hist > 0 else 'تحت'} الصفر"

    return {"macd": round(line, 6), "signal": round(sig, 6),
            "hist": round(hist, 6), "cross": cross, "text": text,
            # ═══ لماذا لا نسبة مئوية ═══
            #
            # ‏MACD بوحدة السعر — قيمته لبتكوين بالآلاف ولرمزٍ بريال
            # بالكسور. فمقارنة رمزين برقمه المطلق بلا معنى، ولا
            # يُعرض إلّا مع رمزه.
            "unit": "بوحدة السعر"}
