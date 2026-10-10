# -*- coding: utf-8 -*-
"""تقاطع MACD الصاعد مع StochRSI موجب — الحالة التي وصفتَها.

═══ الوصف بكلماتك ═══

    «أنجح الصفقات دائماً عندما يتقاطع MACD إيجابياً تحت أو فوق
     الصفر، مع تقاطع أو استمرارٍ في الإيجابية لمؤشّر StochRSI».

فالشرطان:

    MACD      خطّه عبر خطّ الإشارة صعوداً خلال آخر ``WINDOW`` شموع
              مغلقة، وما زال فوقه — تحت الصفر أو فوقه، والموضع
              يُسجَّل لأنّهما حالتان مختلفتان (انعكاسٌ مبكّر مقابل
              استمرار اتّجاه).
    StochRSI  ‏‎%K‎ فوق ‎%D‎ — إمّا عبرَه للتوّ (تقاطع) وإمّا باقٍ
              فوقه (استمرار).

═══ لماذا «خلال آخر ثلاث شموع» لا «في الشمعة نفسها» ═══

التقاطعان نادراً ما يقعان في الشمعة ذاتها: StochRSI أسرع بكثير من
MACD. واشتراط التزامن الحرفيّ يُفرغ القائمة تقريباً — فيُقرأ
«الحالة نادرة» وهي ليست كذلك. والنافذة صغيرة عمداً: تقاطعٌ عمره
عشر شموع ليس «تقاطعاً» بل اتّجاهاً قائماً.

═══ وما لا تدّعيه هذه الوحدة ═══

**المؤشّران من عائلةٍ واحدة.** كلاهما يقيس الزخم من الإغلاق نفسه
(المادّة ١٧). فاتّفاقهما ليس شاهدين مستقلّين بل شاهدٌ واحد يتكلّم
مرّتين — ولهذا هي **فرزٌ** يُعرَض، لا نقاطٌ تُضاف إلى التقييم.

و«دائماً» ذاكرة. الذاكرة تحتفظ بالرابحات وتنسى الخاسرات التي كانت
على الحالة نفسها. ``tools_osc_measure.py`` يقيسها على صفقاتك
المحسومة ويقول: هل تربح أكثر من غيرها، أم تبدو كذلك فقط.

═══ والشمعة المغلقة وحدها ═══

الأخيرة جارية فتُسقَط. ‎%K‎ يعبر ‎%D‎ ويرتدّ داخل الشمعة الواحدة
مراراً، والقرار عليه يجعل الحالة تظهر وتختفي كل دقيقة.
"""
from __future__ import annotations

import logging
import math

log = logging.getLogger("scanner.analysis.macd_stoch")

__all__ = ["evaluate", "read", "STATES", "STATE_LABELS", "WINDOW"]

#: أقصى عمرٍ لتقاطع MACD يُعدّ «تقاطعاً» لا «اتّجاهاً قائماً»
WINDOW = 3

STATES = ("aligned", "macd_only", "stoch_only", "none", "unknown")
STATE_LABELS = {
    "aligned": "MACD تقاطع صاعد + StochRSI موجب",
    "macd_only": "تقاطع MACD وحده — StochRSI سالب",
    "stoch_only": "StochRSI موجب بلا تقاطع MACD قريب",
    "none": "لا هذا ولا ذاك",
    "unknown": "غير محسوب",
}

_CACHE: dict[tuple, tuple] = {}
_CACHE_MAX = 600


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def evaluate(close) -> dict:
    """الحالة من سلسلة الإغلاق — دالّةٌ نقيّة بلا قرص ولا شبكة.

    ``close`` يشمل الشمعة الجارية في آخره، وتُسقَط هنا.
    """
    from scanner.indicators.momentum import stoch_rsi
    from scanner.indicators.trend import macd

    if close is None or len(close) < 60:
        return {"ok": False, "state": "unknown",
                "why": f"شموع غير كافية ({0 if close is None else len(close)})"}

    src = close.astype(float)
    m = macd(src).iloc[:-1]                 # المغلق وحده
    s = stoch_rsi(src).iloc[:-1]
    if len(m) < WINDOW + 2 or len(s) < 2:
        return {"ok": False, "state": "unknown", "why": "تاريخ قصير"}

    line, sig = m["macd"], m["signal"]

    # ── MACD: أقرب تقاطعٍ صاعد خلال النافذة ──
    bars_since = None
    cross_zero = None
    for back in range(0, WINDOW):
        i, j = len(m) - 1 - back, len(m) - 2 - back
        a, b = _num(line.iloc[i]), _num(sig.iloc[i])
        pa, pb = _num(line.iloc[j]), _num(sig.iloc[j])
        if None in (a, b, pa, pb):
            continue
        if pa <= pb and a > b:
            bars_since = back
            cross_zero = "below" if a < 0 else "above"
            break
    now_line, now_sig = _num(line.iloc[-1]), _num(sig.iloc[-1])
    if now_line is None or now_sig is None:
        return {"ok": False, "state": "unknown", "why": "MACD غير محسوب"}
    # ═══ والتقاطع الذي انعكس لا يُحسب ═══
    #
    # عبرَ صعوداً قبل شمعتين ثمّ هبط تحت الإشارة: هذا تقاطعٌ فشل،
    # وعدُّه «تقاطعاً حديثاً» يُدرج أسوأ الحالات في القائمة.
    macd_up = bars_since is not None and now_line > now_sig

    # ── StochRSI: تقاطعٌ أو استمرار ──
    k, d = _num(s["k"].iloc[-1]), _num(s["d"].iloc[-1])
    pk, pd_ = _num(s["k"].iloc[-2]), _num(s["d"].iloc[-2])
    if k is None or d is None:
        return {"ok": False, "state": "unknown", "why": "StochRSI غير محسوب"}
    if k > d and pk is not None and pd_ is not None and pk <= pd_:
        stoch_mode = "cross"
    elif k > d:
        stoch_mode = "continuation"
    else:
        stoch_mode = "negative"
    stoch_up = stoch_mode != "negative"

    if macd_up and stoch_up:
        state = "aligned"
    elif macd_up:
        state = "macd_only"
    elif stoch_up:
        state = "stoch_only"
    else:
        state = "none"

    zone_ar = {"below": "تحت الصفر", "above": "فوق الصفر"}.get(cross_zero, "")
    mode_ar = {"cross": "تقاطع", "continuation": "استمرار",
               "negative": "سالب"}[stoch_mode]
    text = (f"MACD عبر صعوداً {zone_ar} قبل {bars_since} شمعة · "
            f"StochRSI {mode_ar}" if macd_up else
            f"لا تقاطع MACD صاعد خلال {WINDOW} شموع · StochRSI {mode_ar}")
    return {
        "ok": True, "state": state, "label": STATE_LABELS[state],
        "macd_bars_since": bars_since if macd_up else None,
        "macd_zone": cross_zero if macd_up else None,
        "stoch_mode": stoch_mode,
        "k": round(k, 1), "d": round(d, 1),
        "text": text,
    }


def read(market: str, symbol: str, timeframe: str) -> dict:
    """الحالة من الشموع المخزَّنة — ولا ترمي أبداً."""
    try:
        from scanner import storage

        df = storage.load(market, symbol, timeframe)
        if df is None or len(df) < 60:
            n = 0 if df is None else len(df)
            return {"ok": False, "state": "unknown",
                    "why": f"شموع غير كافية ({n})"}
        # مفتاحٌ بزمن آخر شمعة: شمعةٌ جديدة تُبطله وحدها
        key = (market, symbol, timeframe, str(df.index[-1]))
        hit = _CACHE.get(key)
        if hit is not None:
            return hit[0]
        out = evaluate(df["close"])
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = (out,)
        return out
    except Exception as exc:  # noqa: BLE001
        log.info("تعذّرت قراءة MACD/StochRSI %s %s: %s",
                 symbol, timeframe, str(exc)[:90])
        return {"ok": False, "state": "unknown", "why": str(exc)[:90]}
