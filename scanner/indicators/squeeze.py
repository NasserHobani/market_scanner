# -*- coding: utf-8 -*-
"""انضغاط التقلّب واحتمال التمدّد — بالقياس لا بالادّعاء.

═══ الفكرة ═══

التقلّب يتناوب: مدىً ضيّق ثمّ واسع ثمّ ضيّق. فحين ينضغط المدى إلى
أدنى مستوياته التاريخية، يزيد احتمال تمدّده. هذا مبدأٌ قديم
(بولنجر، NR7) وليس اختراعاً هنا.

═══ وما لا يُفعل هنا ═══

لا يُقال «احتمال الانفجار ٧٠٪» لأنّ الشكل يوحي بذلك. الاحتمال
**يُقاس** على شموع الرمز نفسه: كم مرّة انضغط تاريخياً، وكم مرّة
تمدّد بعدها فعلاً خلال أفقٍ محدَّد.

ويُقاس معه **معدّل الأساس**: كم مرّة تمدّد السعر من أيّ نقطة كانت.
فإن كان الانضغاط لا يرفع الاحتمال عن الأساس فهو لا يفيد — ويُقال
ذلك صراحةً بدل عرض رقمٍ يبدو كبيراً وهو الأساس نفسه.

═══ والتعريفات مكتوبة ═══

    الانضغاط — عرض قناة بولنجر (٢٠) في أدنى ``SQUEEZE_PCT``٪ من
               آخر ``LOOKBACK`` شمعة لهذا الرمز.

    التمدّد  — أن يبلغ مدى الحركة (أعلى ناقص أدنى) خلال الأفق
               ``horizon`` مقدارَ ``EXPANSION_ATR`` ضعفاً من ATR
               لحظة الرصد.

كلاهما نسبيّ للرمز نفسه: سهمٌ سعودي هادئ وعملةٌ متقلّبة لا
يُقاسان بمسطرة واحدة.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# عرض القناة يُقارَن بآخر هذا العدد من الشموع — لا بقيمةٍ مطلقة
LOOKBACK = 120

# أدنى نسبة مئوية تُعدّ انضغاطاً
SQUEEZE_PCT = 15.0

# التمدّد: مدى الحركة ÷ ATR لحظة الرصد
EXPANSION_ATR = 3.0

BB_LENGTH = 20
ATR_LENGTH = 14


def bb_width(df: pd.DataFrame, length: int = BB_LENGTH) -> pd.Series:
    """عرض قناة بولنجر منسوباً إلى وسطها.

    القسمة على الوسط تجعله قابلاً للمقارنة بين رمزٍ سعره ٥ وآخر
    سعره ٦٤٠٠٠ — والعرض المطلق لا يُقارَن.
    """
    close = df["close"].astype(float)
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std(ddof=0)
    return ((2 * sd) / mid.replace(0, np.nan)) * 100.0


def squeeze_rank(df: pd.DataFrame, *, length: int = BB_LENGTH,
                 lookback: int = LOOKBACK) -> pd.Series:
    """رتبة عرض القناة الحالي بين آخر ``lookback`` شمعة (٠–١٠٠).

    الصفر أضيق ما كان، والمئة أوسع ما كان. والرتبة تُحسب على
    النافذة **المنتهية بالشمعة الحالية** — فلا تُستعمل شمعةٌ
    لاحقة، وهو تسرّبٌ يجعل النتيجة ممتازة على الورق فقط.
    """
    w = bb_width(df, length)
    return w.rolling(lookback, min_periods=max(20, lookback // 4)).apply(
        lambda a: float((a[:-1] < a[-1]).mean() * 100.0) if len(a) > 1 else np.nan,
        raw=True,
    )


def atr_series(df: pd.DataFrame, length: int = ATR_LENGTH) -> pd.Series:
    from .pine import atr

    return atr(df, length)


def measure(df: pd.DataFrame, *, horizon: int,
            squeeze_pct: float = SQUEEZE_PCT,
            expansion_atr: float = EXPANSION_ATR) -> dict:
    """يقيس على تاريخ الرمز: هل الانضغاط يسبق التمدّد فعلاً؟

    يعيد عدّادات خامّة — النسب والفواصل تُحسب في طبقةٍ أعلى، كي
    تُجمع عدّة رموز قبل حساب أيّ نسبة. وجمعُ النسب خطأ: نسبة رمزٍ
    له خمس حالات لا تساوي نسبة رمزٍ له خمسمئة.
    """
    if df is None or len(df) < LOOKBACK + horizon + BB_LENGTH:
        return {"usable": 0, "squeezed": 0, "squeezed_hits": 0,
                "base": 0, "base_hits": 0, "bars_to_hit": []}

    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    rank = squeeze_rank(df).to_numpy()
    atr = atr_series(df).to_numpy()
    n = len(df)

    usable = squeezed = squeezed_hits = base = base_hits = 0
    bars_to_hit: list[int] = []

    # آخر ``horizon`` شمعة لا تُقاس: لم يمضِ عليها الأفق بعد،
    # واعتبارها «لم تنفجر» يخفض الاحتمال كذباً.
    for i in range(LOOKBACK, n - horizon):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        window_hi = high[i + 1: i + 1 + horizon]
        window_lo = low[i + 1: i + 1 + horizon]
        if window_hi.size == 0:
            continue
        usable += 1

        need = expansion_atr * a
        # أوّل شمعة يبلغ فيها المدى التراكمي الحدّ
        run_hi = np.maximum.accumulate(window_hi)
        run_lo = np.minimum.accumulate(window_lo)
        spread = run_hi - run_lo
        hit_idx = int(np.argmax(spread >= need)) if (spread >= need).any() else -1
        hit = hit_idx >= 0

        base += 1
        base_hits += int(hit)

        r = rank[i]
        if np.isfinite(r) and r <= squeeze_pct:
            squeezed += 1
            if hit:
                squeezed_hits += 1
                bars_to_hit.append(hit_idx + 1)

    return {"usable": usable, "squeezed": squeezed,
            "squeezed_hits": squeezed_hits,
            "base": base, "base_hits": base_hits,
            "bars_to_hit": bars_to_hit}


def current_state(df: pd.DataFrame) -> dict:
    """حالة الرمز الآن — بلا حكمٍ ولا احتمال.

    الاحتمال يأتي من ``measure`` على التاريخ، لا من الحالة
    اللحظية. وهذه تقول فقط: كم هو منضغط الآن، وكم ‏ATR يساوي.
    """
    if df is None or len(df) < BB_LENGTH + 5:
        return {}
    rank = squeeze_rank(df)
    atr = atr_series(df)
    close = df["close"].astype(float)
    r = rank.iloc[-1]
    a = atr.iloc[-1]
    c = close.iloc[-1]
    if not np.isfinite(r) or not np.isfinite(a) or a <= 0:
        return {}
    return {
        "squeeze_rank": round(float(r), 1),
        "is_squeezed": bool(r <= SQUEEZE_PCT),
        "atr": float(a),
        "close": float(c),
        # مقدار الحركة المطلوبة نسبةً — يُقارَن بما يتوقّعه المتداول
        "expansion_pct": round(EXPANSION_ATR * float(a) / float(c) * 100, 2),
        "bb_width": round(float(bb_width(df).iloc[-1]), 3),
    }


__all__ = ["bb_width", "squeeze_rank", "atr_series", "measure",
           "current_state", "LOOKBACK", "SQUEEZE_PCT", "EXPANSION_ATR"]
