# -*- coding: utf-8 -*-
"""وسمُ النتيجة بحاجزين — «بلغ الهدف قبل الوقف؟» لا «كم صعد؟».

═══ لماذا حاجزان لا عائدٌ بعد ن شمعة ═══

«متوسّط العائد بعد اثنتي عشرة شمعة» رقمٌ لا يُنفَّذ. فمن دخل ثمّ
نزل السعر ٣×ATR قبل أن يصعد قد خرج بوقفه، ولا يناله ذلك المتوسّط
أبداً. والرقم يبدو ممتازاً لأنّه يُحسب على مَن لم يُوقَف.

فالوسم هنا يحاكي ما يقع فعلاً:

    هدف   = الدخول + ‎target×ATR‎
    وقف    = الدخول − ‎stop×ATR‎

ويُمشى للأمام شمعةً شمعة: أيّهما بلغ أوّلاً.

═══ و‏ATR لا نسبةٌ مئوية ═══

‏«+3٪» هدفٌ قريبٌ جدّاً على رمزٍ يتحرّك ٨٪ يومياً، وبعيدٌ جدّاً على
آخر يتحرّك ١٪. و‏ATR يقيس تذبذب الرمز نفسه، فالهدف والوقف
يتكيّفان معه — وتصير الأرقام قابلة للمقارنة بين الرموز.

═══ والشمعة التي تبلغ الحاجزين ═══

شمعةٌ قاعها تحت الوقف وقمّتها فوق الهدف: أيّهما وقع أوّلاً لا
يُعرَف من شمعةٍ واحدة. والاحتمالان متساويان ظاهرياً، لكنّ عدّها
ربحاً يُنتج نظاماً يبدو رابحاً وهو يُوقَف في التطبيق.

فتُعدّ **خسارة** — وهو الاتّجاه المتحفّظ — ويُعلَن عددها. فإن كانت
كثيرة فالأفق أو الحاجزان غير مناسبين لهذا الفريم.

═══ ولا نظرَ إلى المستقبل ═══

‏ATR والدخول من الشمعة المغلقة ``i``، والمشي يبدأ من ``i+1``.
وقراءةُ ``high`` أو ``low`` للشمعة ``i`` نفسها تسريبٌ: لحظة
القرار لم تكن قد أُغلقت.
"""
from __future__ import annotations

import numpy as np

__all__ = ["label_forward", "WIN", "LOSS", "OPEN", "DEFAULTS"]

WIN, LOSS, OPEN = 1, 0, -1

DEFAULTS = {
    # ‏2:1 — ونسبة النجاح المطلوبة للتعادل ٣٣٪ قبل الكلفة
    "target_atr": 2.0,
    "stop_atr": 1.0,
    # أفقٌ يكفي لحركةٍ على هذا الفريم. وما لم يُحسم فيه يُعدّ
    # ``OPEN`` ولا يُحتسب — لا ربحاً ولا خسارة.
    "horizon": 24,
    "atr_len": 14,
}


def label_forward(df, *, target_atr: float = 2.0, stop_atr: float = 1.0,
                  horizon: int = 24, atr_len: int = 14) -> dict:
    """يسم كل شمعةٍ بنتيجة الدخول عند إغلاقها.

    يعيد مصفوفاتٍ بطول ``df``: ``label`` و``bars`` و``ambiguous``.
    """
    from scanner.indicators.pine import atr as atr_fn

    n = len(df)
    label = np.full(n, OPEN, dtype="int8")
    bars = np.full(n, -1, dtype="int32")
    ambiguous = np.zeros(n, dtype=bool)
    if n < atr_len + horizon + 2:
        return {"label": label, "bars": bars, "ambiguous": ambiguous,
                "ok": False, "why": f"يلزم {atr_len + horizon + 2} شمعة"}

    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    close = df["close"].astype(float).to_numpy()
    a = atr_fn(df, atr_len).to_numpy(dtype="float64")

    for i in range(n):
        atr_i = a[i]
        if not np.isfinite(atr_i) or atr_i <= 0:
            continue
        # ═══ الحدّ الأخير ═══
        #
        # شمعةٌ لا يتبعها أفقٌ كامل لا تُوسَم: وسمُها بما توفّر
        # يجعل الشموع الأخيرة — وهي الأقرب للحاضر — تُقاس بأفقٍ
        # أقصر، فتبدو أسوأ أو أفضل لسببٍ لا علاقة له بالإشارة.
        if i + horizon >= n:
            break
        entry = close[i]
        up = entry + target_atr * atr_i
        down = entry - stop_atr * atr_i

        for j in range(i + 1, min(i + 1 + horizon, n)):
            hit_up = high[j] >= up
            hit_down = low[j] <= down
            if hit_up and hit_down:
                # الحاجزان في شمعةٍ واحدة: الترتيب مجهول
                ambiguous[i] = True
                label[i] = LOSS
                bars[i] = j - i
                break
            if hit_up:
                label[i] = WIN
                bars[i] = j - i
                break
            if hit_down:
                label[i] = LOSS
                bars[i] = j - i
                break

    return {"label": label, "bars": bars, "ambiguous": ambiguous,
            "ok": True, "why": "",
            "settled": int((label != OPEN).sum()),
            "ambiguous_n": int(ambiguous.sum()),
            "params": {"target_atr": target_atr, "stop_atr": stop_atr,
                       "horizon": horizon, "atr_len": atr_len}}


def rate(label: np.ndarray, mask: np.ndarray | None = None) -> dict:
    """نسبة النجاح على المحسوم وحده — والمفتوح لا يُحتسب.

    عدُّ ``OPEN`` خسارةً يخلط «لم يُحسم في الأفق» بـ«بلغ الوقف»،
    وهما مختلفان: الأوّل خروجٌ بالزمن والثاني بالسعر.
    """
    sel = label if mask is None else label[mask]
    settled = sel[sel != OPEN]
    n = int(settled.size)
    k = int((settled == WIN).sum())
    return {"n": n, "wins": k,
            "rate": round(100.0 * k / n, 1) if n else None,
            "open": int((sel == OPEN).sum())}
