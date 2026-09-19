# -*- coding: utf-8 -*-
"""Pre-Explosion Strategy (PES) — التقاط بداية التمدّد قبل حدوثه.

═══ الفكرة ═══

الدورة المقصودة::

    تجميع → انضغاط → تمدّد حجم → تحسّن زخم
          → قرب مقاومة → اختراق → إعادة اختبار → تمدّد

والهدف الإمساك بالمرحلة الثالثة والرابعة، لا الجري خلف السابعة.

═══ والقاعدة التي تحكم كل شيء (المادّة ١٧) ═══

كثرةُ المؤشّرات ليست دليلاً أقوى. و‏EMA و Supertrend و ADX ثلاثتها
تقيس **الاتجاه** — فاجتماعها ليس ثلاث إشارات بل إشارةٌ واحدة
بثلاثة أسماء. وهذا هو العطب نفسه الذي وقع في وحدة الأدلّة سابقاً:
ثلاثة «أسباب» بأرقامٍ متطابقة كانت الصفقات الثمانية عشر نفسها.

فالإشارات هنا مقسّمة إلى ستّ عائلات، والنقاط تُجمع لكن **التنوّع
يُقاس ويُشترط**: لا يُصنَّف رمزٌ ‏PRE-BREAKOUT إلّا إن جاءت نقاطه
من ثلاث عائلات فأكثر.

═══ وما لا تدّعيه ═══

لا تتنبّأ بأنّ العملة ستصير ×٥. ولا تعطي احتمالاً — النقاط ترتيبٌ
لا نسبة. ومن أراد احتمالاً مقيساً فـ ``tools_pes_measure.py``
يقيس: هل النقاط الأعلى تسبق تمدّداً أكثر فعلاً؟

═══ ومنع النظر إلى المستقبل ═══

كل حسابٍ هنا ينتهي عند الشمعة الأخيرة **المغلقة**. والشمعة الجارية
تُستبعد: قيمها تتغيّر حتى تُغلق، وبناء قرارٍ عليها يجعل الاختبار
الخلفي ممتازاً والتطبيق عاجزاً.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger("scanner.strategies.pes")

# ═══ العائلات ═══
#
# كل عامل ينتمي إلى عائلةٍ واحدة. والتنوّع يُقاس عليها.
FAMILY = {
    "btc_regime": "context",
    "daily_trend": "trend",
    "h4_trend": "trend",
    "adx": "trend",
    # ‏Supertrend اتجاهٌ كغيره — وعائلته تمنعه من التصويت مرّتين
    # مع ‏EMA و‏ADX مهما بلغ وزنه.
    "supertrend": "trend",
    "compression": "volatility",
    "volume": "volume",
    "obv": "volume",
    "rsi": "momentum",
    # ‏MACD و StochRSI معاً في عاملٍ واحد. وفصلُهما عاملين يجعل
    # عائلة الزخم تصوّت مرّتين بمقياسٍ واحد — وهو العطب الذي
    # تحرسه المادّة ١٧ نفسها.
    "momentum_confluence": "momentum",
    "macd": "momentum",          # يبقى للتوافق مع نتائج مخزّنة
    "divergence": "momentum",
    "resistance": "price_action",
}

FAMILY_LABELS = {
    "trend": "الاتجاه", "momentum": "الزخم", "volatility": "التقلّب",
    "volume": "الحجم", "price_action": "حركة السعر", "context": "سياق السوق",
}

# الترتيب من الأضعف إلى الأقوى — وحالتا الرفض في أوّله.
#
# ‏LATE_MOMENTUM ليست ضعفاً في الرمز بل خطأً في التوقيت: الحركة
# التي نبحث عن **بدايتها** جرت. وفصلُها عن ALREADY_EXPANDED مقصود:
# تلك ارتفاعٌ صِرف، وهذه زخمٌ قويّ مع StochRSI في القمّة.
STATES = ("ALREADY_EXPANDED", "LATE_MOMENTUM", "NONE", "WATCH",
          "EARLY_MOMENTUM", "PRE_BREAKOUT", "STRONG_PRE_BREAKOUT",
          "BREAKOUT", "BREAKOUT_RETEST", "ENTRY_READY")

STATE_LABELS = {
    "ALREADY_EXPANDED": "انفجرت بالفعل",
    "LATE_MOMENTUM": "زخم متأخّر — لا تطارد",
    "NONE": "لا إشارة",
    "WATCH": "للمراقبة",
    "EARLY_MOMENTUM": "إنذار مبكّر — الزخم تحوّل",
    "PRE_BREAKOUT": "قبل الاختراق",
    "STRONG_PRE_BREAKOUT": "قبل الاختراق — قويّة",
    "BREAKOUT": "اختراق",
    "BREAKOUT_RETEST": "إعادة اختبار",
    "ENTRY_READY": "جاهزة للدخول",
}

# ما لا يُدخَل منه — لا الآن ولا بعد اختراق
NON_ENTRY_STATES = ("ALREADY_EXPANDED", "LATE_MOMENTUM", "NONE", "WATCH",
                    "EARLY_MOMENTUM")

_params_cache: dict[str, Any] = {}


def load_params(path: str | Path | None = None) -> dict:
    """يقرأ ‏config/pes.yaml — وكل حدٍّ فيه قابل للتعديل."""
    import yaml

    p = Path(path) if path else (Path(__file__).resolve().parents[2]
                                 / "config" / "pes.yaml")
    key = str(p)
    stat = p.stat() if p.exists() else None
    stamp = (stat.st_mtime_ns, stat.st_size) if stat else None
    # ‏mtime+size لا الزمن: الملفّ يُحرَّر أثناء التشغيل، وذاكرةٌ
    # زمنية تُبقي القيم القديمة سارية بلا سبب ظاهر.
    if _params_cache.get("key") == key and _params_cache.get("stamp") == stamp:
        return _params_cache["data"]
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    _params_cache.update(key=key, stamp=stamp, data=data or {})
    return _params_cache["data"]


def _closed(df: pd.DataFrame) -> pd.DataFrame:
    """يُسقط الشمعة الجارية — القرار على المغلق وحده."""
    return df.iloc[:-1] if df is not None and len(df) > 1 else df


def _tier(value: float, tiers: list, *, ascending: bool = True) -> float:
    """يحوّل قيمةً إلى نقاط بجدول عتبات ``[[حدّ, نقاط], …]``."""
    for edge, pts in tiers:
        if (value <= edge) if ascending else (value >= edge):
            return float(pts)
    return 0.0


# ═══════════════════════ ١) نظام BTC ═══════════════════════

def btc_regime(df_1d: pd.DataFrame) -> dict:
    """حالة السوق من عشرة — وهي سقفٌ لثقة إشارات الشراء.

    السوق الهابط لا يمنع الإشارة بل يخفض ثقتها بشدّة: عملةٌ ممتازة
    في سوقٍ ينزف تتحرّك مع السوق لا معك.
    """
    from scanner.indicators.pine import ema, rsi

    df = _closed(df_1d)
    if df is None or len(df) < 210:
        return {"score": 0, "label": "غير معروف", "parts": [],
                "usable": False}

    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    e20, e50, e200 = ema(close, 20), ema(close, 50), ema(close, 200)
    r = rsi(close, 14)
    c = float(close.iloc[-1])

    parts: list[dict] = []

    def add(name: str, ok: bool, pts: int, detail: str = "") -> None:
        parts.append({"name": name, "ok": bool(ok),
                      "points": pts if ok else 0, "max": pts,
                      "detail": detail})

    add("السعر فوق EMA20", c > float(e20.iloc[-1]), 2,
        f"{c:.0f} مقابل {float(e20.iloc[-1]):.0f}")
    add("EMA20 فوق EMA50", float(e20.iloc[-1]) > float(e50.iloc[-1]), 2)
    add("السعر فوق EMA200", c > float(e200.iloc[-1]), 2)

    # قمم وقيعان أعلى على آخر عشرين شمعة مقابل التي قبلها
    hi_now, hi_prev = close.iloc[-20:].max(), close.iloc[-40:-20].max()
    lo_now, lo_prev = close.iloc[-20:].min(), close.iloc[-40:-20].min()
    add("قمم وقيعان أعلى", hi_now > hi_prev and lo_now > lo_prev, 2)

    add("الحجم فوق متوسّط 20", float(vol.iloc[-1]) >
        float(vol.rolling(20).mean().iloc[-1]), 1)
    rv = float(r.iloc[-1])
    add("RSI بين 50 و70", 50 <= rv <= 70, 1, f"{rv:.0f}")

    score = sum(p["points"] for p in parts)
    label = "صاعد" if score >= 7 else ("محايد" if score >= 5 else "هابط")
    return {"score": score, "label": label, "parts": parts, "usable": True}


# ═══════════════════════ ٢) العوامل ═══════════════════════

def _f_daily_trend(d1: pd.DataFrame, w: float, p: dict) -> dict:
    from scanner.indicators.pine import ema, rsi

    df = _closed(d1)
    if df is None or len(df) < 60:
        return _na("daily_trend", w, "شموع يومية غير كافية")
    close = df["close"].astype(float)
    e20, e50 = ema(close, 20), ema(close, 50)
    c = float(close.iloc[-1])
    r = float(rsi(close, 14).iloc[-1])
    ext = (c - float(e20.iloc[-1])) / float(e20.iloc[-1]) * 100

    # ═══ ‏Supertrend خرج من هنا ═══
    #
    # كان فحصاً بوزن ٠٫٢٥ داخل هذا العامل. وصار عاملاً مستقلّاً
    # له عموده على الشاشة — فبقاؤه هنا عدٌّ مزدوج للشيء نفسه.
    # والحصص أُعيد ضبطها لتجمع واحداً بلا نقصان.
    checks = [
        ("السعر فوق EMA50", c > float(e50.iloc[-1]), 0.40),
        ("EMA20 فوق EMA50", float(e20.iloc[-1]) > float(e50.iloc[-1]), 0.30),
        ("RSI بين 50 و68", 50 <= r <= 68, 0.15),
        # ═══ الابتعاد يخصم ═══
        # سعرٌ ابتعد عن متوسّطه ارتفع بالفعل — وهذا ليس «ما قبل».
        ("قريب من EMA20",
         ext <= float((p.get("anti_chasing") or {}).get(
             "max_ext_above_ema20", 12.0)), 0.15),
    ]
    got = sum(w * frac for _, ok, frac in checks if ok)
    return {"key": "daily_trend", "family": FAMILY["daily_trend"],
            "points": round(got, 2), "max": w,
            "detail": f"RSI {r:.0f} · بُعد عن EMA20 {ext:+.1f}٪",
            "checks": [{"name": n, "ok": bool(o)} for n, o, _ in checks]}


def _f_supertrend(frames: dict, w: float, p: dict) -> dict:
    """‏Supertrend على فريم المسح واليوميّ — والوزن للتوقيت لا للاتجاه.

    ═══ ما الذي يضيفه فعلاً (المادّة ١٧) ═══

    «صاعد» يقولها ‏EMA و‏ADX أيضاً، فلا تُشترى مرّتين. فأكثر الوزن
    هنا على ما **لا** يقولانه:

        ٠٫٢٥  اتجاه فريم المسح صاعد        ← مشترَك، فحصّته صغيرة
        ٠٫٢٠  واليوميّ يوافقه               ← اتّفاق الفريمين
        ٠٫٣٥  الانقلاب حديث (≤ ٨ شموع)     ← توقيتٌ لا يعطيه غيره
        ٠٫٢٠  السعر قريب من الخطّ           ← كلفة الوقف

    والمرحلة المقصودة «ما قبل الانفجار»: اتجاهٌ **بدأ للتوّ**.
    واتجاهٌ عمره أربعون شمعة صاعدٌ صحيح — والدخول فيه مطاردة.

    وعائلته ``trend``، ووزنه اقتُطع من ``daily_trend`` و‏``h4_trend``
    فمجموع العائلة لم يتغيّر: رفعُه كان سيجعل الاتجاه يصوّت أكثر،
    وهو ما تمنعه القاعدة ١٧ نفسها.
    """
    from scanner.indicators.trend import supertrend_state

    cfg = p.get("supertrend") or {}
    length = int(cfg.get("length", 10))
    mult = float(cfg.get("multiplier", 3.0))
    fresh_max = int(cfg.get("fresh_flip_bars", 8))
    near_pct = float(cfg.get("near_line_pct", 6.0))

    # ═══ فريم المسح هو الأصل ═══
    #
    # الشاشة تعرض ‎4h‎ افتراضاً، والعامل يجب أن يوافق ما يراه
    # المستخدم. وإلّا قرأ «Supertrend صاعد» في عمودٍ يقيس اليوميّ
    # بينما شارتُه يقول غير ذلك.
    scan_tf = "4h" if frames.get("4h") is not None else "1d"
    st = supertrend_state(frames.get(scan_tf), length, mult)
    if not st["usable"]:
        return _na("supertrend", w, "شموع غير كافية لـ Supertrend")

    st_d = supertrend_state(frames.get("1d"), length, mult)
    bars = st["bars_since_flip"]
    dist = st["distance_pct"]

    up = st["direction"] > 0
    checks = [
        (f"اتجاه {scan_tf} صاعد", up, 0.25),
        ("واليوميّ يوافقه", up and st_d["usable"] and st_d["direction"] > 0,
         0.20),
        (f"انقلابٌ حديث (≤{fresh_max} شمعة)",
         up and bars is not None and bars <= fresh_max, 0.35),
        (f"السعر قريب من الخطّ (≤{near_pct:.0f}٪)",
         up and dist is not None and 0 <= dist <= near_pct, 0.20),
    ]
    got = sum(w * frac for _, ok, frac in checks if ok)

    label = ("صاعد" if up else "هابط")
    age = "—" if bars is None else f"{bars} شمعة"
    return {"key": "supertrend", "family": FAMILY["supertrend"],
            "points": round(got, 2), "max": w,
            "detail": f"{scan_tf} {label} · منذ {age}"
                      + ("" if dist is None else f" · بعدٌ {dist:+.1f}٪"),
            "supertrend": {
                "timeframe": scan_tf,
                "direction": st["direction"],
                "line": st["line"],
                "bars_since_flip": bars,
                "distance_pct": dist,
                "flipped_up": st["flipped_up"],
                "daily_direction": st_d["direction"] if st_d["usable"] else 0,
            },
            "checks": [{"name": n, "ok": bool(o)} for n, o, _ in checks]}


def _f_h4_trend(h4: pd.DataFrame, w: float, p: dict) -> dict:
    """الاتجاه صاعد **مع** تماسك — أهمّ منطقة في الاستراتيجية."""
    from scanner.indicators.pine import ema

    df = _closed(h4)
    if df is None or len(df) < 60:
        return _na("h4_trend", w, "شموع 4H غير كافية")
    close = df["close"].astype(float)
    e20, e50 = ema(close, 20), ema(close, 50)
    c = float(close.iloc[-1])
    win = close.iloc[-20:]
    rng = float((win.max() - win.min()) / win.mean() * 100)

    up = c > float(e50.iloc[-1]) and float(e20.iloc[-1]) > float(e50.iloc[-1])
    tight = rng <= 12.0
    checks = [
        ("الاتجاه صاعد", up, 0.5),
        ("نطاق ضيّق", tight, 0.5),
    ]
    got = sum(w * frac for _, ok, frac in checks if ok)
    return {"key": "h4_trend", "family": FAMILY["h4_trend"],
            "points": round(got, 2), "max": w,
            "detail": f"نطاق 20 شمعة {rng:.1f}٪",
            "checks": [{"name": n, "ok": bool(o)} for n, o, _ in checks]}


def _f_compression(h4: pd.DataFrame, w: float, p: dict) -> dict:
    from scanner.indicators.squeeze import bb_width

    cfg = p.get("compression") or {}
    df = _closed(h4)
    look = int(cfg.get("lookback", 100))
    if df is None or len(df) < look + 25:
        return _na("compression", w, "شموع غير كافية للانضغاط")
    bw = bb_width(df, int(cfg.get("bands_length", 20))).dropna()
    if len(bw) < look:
        return _na("compression", w, "عرض القناة غير محسوب")
    window = bw.iloc[-look:]
    cur = float(window.iloc[-1])
    pct = float((window.iloc[:-1] < cur).mean() * 100)
    raw = _tier(pct, cfg.get("tiers") or [[10, 15], [20, 12], [30, 9],
                                          [40, 5]])
    # الأوزان قابلة للتعديل، والجدول مكتوبٌ لسقف 15 — فيُقاس عليه
    got = raw * (w / 15.0)
    return {"key": "compression", "family": FAMILY["compression"],
            "points": round(got, 2), "max": w,
            "detail": f"عرض القناة في المئين {pct:.0f}"}


def _f_volume(h4: pd.DataFrame, w: float, p: dict) -> dict:
    cfg = p.get("volume") or {}
    df = _closed(h4)
    n = int(cfg.get("sma_length", 20))
    if df is None or len(df) < n + 5:
        return _na("volume", w, "شموع غير كافية")
    vol = df["volume"].astype(float)
    avg = float(vol.rolling(n).mean().iloc[-1])
    rvol = float(vol.iloc[-1]) / avg if avg > 0 else 0.0
    raw = _tier(rvol, cfg.get("tiers") or [[1.0, 0], [1.3, 3], [1.5, 7],
                                           [2.0, 11], [999, 15]])
    close = df["close"].astype(float)
    chg = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(close) > 1 else 0

    # ═══ حجمٌ هائل مع قفزة سعر ═══
    #
    # ليست تجميعاً بل انفجاراً وقع. والنقاط تُصفَّر لا تُرفع.
    exploded = (rvol >= float(cfg.get("explosive_rvol", 3.0)) and chg > 5)
    if exploded:
        raw = 0.0
    got = raw * (w / 15.0)
    return {"key": "volume", "family": FAMILY["volume"],
            "points": round(got, 2), "max": w,
            "detail": f"RVOL {rvol:.2f}" + (" — انفجر بالفعل" if exploded
                                            else "")}


def _f_obv(h4: pd.DataFrame, w: float, p: dict) -> dict:
    """‏OBV يصعد والسعر ثابت — تجميعٌ قبل التمدّد."""
    from scanner.indicators.trend import slope
    from scanner.indicators.volume import obv

    cfg = p.get("obv") or {}
    df = _closed(h4)
    win = int(cfg.get("window", 20))
    if df is None or len(df) < win + 5:
        return _na("obv", w, "شموع غير كافية")
    o = obv(df)
    sl = slope(o, win)
    close = df["close"].astype(float).iloc[-win:]
    rng = float((close.max() - close.min()) / close.mean() * 100)
    flat = rng <= float(cfg.get("max_price_range_pct", 8.0))

    if sl > 0 and flat:
        got = w                      # التجميع الكلاسيكي
    elif sl > 0:
        got = w * 0.5                # يصعد لكنّ السعر تحرّك معه
    else:
        got = 0.0
    return {"key": "obv", "family": FAMILY["obv"],
            "points": round(got, 2), "max": w,
            "detail": f"ميل OBV {sl:+.4f} · نطاق السعر {rng:.1f}٪"}


def _f_resistance(h4: pd.DataFrame, w: float, p: dict) -> dict:
    from scanner.indicators.pine import pivot_high

    cfg = p.get("resistance") or {}
    df = _closed(h4)
    look = int(cfg.get("lookback", 60))
    if df is None or len(df) < look + 10:
        return _na("resistance", w, "شموع غير كافية")
    ph = pivot_high(df["high"].astype(float), int(cfg.get("pivot_left", 5)),
                    int(cfg.get("pivot_right", 5)))
    levels = ph.dropna().iloc[-look:]
    c = float(df["close"].astype(float).iloc[-1])
    above = [float(v) for v in levels if float(v) > c]
    if not above:
        return {"key": "resistance", "family": FAMILY["resistance"],
                "points": 0.0, "max": w,
                "detail": "لا مقاومة فوق السعر — اخترقها بالفعل",
                "distance": None, "level": None}
    lvl = min(above)
    dist = (lvl - c) / c * 100
    raw = _tier(dist, cfg.get("tiers") or [[1.0, 10], [3.0, 9], [5.0, 6],
                                           [7.0, 3]])
    got = raw * (w / 10.0)
    return {"key": "resistance", "family": FAMILY["resistance"],
            "points": round(got, 2), "max": w,
            "detail": f"المقاومة {lvl:.6g} على بعد {dist:.1f}٪",
            "distance": round(dist, 2), "level": lvl}


def _f_adx(h4: pd.DataFrame, w: float, p: dict) -> dict:
    """‏ADX صاعد لا مرتفع: ‎18→26‎ يبدأ، و‎42→47‎ نضج."""
    from scanner.indicators.trend import adx, slope

    cfg = p.get("adx") or {}
    df = _closed(h4)
    if df is None or len(df) < 40:
        return _na("adx", w, "شموع غير كافية")
    a = adx(df, int(cfg.get("length", 14)))["adx"]
    cur = float(a.iloc[-1])
    sl = slope(a, 5)
    lo, hi = float(cfg.get("min_value", 15)), float(cfg.get("max_value", 40))

    got = 0.0
    if lo <= cur <= hi:
        got += w * 0.5
    if sl > 0:
        got += w * 0.5
    if cur > hi:
        got = 0.0                    # الحركة نضجت
    return {"key": "adx", "family": FAMILY["adx"],
            "points": round(got, 2), "max": w,
            "detail": f"ADX {cur:.0f} · الميل {sl:+.4f}"}


def _f_rsi(h4: pd.DataFrame, w: float, p: dict) -> dict:
    from scanner.indicators.pine import rsi
    from scanner.indicators.trend import slope

    cfg = p.get("rsi") or {}
    df = _closed(h4)
    if df is None or len(df) < 30:
        return _na("rsi", w, "شموع غير كافية")
    r = rsi(df["close"].astype(float), int(cfg.get("length", 14)))
    cur = float(r.iloc[-1])
    sl = slope(r, 5)
    lo = float(cfg.get("ideal_low", 50))
    hi = float(cfg.get("ideal_high", 65))
    ob = float(cfg.get("overbought", 75))

    got = 0.0
    if lo <= cur <= hi:
        got += w * 0.6
    if sl > 0:
        got += w * 0.4
    if cur > ob:
        got = 0.0                    # ليست «ما قبل» بل «أثناء»
    return {"key": "rsi", "family": FAMILY["rsi"],
            "points": round(got, 2), "max": w,
            "detail": f"RSI {cur:.0f} · الميل {sl:+.4f}"}


def _f_macd(h4: pd.DataFrame, w: float, p: dict) -> dict:
    """المدرَّج الصاعد يسبق التقاطع — والتقاطع متأخّر."""
    from scanner.indicators.trend import macd, slope

    df = _closed(h4)
    if df is None or len(df) < 40:
        return _na("macd", w, "شموع غير كافية")
    m = macd(df["close"].astype(float))
    h = m["hist"]
    sl = slope(h, 5)
    cur = float(h.iloc[-1])
    got = 0.0
    if sl > 0:
        got += w * 0.7
    # من سالبٍ نحو الصفر: أنفع من موجبٍ يتوسّع
    if sl > 0 and cur < 0:
        got += w * 0.3
    elif cur > 0:
        got += w * 0.15
    return {"key": "macd", "family": FAMILY["macd"],
            "points": round(min(got, w), 2), "max": w,
            "detail": f"المدرَّج {cur:+.4g} · الميل {sl:+.4f}"}


def _f_momentum_confluence(frames: dict, w: float, p: dict, *,
                           rsi_ok: bool = False,
                           external_confirm: bool = False) -> dict:
    """‏MACD يؤكّد التحوّل، و‏StochRSI يحدّد لحظته — درجةٌ واحدة.

    ═══ لماذا عاملٌ واحد لا عاملان ═══

    كلاهما مؤشّر زخم. ومقياسان لشيءٍ واحد ليسا شاهدين مستقلّين بل
    شاهداً واحداً بصوتين. فلو فُصلا عاملين لصوّتت عائلة الزخم
    مرّتين بالمقياس نفسه — وهو العطب الذي تحرسه المادّة ١٧.

    ووزنُه مأخوذ من ميزانية العائلة لا مضافٌ إليها: كان
    ``rsi 5 + macd 5 + divergence 5``، وصار
    ``confluence 10 + rsi 3 + divergence 2``. المجموع ١٥ كما كان.
    """
    from . import momentum_confluence as mc

    h4 = frames.get("4h")
    if h4 is None or len(h4) < 60:
        return _na("momentum_confluence", w, "شموع 4H غير كافية")

    res = mc.measure(frames, p, rsi_ok=rsi_ok,
                     external_confirm=external_confirm)
    if not res.get("usable"):
        return _na("momentum_confluence", w,
                   (res.get("reasons") or ["غير محسوب"])[0])

    # الدرجة من عشر → النقاط من الوزن
    got = float(w) * (res["score"] / 10.0)
    return {"key": "momentum_confluence",
            "family": FAMILY["momentum_confluence"],
            "points": round(got, 2), "max": w,
            "detail": f"{res['score']}/10 · {res['label']}",
            "confluence": res}


def _f_divergence(h4: pd.DataFrame, w: float, p: dict) -> dict:
    """دايفرجنس صاعد: قاعٌ أدنى في السعر وقاعٌ أعلى في RSI.

    ولا تُطلِق دخولاً وحدها — هي نقاطٌ إضافية لا شرط.
    """
    from scanner.indicators.pine import rsi

    df = _closed(h4)
    if df is None or len(df) < 40:
        return _na("divergence", w, "شموع غير كافية")
    close = df["close"].astype(float)
    r = rsi(close, 14)
    a, b = close.iloc[-20:-10], close.iloc[-10:]
    ra, rb = r.iloc[-20:-10], r.iloc[-10:]
    if a.empty or b.empty:
        return _na("divergence", w, "نافذة غير كافية")
    price_lower = float(b.min()) < float(a.min())
    rsi_higher = float(rb.min()) > float(ra.min())
    ok = price_lower and rsi_higher
    return {"key": "divergence", "family": FAMILY["divergence"],
            "points": float(w) if ok else 0.0, "max": w,
            "detail": "دايفرجنس صاعد" if ok else "لا دايفرجنس"}


def _na(key: str, w: float, why: str) -> dict:
    """عاملٌ تعذّر حسابه — صفرٌ معلَّل لا صفرٌ صامت."""
    return {"key": key, "family": FAMILY.get(key, "?"), "points": 0.0,
            "max": w, "detail": why, "unavailable": True}


# ═══════════════════════ ٣) مانع المطاردة ═══════════════════════

def already_expanded(d1: pd.DataFrame, h4: pd.DataFrame, p: dict) -> dict:
    """هل ارتفعت بالفعل؟ — فلا تُسمّى «ما قبل الانفجار».

    الفحص قبل كل شيء: عملةٌ ارتفعت ٣٠٪ أمس ليست فرصةً مبكّرة مهما
    بلغت نقاطها، وتصنيفُها كذلك هو مطاردةٌ باسمٍ آخر.
    """
    cfg = p.get("anti_chasing") or {}
    reasons: list[str] = []

    d = _closed(d1)
    if d is not None and len(d) > 1:
        c = d["close"].astype(float)
        chg = float((c.iloc[-1] / c.iloc[-2] - 1) * 100)
        if chg > float(cfg.get("max_change_24h", 20.0)):
            reasons.append(f"تغيّر 24س {chg:+.1f}٪")

    h = _closed(h4)
    if h is not None and len(h) > 1:
        c = h["close"].astype(float)
        chg4 = float((c.iloc[-1] / c.iloc[-2] - 1) * 100)
        if chg4 > float(cfg.get("max_change_4h", 15.0)):
            reasons.append(f"تغيّر 4س {chg4:+.1f}٪")

    # ═══ موضع السعر في سلّم فيبوناتشي ═══
    #
    # الفحصان أعلاه يقيسان **سرعة** الارتفاع (٢٤س و٤س). وهذا يقيس
    # **مداه**: سعرٌ تجاوز امتداد ‎1.618‎ للموجة السابقة قطع الحركة
    # التي نبحث عن بدايتها — ولو صعد إليها ببطءٍ لا يلفت المقياسين
    # الآخرين.
    #
    # ولا يُضاف نقاطاً: هذا رفضٌ لا تقييم. والرفض بابٌ قائم في
    # الاستراتيجية أصلاً، فلا تكبر به عائلةٌ ولا يتغيّر وزن.
    if bool((p.get("fib_extension") or {}).get("anti_chasing", True)):
        try:
            from scanner.indicators import fib_extension as fx

            fib = fx.measure(h4, p)
            if fib.get("ok") and fib.get("extended"):
                reasons.append(
                    f"تجاوز امتداد فيب {fx.DEFAULTS['extended_ratio']} "
                    f"عند {fib['extended_at']:.6g}")
        except Exception:  # noqa: BLE001
            # مقياسٌ إضافي: تعذّره لا يمنع الفحوص الأخرى
            pass

    return {"expanded": bool(reasons), "reasons": reasons}


# ═══════════════════════ ٤) التقييم ═══════════════════════

#: الأسواق التي يعني فيها نظام البتكوين شيئاً.
#
# ═══ لماذا قائمة لا شرطٌ على الاسم ═══
#
# ``market == "crypto"`` يكسر بصمت لو أُضيف سوقٌ رقميّ ثانٍ باسمٍ
# آخر. والقائمة تُقرأ وتُعدَّل، والاسم غير المذكور فيها **لا**
# يُحسب له نظام BTC — وهو الافتراض الآمن.
BTC_MARKETS = frozenset({"crypto"})


def evaluate(frames: dict, *, btc: dict | None = None,
             params: dict | None = None, market: str = "crypto") -> dict:
    """يقيّم رمزاً واحداً — ويعيد النقاط وتفصيلها وعائلاتها.

    ═══ ``market`` وأثره ═══

    نظام البتكوين سياقٌ للسوق الرقميّ وحده. وكان يُطبَّق على كل
    سوق: عشر نقاطٍ من مئة لسهمٍ سعوديّ تتحرّك بحركة البتكوين،
    ومُضاعِفُ ثقةٍ يهبط إلى ٠٫٤ لأرامكو لأنّ البتكوين هابط.

    فخارج ``BTC_MARKETS`` يُحذَف العامل **ولا يُصفَّر**: التصفير
    يُبقيه في المقام فيخفض كل درجة عشر نقاط، والحذف يُعيد توزيع
    وزنه على العوامل الباقية.
    """
    p = params or load_params()
    btc_applies = market in BTC_MARKETS
    if not btc_applies:
        btc = None
    w = p.get("weights") or {}

    # ═══ إعادة التوزيع قبل الحساب لا بعده ═══
    #
    # الوزن يُعاد توزيعه على الأوزان **نفسها**، فيخرج كل شيءٍ
    # متّسقاً: العوامل ومجاميع العائلات والدرجة. والبديل — قسمةُ
    # الدرجة النهائية وحدها — يترك العائلات على مقياسٍ آخر، فتُجمَع
    # على الشاشة فلا تساوي الدرجة المعروضة فوقها.
    #
    # والنسبة تُحسب من الأوزان المعلَنة لا من ثابت ١٠٠: من غيّر
    # أوزانه في ‎config/pes.yaml‎ يبقى مجموعه محفوظاً.
    if not btc_applies and float(w.get("btc_regime", 0)) > 0:
        _bw = float(w["btc_regime"])
        _rest = {k: float(v) for k, v in w.items() if k != "btc_regime"}
        _sum = sum(_rest.values())
        if _sum > 0:
            _k = (_sum + _bw) / _sum
            w = {k: v * _k for k, v in _rest.items()}

    d1, h4 = frames.get("1d"), frames.get("4h")

    chase = already_expanded(d1, h4, p)

    # ═══ الترتيب مقصود: الالتقاء يُحسب أخيراً ═══
    #
    # مرتبتُه العاشرة تشترط تأكيداً من الاتجاه والحجم والانضغاط،
    # فلا بدّ أن تُحسب تلك قبله.
    rsi_f = _f_rsi(h4, float(w.get("rsi", 3)), p)
    trend_f = _f_h4_trend(h4, float(w.get("h4_trend", 10)), p)
    vol_f = _f_volume(h4, float(w.get("volume", 15)), p)
    comp_f = _f_compression(h4, float(w.get("compression", 15)), p)

    # ═══ نقطةٌ واحدة على الأكثر من خارج العائلة ═══
    #
    # الاتجاه والحجم والانضغاط محسوبةٌ في عائلاتها بالفعل،
    # وإعادةُ وزنها هنا عدٌّ مزدوج. فحصّتها من الالتقاء نقطةٌ
    # واحدة من عشر — أي عُشر وزنه، أي واحدٌ من مئة في النتيجة.
    # وهذا حدّ ما نقبله من التداخل، ويُذكر كي لا يُنسى.
    def _strong(f):
        return f.get("max", 0) > 0 and f["points"] / f["max"] >= 0.6

    external = _strong(trend_f) and _strong(vol_f) and _strong(comp_f)
    rsi_ok = _strong(rsi_f)

    factors = [
        _f_daily_trend(d1, float(w.get("daily_trend", 8)), p),
        _f_supertrend(frames, float(w.get("supertrend", 4)), p),
        trend_f, comp_f, vol_f,
        _f_obv(h4, float(w.get("obv", 10)), p),
        _f_resistance(h4, float(w.get("resistance", 10)), p),
        _f_adx(h4, float(w.get("adx", 5)), p),
        rsi_f,
        _f_momentum_confluence(frames,
                               float(w.get("momentum_confluence", 10)), p,
                               rsi_ok=rsi_ok, external_confirm=external),
        _f_divergence(h4, float(w.get("divergence", 2)), p),
    ]
    # ‏macd عاملاً مستقلّاً أُلغي: منطقه كلّه داخل الالتقاء وأدقّ.
    # ويبقى مقروءاً من الإعدادات لمن ثبّت وزناً له صراحةً.
    if float(w.get("macd", 0)) > 0:
        factors.append(_f_macd(h4, float(w["macd"]), p))

    # ═══ الحذف لا التصفير ═══
    #
    # ``_na`` يُبقي الوزن في المقام — وهو صحيحٌ لعاملٍ **تعذّر
    # حسابه**: غيابُ الدليل ليس دليلاً إيجابياً. أمّا هنا فالعامل
    # **غير منطبق** أصلاً، ووزنه أُعيد توزيعه أعلاه. فإضافته ولو
    # صفراً تحسب الوزن مرّتين.
    if btc_applies:
        bw = float(w.get("btc_regime", 10))
        if btc and btc.get("usable"):
            pts = bw * (btc["score"] / 10.0)
            factors.append({"key": "btc_regime", "family": "context",
                            "points": round(pts, 2), "max": bw,
                            "detail": f"BTC {btc['label']} ({btc['score']}/10)"})
        else:
            factors.append(_na("btc_regime", bw, "نظام BTC غير محسوب"))

    total = round(sum(f["points"] for f in factors), 1)

    # ═══ تنوّع العائلات — المادّة ١٧ ═══
    fam_cfg = p.get("families") or {}
    ratio = float(fam_cfg.get("contribution_ratio", 0.4))
    fam: dict[str, dict] = {}
    for f in factors:
        g = fam.setdefault(f["family"], {"points": 0.0, "max": 0.0})
        g["points"] += f["points"]
        g["max"] += f["max"]
    contributing = [k for k, v in fam.items()
                    if v["max"] > 0 and v["points"] / v["max"] >= ratio]

    # السوق الهابط يخفض الثقة بشدّة — لا النقاط بل الثقة
    confidence = 1.0
    if btc and btc.get("usable"):
        if btc["label"] == "هابط":
            confidence = 0.4
        elif btc["label"] == "محايد":
            confidence = 0.75

    # تفصيل الالتقاء يُرفع إلى أعلى المخرَج: التصنيف يحتاجه،
    # والشاشة تعرضه، فلا يُبحث عنه داخل قائمة العوامل.
    conf_f = next((f for f in factors
                   if f["key"] == "momentum_confluence"), {})
    momentum = conf_f.get("confluence") or {"usable": False, "score": 0.0}

    return {
        "score": total,
        "momentum": momentum,
        "factors": factors,
        "families": {k: {"points": round(v["points"], 1),
                         "max": round(v["max"], 1),
                         "label": FAMILY_LABELS.get(k, k)}
                     for k, v in fam.items()},
        "families_contributing": contributing,
        "family_count": len(contributing),
        "already_expanded": chase["expanded"],
        "expanded_reasons": chase["reasons"],
        "confidence": confidence,
        "btc": btc or {},
        # ═══ الفرق بين «لا ينطبق» و«لم يُحسب» ═══
        #
        # ‏``btc: {}`` وحدها ملتبسة: أهي سوقٌ لا شأن لها بالبتكوين،
        # أم كريبتو تعذّر حساب نظامها؟ والشاشة تحتاج التمييز كي
        # تُخفي الشارة في الأولى وتُظهر تحذيراً في الثانية.
        "btc_applies": btc_applies,
        "market": market,
    }


__all__ = ["evaluate", "btc_regime", "load_params", "already_expanded",
           "classify", "breakout_check", "retest_check",
           "FAMILY", "FAMILY_LABELS", "STATES", "STATE_LABELS",
           "NON_ENTRY_STATES"]


# ═══════════════════════ ٥) التصنيف ومراحل الدورة ═══════════════════════

def breakout_check(h4: pd.DataFrame, level: float | None, p: dict) -> dict:
    """اختراقٌ مؤكَّد أم فتيل؟

    ═══ لماذا الجسم لا الإغلاق وحده ═══

    فتيلٌ يخترق المقاومة ثمّ يعود ليس اختراقاً بل رفضاً. والشمعة
    التي جسمها نصف مداها فأكثر تعني أنّ السعر **بقي** فوق المستوى
    لا أنّه لمسه.
    """
    cfg = p.get("classification") or {}
    df = _closed(h4)
    if df is None or len(df) < 25 or not level:
        return {"broke": False, "why": "لا مستوى أو شموع"}

    last = df.iloc[-1]
    o, h, lo, c = (float(last["open"]), float(last["high"]),
                   float(last["low"]), float(last["close"]))
    rng = h - lo
    body = abs(c - o)
    body_ratio = (body / rng) if rng > 0 else 0.0

    vol = df["volume"].astype(float)
    avg = float(vol.rolling(20).mean().iloc[-1])
    rvol = float(vol.iloc[-1]) / avg if avg > 0 else 0.0

    need_rvol = float(cfg.get("breakout_min_rvol", 1.8))
    need_body = float(cfg.get("breakout_min_body_ratio", 0.5))
    closed_above = c > level
    ok = closed_above and rvol >= need_rvol and body_ratio >= need_body

    why = []
    if not closed_above:
        why.append("لم يُغلق فوق المستوى")
    else:
        if rvol < need_rvol:
            why.append(f"RVOL {rvol:.2f} دون {need_rvol}")
        if body_ratio < need_body:
            why.append(f"الجسم {body_ratio:.0%} من المدى — فتيل")
    return {"broke": ok, "closed_above": closed_above,
            "rvol": round(rvol, 2), "body_ratio": round(body_ratio, 2),
            "why": " · ".join(why) or "اختراق مؤكَّد"}


def retest_check(h4: pd.DataFrame, level: float | None, p: dict) -> dict:
    """إعادة اختبار: عودةٌ للمستوى بحجمٍ أقلّ ورفضٍ صاعد.

    المقاومة تتحوّل دعماً — والدليل أن يهبط الحجم أثناء التراجع.
    تراجعٌ بحجمٍ عالٍ بيعٌ لا اختبار.
    """
    cfg = p.get("classification") or {}
    df = _closed(h4)
    if df is None or len(df) < 30 or not level:
        return {"retest": False, "why": "لا مستوى أو شموع"}

    c = float(df["close"].astype(float).iloc[-1])
    dist = abs(c - level) / level * 100
    near = dist <= float(cfg.get("retest_max_distance", 2.0))

    vol = df["volume"].astype(float)
    recent = float(vol.iloc[-3:].mean())
    before = float(vol.iloc[-10:-3].mean())
    volume_dry = recent < before

    last = df.iloc[-1]
    o, h, lo, cl = (float(last["open"]), float(last["high"]),
                    float(last["low"]), float(last["close"]))
    rng = h - lo
    # ذيلٌ سفليّ طويل وإغلاقٌ في النصف العلوي = رفضٌ صاعد
    lower_wick = (min(o, cl) - lo) / rng if rng > 0 else 0.0
    bullish = cl > o and lower_wick >= 0.3

    ok = near and volume_dry and cl > level * 0.98
    return {"retest": ok, "near": near, "distance": round(dist, 2),
            "volume_dry": volume_dry, "bullish_rejection": bullish,
            "why": ("عاد للمستوى بحجمٍ أقلّ" if ok else
                    ("بعيدٌ عن المستوى" if not near else
                     "الحجم لم يهبط أثناء التراجع"))}


def classify(result: dict, h4: pd.DataFrame, *, previous: str = "",
             params: dict | None = None) -> dict:
    """يحوّل النقاط والحالة إلى مرحلةٍ من مراحل الدورة.

    ═══ المراحل تُبنى على تاريخٍ لا على لحظة ═══

    ``ENTRY_READY`` لا تُمنح إلّا لمن مرّ بـ ‏PRE_BREAKOUT ثمّ
    اختراقٍ مؤكَّد ثمّ إعادة اختبار. ولذلك تُحفظ الحالة السابقة
    ويُقارَن بها — ورمزٌ يظهر فجأةً «جاهزاً للدخول» بلا مسارٍ
    مسجَّل هو ادّعاءٌ لا تسلسل.
    """
    p = params or load_params()
    cfg = p.get("classification") or {}
    fam_cfg = p.get("families") or {}

    if result.get("already_expanded"):
        return {"state": "ALREADY_EXPANDED",
                "label": STATE_LABELS["ALREADY_EXPANDED"],
                "why": " · ".join(result.get("expanded_reasons") or []),
                "breakout": {}, "retest": {}}

    # ═══ المتأخّر يُرفض قبل أن يُقيَّم ═══
    #
    # زخمٌ قويّ + ‏StochRSI فوق ٩٠ + ارتفاعٌ تحقّق: الحركة التي
    # نبحث عن **بدايتها** جرت. ونقاطُه قد تكون عالية جدّاً —
    # ولهذا يُفحص هنا لا بعد العتبات، وإلّا خرج «قبل الاختراق»
    # وهو في قمّته.
    mom = result.get("momentum") or {}
    if mom.get("usable"):
        from . import momentum_confluence as mc

        late = mc.is_late({"4h": h4}, mom.get("macd") or {},
                          mom.get("stoch_rsi") or {}, p)
        if late.get("late"):
            return {"state": "LATE_MOMENTUM",
                    "label": STATE_LABELS["LATE_MOMENTUM"],
                    "why": late["why"], "breakout": {}, "retest": {},
                    "momentum": mom}

    res = next((f for f in result["factors"]
                if f["key"] == "resistance"), {})
    level = res.get("level")
    dist = res.get("distance")
    score = result["score"]

    bo = breakout_check(h4, level, p)
    rt = retest_check(h4, level, p)

    need_fams = int(fam_cfg.get("min_for_pre_breakout", 3))
    enough_families = result["family_count"] >= need_fams

    # ═══ شروط الزخم — تُقرأ مرّة وتُستعمل في ثلاثة مواضع ═══
    conf_score = float(mom.get("score", 0.0)) if mom.get("usable") else 0.0
    macd_rising = bool(mom.get("macd_rising"))
    stoch_timing = bool(mom.get("stoch_timing"))
    momentum_turned = macd_rising and stoch_timing

    need_conf_early = float(cfg.get("early_momentum_confluence", 7))
    need_conf_strong = float(cfg.get("strong_pre_breakout_confluence", 7))

    state, why = "NONE", ""
    if bo.get("broke"):
        state, why = "BREAKOUT", bo["why"]
        if previous in ("PRE_BREAKOUT", "STRONG_PRE_BREAKOUT", "WATCH",
                        "EARLY_MOMENTUM"):
            why += " · بعد مرحلة ما قبل الاختراق"
    elif previous in ("BREAKOUT", "BREAKOUT_RETEST") and rt.get("retest"):
        state = "BREAKOUT_RETEST"
        why = rt["why"]
        if rt.get("bullish_rejection"):
            state, why = "ENTRY_READY", why + " · ورفضٌ صاعد"
    elif score >= float(cfg.get("pre_breakout_min", 75)):
        if (dist is not None
                and dist <= float(cfg.get("pre_breakout_max_distance", 3.0))
                and enough_families and not bo.get("closed_above")):
            state = "PRE_BREAKOUT"
            why = f"النقاط {score} · المقاومة على بعد {dist}٪"

            # ═══ الترقية إلى «قويّة» ═══
            #
            # كل شرطٍ هنا من عائلةٍ أخرى: النقاط، والزخم، والمسافة
            # (حركة سعر)، والحجم، وOBV. فالترقية التقاءٌ حقيقي لا
            # تكرارُ مقياسٍ واحد بأسماء.
            obv_f = next((f for f in result["factors"]
                          if f["key"] == "obv"), {})
            obv_rising = obv_f.get("points", 0) > 0
            need_rvol = float(cfg.get("strong_pre_breakout_min_rvol", 1.3))
            rvol = float(bo.get("rvol") or 0.0)
            near = dist <= float(
                cfg.get("strong_pre_breakout_max_distance", 3.0))

            if (score >= float(cfg.get("strong_pre_breakout_min", 75))
                    and conf_score >= need_conf_strong
                    and momentum_turned and near
                    and rvol >= need_rvol and obv_rising):
                state = "STRONG_PRE_BREAKOUT"
                why = (f"النقاط {score} · الالتقاء {conf_score}/10 · "
                       f"المقاومة {dist}٪ · RVOL {rvol:.2f} · OBV صاعد")
        else:
            state = "WATCH"
            # ═══ سبب عدم الترقية يُقال ═══
            #
            # «نقاطٌ عالية وحالةٌ منخفضة» بلا سبب تجعل المستخدم
            # يظنّ العتبة معطّلة.
            miss = []
            if dist is None:
                miss.append("لا مقاومة فوق السعر")
            elif dist > float(cfg.get("pre_breakout_max_distance", 3.0)):
                miss.append(f"المقاومة على بعد {dist}٪")
            if not enough_families:
                miss.append(f"العائلات {result['family_count']} دون "
                            f"{need_fams}")
            if bo.get("closed_above"):
                miss.append("أغلق فوق المستوى بلا تأكيد")
            why = " · ".join(miss)
    elif score >= float(cfg.get("watch_min", 65)):
        # ═══ الإنذار المبكّر ═══
        #
        # النقاط كافية للمراقبة، والزخم **تحوّل** فعلاً، لكنّ
        # الاختراق لم يقترب. وهذه ليست دخولاً — هي «راقب» بسببٍ
        # مسمّى بدل «راقب» بلا سبب.
        #
        # والتسمية تحمي: حالةٌ اسمها «إنذار مبكّر» لا تُقرأ أمرَ
        # شراء، بخلاف «قبل الاختراق» التي تُقرأ كذلك.
        if (score >= float(cfg.get("early_momentum_min", 65))
                and conf_score >= need_conf_early and momentum_turned):
            state = "EARLY_MOMENTUM"
            why = (f"النقاط {score} · الالتقاء {conf_score}/10 — "
                   "المدرَّج صاعد وتقاطع StochRSI، ولمّا يقترب الاختراق")
        else:
            state, why = "WATCH", f"النقاط {score}"

    # ═══ الزخم يرفع ثقة الاختراق لا نقاطه (المادّة ٨) ═══
    #
    # الاختراق يُقرَّر بالإغلاق والحجم وجسم الشمعة — وهذه حركة
    # سعرٍ وحجم، لا زخم. فدعمُ الزخم يزيد الثقة ولا يصنع اختراقاً
    # لم يقع، ولا يُلغي اختراقاً وقع.
    momentum_backs = bool(
        mom.get("usable")
        and (mom.get("macd") or {}).get("hist") is not None
        and (mom["macd"]["hist"] > mom["macd"]["hist_prev"])
        and (mom.get("stoch_rsi") or {}).get("k_above_d"))

    confidence_boost = 0.0
    if state in ("BREAKOUT", "BREAKOUT_RETEST", "ENTRY_READY"):
        if momentum_backs:
            confidence_boost = 0.15
            why += " · والزخم يدعمه (المدرَّج يتمدّد و‎%K≥%D‎)"
        elif mom.get("usable"):
            why += " · لكنّ الزخم لا يدعمه"

    # ═══ الأهداف من امتداد فيبوناتشي ═══
    #
    # هذا هو استعمالها الأصلي كما ينصّ عليه مصدرها: تحديد جني
    # الأرباح. فتُحسب هنا **بعد** التصنيف ولا تدخله — الحالة
    # تُقرَّر بالنقاط والزخم والاختراق، والفيب يقول: إلى أين، وكم
    # يبعد.
    #
    # وقيمتها العملية أنّها تُحوّل «إشارة» إلى **صفقة قابلة
    # للتقييم**: هدفٌ عند مستوىً معروف يُقارَن بالوقف فيُعطي
    # عائد/مخاطرة قبل الدخول.
    fib = {"ok": False}
    try:
        from scanner.indicators import fib_extension as fx

        fib = fx.measure(h4, p, resistance=level)
    except Exception:  # noqa: BLE001
        pass

    if fib.get("ok") and fib.get("confluence"):
        c = fib["confluence"]
        why = (why + " · " if why else "") + \
            f"والمقاومة تقع على امتداد {c['ratio']}"

    return {"state": state, "label": STATE_LABELS.get(state, state),
            "why": why, "breakout": bo, "retest": rt,
            "resistance_level": level, "resistance_distance": dist,
            "momentum": mom, "momentum_backs_breakout": momentum_backs,
            "confidence_boost": confidence_boost,
            "fib": fib,
            "is_entry": state not in NON_ENTRY_STATES}
