# -*- coding: utf-8 -*-
"""التقاء الزخم — ‏MACD يؤكّد التحوّل، و‏StochRSI يحدّد لحظته.

═══ وظيفتان لا إشارتان ═══

    MACD      = هل بدأت الطاقة تتغيّر؟        (تأكيد التحوّل)
    StochRSI  = ومتى تبدأ الحركة القصيرة؟     (التوقيت)

والفرق عمليّ: ‏MACD يتحرّك ببطء فيقول «الاتجاه العميق يتحسّن»
ويتأخّر عن القاع. و‏StochRSI يتحرّك بسرعة فيقول «الآن» — ويكذب
كثيراً وحده. فالأوّل يختار **الرمز**، والثاني يختار **اللحظة**.

═══ ولماذا لا يُحسبان دليلين ═══

كلاهما مؤشّر زخم. ومقياسان لشيءٍ واحد ليسا شاهدين مستقلّين، بل
شاهدٌ واحد بصوتين. وهذا هو العطب الذي وقع في وحدة الأدلّة من قبل:
ثلاثة «أسباب» بأرقامٍ متطابقة كانت الصفقات الثمانية عشر نفسها.

ولهذا تعيد هذه الوحدة **درجةً واحدة من عشر** لا عاملين. ووزنُها
في PES مأخوذ من ميزانية عائلة الزخم نفسها، فلا تكبر العائلة:

    قبل:  rsi 5 + macd 5 + divergence 5            = 15
    بعد:  confluence 10 + rsi 3 + divergence 2     = 15

═══ والسلّم ليس خطّياً ═══

الدرجات من ٠ إلى ١٠ مراتب لا مجموع نقاط. والقفزة من ٦ إلى ٧ هي
دخول ‏StochRSI: أي أنّ التوقيت لا يُشترى بمزيدٍ من تأكيد MACD.
وهذا مقصود — ثلاثة مقاييس لـ MACD لا تصنع توقيتاً.

═══ وما لا تدّعيه ═══

الدرجة ترتيبٌ لا احتمال. ولا تقول «سيرتفع»، بل «تحسّن الزخم بلغ
هذه المرتبة». وأثرُها على النتيجة يبقى ١٠ من ١٠٠ — أي أنّها لا
تصنع إشارةً وحدها مهما بلغت.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["measure", "evaluate_confluence", "DEFAULTS", "TIER_LABELS"]

# القيم الافتراضية — كلّها قابلة للتجاوز من ``config/pes.yaml``
DEFAULTS = {
    "macd": {
        "fast": 12, "slow": 26, "signal": 9,
        "slope_bars": 5,
        # كم شمعة متتالية صاعدة تُسمّى «مدرَّجاً صاعداً»
        "rising_bars": 3,
        # ميلٌ فوق هذا يُسمّى «صعوداً واضحاً» (نسبةً لمدى المدرَّج)
        "strong_slope": 0.10,
    },
    "stoch_rsi": {
        "rsi_length": 14, "stoch_length": 14, "k": 3, "d": 3,
        "low_zone": 30.0,
        "high_zone": 80.0,
        # الخروج من منطقةٍ منخفضة يُقاس على هذه النافذة
        "from_low_bars": 8,
        # تشبّعٌ شرائي مزمن: كم شمعة فوق ‎high_zone‎ تُبطل «التوقيت»
        "max_overbought_bars": 6,
        # فوق هذا مع ارتفاعٍ سابق = متأخّر
        "late_level": 90.0,
    },
    "late": {
        # ارتفاعٌ تحقّق بالفعل — مع StochRSI مرتفع يعني «لا تطارد»
        "min_gain_pct": 15.0,
        "lookback_bars": 30,
    },
}

# كل مرتبةٍ باسمها الدقيق. و‏٥ و‏٦ منفصلتان عمداً: الفرق بينهما
# دعمُ RSI، ووسمُهما بنصٍّ واحد يجعل الشاشة تقول «‏RSI داعم» في
# الحالة التي يكون فيها غير داعمٍ تحديداً.
TIER_LABELS = {
    0: "زخم هابط",
    3: "المدرَّج بدأ يتحسّن",
    5: "المدرَّج صاعد — تأكيدٌ بلا توقيت",
    6: "المدرَّج صاعد و RSI داعم",
    7: "المدرَّج صاعد مع تقاطع StochRSI",
    8: "تقاطع StochRSI و MACD فوق إشارته",
    9: "التقاء كامل — وخروجٌ من منطقةٍ منخفضة",
    10: "التقاء كامل بتأكيدٍ من الاتجاه والحجم والانضغاط",
}


def _cfg(params: dict | None, *path, default=None):
    """قيمةٌ من ``pes.yaml`` أو من الافتراضي — بلا قيمٍ مزروعة."""
    node = (params or {}).get("momentum") or {}
    fallback = DEFAULTS
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
        fallback = fallback.get(key) if isinstance(fallback, dict) else None
    if node is None:
        return fallback if fallback is not None else default
    return node


def _closed(df: pd.DataFrame) -> pd.DataFrame:
    """يُسقط الشمعة الجارية — القرار على المغلق وحده.

    والفرق هنا حادّ: تقاطع ‎%K/%D‎ يظهر ويختفي داخل الشمعة الواحدة
    مرّاتٍ قبل إغلاقها. فبناء «توقيت» عليها يجعل الاختبار الخلفي
    ممتازاً والتطبيق عاجزاً.
    """
    return df.iloc[:-1] if df is not None and len(df) > 1 else df


def _f(v) -> float | None:
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(out) else out


# ═══════════════════ ١) قياس MACD ═══════════════════

def macd_reading(df: pd.DataFrame, params: dict | None = None) -> dict:
    """المدرَّج وميله وتسارعه — لا التقاطع وحده.

    ═══ لماذا الميل قبل التقاطع ═══

    التقاطع يقع **بعد** أن يعبر المدرَّج الصفر. والمدرَّج الصاعد
    وهو سالب::

        -0.08 → -0.06 → -0.04 → -0.02 → -0.01

    يقول الشيء نفسه قبله بشمعاتٍ عدّة. فالتقاطع تأكيدٌ متأخّر،
    والميل إشارةٌ مبكّرة — وهذه استراتيجية «ما قبل».
    """
    from scanner.indicators.trend import macd, slope

    d = _closed(df)
    bars = int(_cfg(params, "macd", "slope_bars", default=5))
    need = int(_cfg(params, "macd", "slow", default=26)) + bars + 5
    if d is None or len(d) < need:
        return {"ok": False, "why": f"يلزم {need} شمعة"}

    m = macd(d["close"].astype(float),
             int(_cfg(params, "macd", "fast", default=12)),
             int(_cfg(params, "macd", "slow", default=26)),
             int(_cfg(params, "macd", "signal", default=9)))
    hist = m["hist"]
    line, sig = m["macd"], m["signal"]

    cur = _f(hist.iloc[-1])
    prev = _f(hist.iloc[-2])
    if cur is None or prev is None:
        return {"ok": False, "why": "المدرَّج غير محسوب"}

    sl = float(slope(hist, bars))

    # ═══ التسارع ═══
    #
    # فرقُ الفروق: هل يتسارع التحسّن أم يخفّ؟ ومدرَّجٌ يصعد بوتيرةٍ
    # متناقصة يقترب من قمّته لا من انطلاقه.
    diffs = hist.diff().dropna()
    accel = None
    if len(diffs) >= bars * 2:
        recent = float(diffs.iloc[-bars:].mean())
        before = float(diffs.iloc[-bars * 2:-bars].mean())
        if np.isfinite(recent) and np.isfinite(before):
            accel = recent - before

    n_rise = int(_cfg(params, "macd", "rising_bars", default=3))
    tail = [_f(x) for x in hist.iloc[-(n_rise + 1):]]
    rising = (len(tail) == n_rise + 1 and all(x is not None for x in tail)
              and all(tail[i] < tail[i + 1] for i in range(n_rise)))

    # صعودٌ «واضح»: الميل نسبةً إلى مدى المدرَّج، لا رقمٌ مطلق —
    # فالمدرَّج بوحدة السعر، وعتبةٌ ثابتة تصلح لرمزٍ وتخطئ في آخر
    span = float(hist.iloc[-60:].abs().max() or 0.0)
    rel_slope = (sl / span) if span > 0 else 0.0
    strong = rel_slope >= float(_cfg(params, "macd", "strong_slope",
                                     default=0.10))

    l_now, s_now = _f(line.iloc[-1]), _f(sig.iloc[-1])
    l_prev, s_prev = _f(line.iloc[-2]), _f(sig.iloc[-2])
    cross_up = (None not in (l_now, s_now, l_prev, s_prev)
                and l_prev <= s_prev and l_now > s_now)
    above_signal = None not in (l_now, s_now) and l_now > s_now
    zero_cross_up = prev <= 0 < cur

    return {
        "ok": True, "hist": cur, "hist_prev": prev,
        "slope": sl, "rel_slope": round(rel_slope, 4), "accel": accel,
        "rising": bool(rising), "strong_rising": bool(rising and strong),
        "above_zero": cur > 0,
        "cross_up": bool(cross_up), "zero_cross_up": bool(zero_cross_up),
        "above_signal": bool(above_signal),
        # التحسّن قبل التقاطع: المدرَّج سالبٌ وصاعد — أنفع حالاته
        "early_turn": bool(rising and cur < 0),
        "line": l_now, "signal": s_now,
    }


# ═══════════════════ ٢) قياس StochRSI ═══════════════════

def stoch_reading(df: pd.DataFrame, params: dict | None = None) -> dict:
    """التوقيت: تقاطعٌ صاعد قادمٌ من منطقةٍ منخفضة أو وسطى.

    ═══ ولماذا يُشترط «من أين جاء» ═══

    تقاطعٌ عند ٨٥ ليس بدايةَ دورة بل نهايتَها. والمؤشّر يعبر
    خطّه عشرات المرّات شهرياً، فالتقاطع وحده بلا موضعٍ ولا تاريخ
    ضجيجٌ لا إشارة.
    """
    from scanner.indicators.momentum import stoch_rsi

    d = _closed(df)
    if d is None or len(d) < 60:
        return {"ok": False, "why": "شموع غير كافية"}

    f = stoch_rsi(d["close"].astype(float),
                  int(_cfg(params, "stoch_rsi", "rsi_length", default=14)),
                  int(_cfg(params, "stoch_rsi", "stoch_length", default=14)),
                  int(_cfg(params, "stoch_rsi", "k", default=3)),
                  int(_cfg(params, "stoch_rsi", "d", default=3)))

    k_now, d_now = _f(f["k"].iloc[-1]), _f(f["d"].iloc[-1])
    k_prev, d_prev = _f(f["k"].iloc[-2]), _f(f["d"].iloc[-2])
    if None in (k_now, d_now, k_prev, d_prev):
        return {"ok": False, "why": "غير محسوب بعد"}

    low = float(_cfg(params, "stoch_rsi", "low_zone", default=30.0))
    high = float(_cfg(params, "stoch_rsi", "high_zone", default=80.0))
    late = float(_cfg(params, "stoch_rsi", "late_level", default=90.0))
    back = int(_cfg(params, "stoch_rsi", "from_low_bars", default=8))
    max_ob = int(_cfg(params, "stoch_rsi", "max_overbought_bars", default=6))

    cross_up = k_prev <= d_prev and k_now > d_now
    window = [x for x in (_f(v) for v in f["k"].iloc[-back:]) if x is not None]
    from_low = bool(window) and min(window) <= low
    # ═══ التشبّع المزمن يُبطل التوقيت ═══
    #
    # مؤشّرٌ بقي فوق ٨٠ ستّ شمعات ليس «بداية دورة». والتقاطع
    # داخل التشبّع تذبذبٌ في القمّة.
    ob_bars = sum(1 for x in window if x >= high)
    stale = ob_bars > max_ob

    zone = ("overbought" if k_now >= high else
            "oversold" if k_now <= low else "middle")

    return {
        "ok": True, "k": round(k_now, 1), "d": round(d_now, 1),
        "cross_up": bool(cross_up), "k_above_d": k_now > d_now,
        "from_low": from_low, "zone": zone,
        "overbought_bars": ob_bars, "stale_overbought": stale,
        "very_high": k_now >= late,
        # التوقيت الصالح: تقاطعٌ صاعد، من منطقةٍ ليست مرتفعة، وبلا
        # تشبّعٍ مزمن
        "timing": bool(cross_up and not stale and k_now < high),
    }


# ═══════════════════ ٣) السلّم ═══════════════════

def evaluate_confluence(macd_r: dict, stoch_r: dict, rsi_ok: bool = False,
                        external_confirm: bool = False) -> dict:
    """درجةٌ من عشر — مراتب لا مجموع.

    ``external_confirm`` هو تأكيد الاتجاه والحجم والانضغاط. ولا
    يُستعمل إلّا في المرتبة العاشرة، ونقطةً واحدة: تلك العوامل
    محسوبةٌ في عائلاتها، وإعادةُ وزنها هنا عدٌّ مزدوج. ونقطةٌ من
    مئة حدُّ ما نقبله منه.
    """
    if not macd_r.get("ok"):
        return {"score": 0.0, "tier": 0, "label": "MACD غير محسوب",
                "reasons": [macd_r.get("why", "—")], "usable": False}

    rising = macd_r.get("rising")
    improving = macd_r.get("hist", 0) > macd_r.get("hist_prev", 0)
    timing = bool(stoch_r.get("ok") and stoch_r.get("timing"))
    from_low = bool(stoch_r.get("ok") and stoch_r.get("from_low"))
    macd_bull = bool(macd_r.get("above_signal") or macd_r.get("cross_up")
                     or macd_r.get("zero_cross_up"))

    reasons: list[str] = []
    score = 0.0

    if not rising and not improving:
        # ٠–٢: المدرَّج هابط أو مسطّح
        score = 2.0 if improving else 0.0
        reasons.append("المدرَّج لا يتحسّن")
    elif rising and timing and from_low and macd_bull:
        score = 9.0
        reasons += ["المدرَّج صاعد", "تقاطع StochRSI صاعد",
                    "قادمٌ من منطقةٍ منخفضة", "MACD فوق إشارته"]
        if external_confirm and macd_r.get("strong_rising"):
            score = 10.0
            reasons.append("والاتجاه والحجم والانضغاط تؤكّد")
    elif rising and timing:
        # ٧–٨: التوقيت حاضر لكن بلا خروجٍ من منطقةٍ منخفضة
        score = 8.0 if macd_bull else 7.0
        reasons += ["المدرَّج صاعد", "تقاطع StochRSI صاعد"]
        if not from_low:
            reasons.append("لكنّه لم يأتِ من منطقةٍ منخفضة")
    elif rising:
        # ٥–٦: تأكيدٌ بلا توقيت — وهذا سقفُ MACD وحده
        score = 6.0 if rsi_ok else 5.0
        reasons.append("المدرَّج صاعد")
        reasons.append("و RSI داعم" if rsi_ok else "بلا دعمٍ من RSI")
        if stoch_r.get("ok") and not timing:
            reasons.append("ولا تقاطع StochRSI بعد — التوقيت لم يحن")
    else:
        # ٣–٤: بداية تحسّن، شمعةٌ واحدة لا اتجاه
        score = 4.0 if macd_r.get("early_turn") else 3.0
        reasons.append("المدرَّج بدأ يتحسّن")

    # التشبّع المزمن يخصم: التقاطع داخله تذبذبٌ في القمّة
    if stoch_r.get("ok") and stoch_r.get("stale_overbought") and score > 4:
        score = 4.0
        reasons.append("لكنّ StochRSI متشبّعٌ منذ شمعاتٍ — ليس بداية")

    tier = max(k for k in TIER_LABELS if k <= int(score))
    return {"score": round(score, 1), "tier": tier,
            "label": TIER_LABELS[tier], "reasons": reasons,
            "usable": True,
            "macd_rising": bool(rising), "stoch_timing": timing,
            "from_low": from_low}


# ═══════════════════ ٤) الواجهة ═══════════════════

def measure(frames: dict, params: dict | None = None,
            *, rsi_ok: bool = False, external_confirm: bool = False) -> dict:
    """يقيس على الأطر الثلاثة ويعيد درجةً واحدة وتفصيلها.

    ═══ توزيع الأدوار على الأطر (المادّة ١٠) ═══

        ‎4h‎   ‏MACD — الزخم الرئيسي داعم
        ‎1h‎   ‏MACD — التحسّن أقرب
        ‎15m‎  ‏StochRSI — لحظة الدخول

    والإطار الغائب **لا يُعاقَب**: رمزٌ لم يُزامَن فريمه بعد ليس
    رمزاً سيّئاً. فيرتدّ القياس إلى ‎4h‎ ويُعلَن ذلك في التفصيل —
    وصفرٌ صامت لغيابِ بيانات يُقرأ «ضعيف» وهو «مجهول».
    """
    h4 = frames.get("4h")
    h1 = frames.get("1h")
    m15 = frames.get("15m")

    macd_h4 = macd_reading(h4, params)
    macd_h1 = macd_reading(h1, params) if h1 is not None else {
        "ok": False, "why": "فريم 1h غير متاح"}
    # التوقيت من ‎15m‎ إن وُجد، وإلّا من ‎4h‎ — أخشن لكنّه ليس فراغاً
    stoch_src = "15m" if m15 is not None else "4h"
    stoch = stoch_reading(m15 if m15 is not None else h4, params)

    conf = evaluate_confluence(macd_h4, stoch, rsi_ok=rsi_ok,
                               external_confirm=external_confirm)

    # ═══ ‎1h‎ يرفع درجةً واحدة لا أكثر ═══
    #
    # هو الإطار نفسه والمؤشّر نفسه على مقياسٍ أدقّ — تأكيدٌ لا
    # شاهدٌ جديد. ومنحُه وزناً كاملاً يجعل MACD يُحسب مرّتين.
    h1_supports = bool(macd_h1.get("ok")
                       and (macd_h1.get("rising") or macd_h1.get("cross_up")))
    if h1_supports and conf["usable"] and 4 < conf["score"] < 9:
        conf["score"] = round(min(9.0, conf["score"] + 1.0), 1)
        conf["reasons"].append("و‎1h‎ يؤكّد")

    conf["timeframes"] = {
        "4h": {"macd": macd_h4.get("ok", False),
               "rising": macd_h4.get("rising", False)},
        "1h": {"available": h1 is not None, "supports": h1_supports,
               "why": macd_h1.get("why", "")},
        "15m": {"available": m15 is not None, "used_for_timing": stoch_src},
    }
    conf["macd"] = macd_h4
    conf["stoch_rsi"] = stoch
    conf["timing_source"] = stoch_src
    return conf


def is_late(frames: dict, macd_r: dict, stoch_r: dict,
            params: dict | None = None) -> dict:
    """زخمٌ قويّ + ‏StochRSI مرتفع جدّاً + ارتفاعٌ تحقّق = متأخّر.

    وهذه ليست ضعفاً في الرمز بل خطأً في التوقيت: الحركة التي
    نبحث عن **بدايتها** جرت. والدخول هنا مطاردة.
    """
    if not (macd_r.get("ok") and stoch_r.get("ok")):
        return {"late": False, "why": "غير محسوب"}

    h4 = _closed(frames.get("4h"))
    look = int(_cfg(params, "late", "lookback_bars", default=30))
    need = float(_cfg(params, "late", "min_gain_pct", default=15.0))
    gain = None
    if h4 is not None and len(h4) > look:
        close = h4["close"].astype(float)
        base = float(close.iloc[-look])
        if base > 0:
            gain = (float(close.iloc[-1]) - base) / base * 100.0

    strong = bool(macd_r.get("above_signal") and macd_r.get("above_zero"))
    very_high = bool(stoch_r.get("very_high"))
    moved = gain is not None and gain >= need

    late = strong and very_high and moved
    why = ""
    if late:
        why = (f"‏StochRSI {stoch_r.get('k')} و MACD قويّ، والسعر "
               f"{gain:+.1f}٪ خلال {look} شمعة — الحركة بدأت")
    return {"late": late, "gain_pct": None if gain is None else round(gain, 1),
            "why": why}
