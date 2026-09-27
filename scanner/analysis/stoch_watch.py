# -*- coding: utf-8 -*-
"""«راكبُ التشبّع» — تشبّعٌ شرائيّ **داخل** اتّجاهٍ صاعد.

═══ الحالة التي يصفها ═══

‏StochRSI فوق ٨٠ يُقرأ «بِع». وهي قراءةٌ خاطئة في الاتّجاه الصاعد
القويّ: المؤشّر يبقى هناك أسابيع، ومن باع عندها باع أوّل الحركة.
ولهذا يحمل ``stoch_rsi_state`` تحذيراً نصّياً منذ بنائه.

وهذه الوحدة تحوّل ذلك التحذير إلى **حالةٍ تُفرَز بها**:

    riding      تشبّعٌ شرائيّ واتّجاهٌ صاعد   ← الحالة المقصودة
    exhausted   تشبّعٌ شرائيّ بلا اتّجاه صاعد ← تحذيرٌ حقيقيّ
    oversold    تشبّعٌ بيعيّ
    middle      لا هذا ولا ذاك

═══ ولماذا يلزم شرط الاتّجاه ═══

الفرز بـ«فوق ٨٠» وحده يجمع الحالتين: الركوب والإنهاك. وهما
نقيضان — الأولى استمرارٌ والثانية قمّة. وخلطُهما يُنتج قائمةً
نصفُها ضدّ ما يُبحَث عنه، ثمّ تُنسَب نتيجتُها كلّها إلى «الفلتر».

والاتّجاه هنا: السعر فوق ‎EMA50‎ و‎EMA50‎ صاعد. تعريفٌ واحد
مكتوبٌ في مكانٍ واحد — لا «صاعد» بمعنىً هنا وآخر هناك.

═══ وما لا تدّعيه ═══

لا تقول إنّ هذه الحالة تربح. هي **وصفٌ** يُفرَز به، ومقولةُ «أغلب
صفقاتي الناجحة كانت هكذا» ذاكرةٌ لا قياس — والذاكرة تحتفظ
بالرابحات. و``tools_stoch_measure.py`` يفحصها على الصفقات
المحسومة فعلاً.

═══ والشمعة المغلقة وحدها ═══

``stoch_rsi_state`` يقرأ ‎-2‎ لا ‎-1‎. و‎%K‎ يعبر ‎%D‎ ويرتدّ داخل
الشمعة الواحدة مراراً، فبناءُ فرزٍ عليها يجعل القائمة تتبدّل كل
دقيقة بلا أن يتغيّر شيء.
"""
from __future__ import annotations

import logging

log = logging.getLogger("scanner.analysis.stoch_watch")

__all__ = ["read", "STATES", "STATE_LABELS", "classify"]

STATES = ("riding", "exhausted", "oversold", "middle", "unknown")

STATE_LABELS = {
    "riding": "راكب التشبّع — تشبّع شرائي في اتّجاه صاعد",
    "exhausted": "تشبّع شرائي بلا اتّجاه صاعد",
    "oversold": "تشبّع بيعي",
    "middle": "المنطقة الوسطى",
    "unknown": "غير محسوب",
}

#: ما يُعدّ «الحالة المقصودة» في الفرز
TARGET = "riding"

_CACHE: dict[tuple, tuple] = {}
_CACHE_MAX = 600


def classify(zone: str, uptrend: bool | None) -> str:
    """الحالة من المنطقة والاتّجاه.

    ═══ والاتّجاه المجهول لا يصير «راكباً» ═══

    ``uptrend is None`` يعني شموعاً لا تكفي لـ‎EMA200‎ — لا يعني
    «ليس صاعداً». وعدُّه ركوباً يُدخل رمزاً لم يُفحَص في القائمة،
    وعدُّه إنهاكاً يُخرج رمزاً قد يكون المطلوب. فالصواب أن يُقال
    مجهولاً.
    """
    if zone == "unknown" or zone is None:
        return "unknown"
    if zone == "oversold":
        return "oversold"
    if zone != "overbought":
        return "middle"
    if uptrend is None:
        return "unknown"
    return "riding" if uptrend else "exhausted"


def _uptrend(close) -> bool | None:
    """السعر فوق ‎EMA50‎ و‎EMA50‎ صاعد — على المغلق وحده."""
    from scanner.indicators.pine import ema

    if close is None or len(close) < 60:
        return None
    try:
        e = ema(close.astype(float), 50)
        # ‎-2‎: الشمعة الجارية لا تدخل قراراً
        now, prev = float(e.iloc[-2]), float(e.iloc[-7])
        px = float(close.iloc[-2])
    except (IndexError, ValueError, TypeError):
        return None
    if now != now or prev != prev or px != px:      # NaN
        return None
    return bool(px > now and now > prev)


def read(market: str, symbol: str, timeframe: str) -> dict:
    """حالة التشبّع لهذا الرمز — ولا ترمي أبداً.

    تقرأ الشموع المخزَّنة، فلا طلبَ شبكة ولا انتظار: الشاشة تعرض
    عشرات المراقبات، وطلبٌ لكلٍّ منها يجعلها تتأخّر ثوانيَ لكل صفّ.
    """
    try:
        from scanner import storage
        from scanner.indicators.momentum import stoch_rsi, stoch_rsi_state

        df = storage.load(market, symbol, timeframe)
        if df is None or len(df) < 60:
            n = 0 if df is None else len(df)
            return {"ok": False, "state": "unknown",
                    "why": f"شموع غير كافية ({n})"}

        # مفتاح التخبئة يحمل زمن آخر شمعة: شمعةٌ جديدة تُبطِله
        # تلقائياً، فلا مهلةٌ تُضبط ولا قيمةٌ تشيخ بصمت.
        key = (market, symbol, timeframe, str(df.index[-1]))
        hit = _CACHE.get(key)
        if hit is not None:
            return hit[0]

        frame = stoch_rsi(df["close"].astype(float))
        st = stoch_rsi_state(frame)
        up = _uptrend(df["close"])
        state = classify(st.get("zone", "unknown"), up)

        out = {
            "ok": True,
            "k": st.get("k"), "d": st.get("d"),
            "zone": st.get("zone"), "cross": st.get("cross"),
            "uptrend": up,
            "state": state,
            "label": STATE_LABELS[state],
            "text": st.get("text", ""),
            "note": st.get("note", ""),
        }
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = (out,)
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("تعذّرت قراءة التشبّع %s %s: %s",
                 symbol, timeframe, str(exc)[:90])
        return {"ok": False, "state": "unknown", "why": str(exc)[:90]}
