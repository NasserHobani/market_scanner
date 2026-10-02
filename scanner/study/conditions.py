# -*- coding: utf-8 -*-
"""شروط الدخول — تُقاس ولا تُبحَث.

═══ الفرق بين القياس والبحث ═══

لو مشيتُ على التاريخ أجرّب عتبات RSI من ٥ إلى ٩٥ وأفقاً من ٤ إلى
٩٦ شمعة، لوجدتُ تركيبةً نسبتها ٨٠٪. ووجودُها مضمونٌ رياضياً حتى
على بياناتٍ عشوائية: ألفُ محاولةٍ تُنتج صدفةً تبدو قانوناً.

فالشروط هنا **مكتوبةٌ سلفاً** — وهي حالات المنصّة نفسها التي
تعمل بها بقيّة الشاشات. لا تُولَّد ولا تُحسَّن على البيانات، فما
يُقاس هو ما يُستعمل فعلاً.

وعددُها ثابتٌ معروف، فتصحيح المقارنات المتعدّدة له معنى: مع
خمسة عشر شرطاً، واحدٌ بـ‎p<0.05‎ متوقَّعٌ بالصدفة وحدها.

═══ والتقسيم الزمنيّ ═══

النصف الأوّل للاكتشاف، والأخير للتحقّق. وشرطٌ يعمل في الأوّل
ويسقط في الثاني ليس اكتشافاً بل ملاءمةً — ويُوسَم بذلك صراحةً.

ولا يُخلَط التقسيم: السلاسل الزمنية لا تُبعثَر عشوائياً، فالتدريب
على ٢٠٢٦ والاختبار على ٢٠٢٣ تسريبٌ صريح.

═══ وما لا يُعرَض ═══

لا «أفضل شرط» بلا نظرٍ في تداخل الفواصل. شرطان نسبتهما ٦٢٪ و‏٥٨٪
وفاصلاهما متداخلان ليسا مرتّبين — والترتيب بينهما اختراع.
"""
from __future__ import annotations

import math

import numpy as np

from .labels import OPEN, WIN

__all__ = ["evaluate", "CONDITIONS", "MIN_N"]

#: أقلّ عدد حالاتٍ محسومة قبل الحكم على شرط
MIN_N = 20
Z95 = 1.959963985


def _wilson(k: int, n: int) -> tuple[float, float, float]:
    if n <= 0:
        return (0.0, 0.0, 100.0)
    p = k / n
    d = 1 + Z95 * Z95 / n
    c = (p + Z95 * Z95 / (2 * n)) / d
    h = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * max(0.0, c - h), 1),
            round(100 * min(1.0, c + h), 1))


def _binom_p(k: int, n: int, p0: float) -> float:
    """‏p ثنائية الطرف بالصيغة الدقيقة — بلا scipy.

    والعيّنات هنا عشرات لا آلاف، والتقريب الطبيعيّ يخطئ عند
    الأطراف حيث تقع النتائج المهمّة.
    """
    if n <= 0 or not (0.0 < p0 < 1.0):
        return 1.0
    from math import comb

    def pmf(i: int) -> float:
        return comb(n, i) * (p0 ** i) * ((1 - p0) ** (n - i))

    obs = pmf(k)
    tol = obs * 1e-9
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs + tol))


def _bh(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    """بنجاميني–هوكبرج: أيّ الفحوص يصمد بعد التصحيح."""
    m = len(pvals)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    keep = [False] * m
    thresh = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= alpha * rank / m:
            thresh = rank
    for rank, i in enumerate(order, start=1):
        if rank <= thresh:
            keep[i] = True
    return keep


# ═══════════════════════════════════════════════════════════════
#  الشروط — مكتوبةٌ سلفاً، وهي حالات المنصّة نفسها
# ═══════════════════════════════════════════════════════════════

def _build_series(df, daily=None) -> dict:
    """المؤشّرات مرّةً واحدة — لا مرّةً لكل شرط."""
    from scanner.indicators.momentum import stoch_rsi
    from scanner.indicators.pine import atr, ema, rsi
    from scanner.indicators.trend import adx, macd, supertrend

    close = df["close"].astype(float)
    out: dict = {}
    out["close"] = close.to_numpy()
    out["rsi"] = rsi(close, 14).to_numpy()
    out["ema50"] = ema(close, 50).to_numpy()
    out["ema200"] = ema(close, 200).to_numpy()
    out["atr"] = atr(df, 14).to_numpy()

    m = macd(close)
    hist = m["hist"].to_numpy()
    out["hist"] = hist
    out["hist_prev"] = np.concatenate(([np.nan], hist[:-1]))
    line, sig = m["macd"].to_numpy(), m["signal"].to_numpy()
    out["above_signal"] = line > sig

    f = stoch_rsi(close)
    out["k"] = f["k"].to_numpy()
    out["d"] = f["d"].to_numpy()
    out["k_prev"] = np.concatenate(([np.nan], out["k"][:-1]))
    out["d_prev"] = np.concatenate(([np.nan], out["d"][:-1]))

    try:
        st = supertrend(df)
        out["st_dir"] = np.asarray(st["direction"], dtype="float64")
    except Exception:  # noqa: BLE001
        out["st_dir"] = np.full(len(df), np.nan)
    try:
        out["adx"] = adx(df, 14).to_numpy()
    except Exception:  # noqa: BLE001
        out["adx"] = np.full(len(df), np.nan)

    vol = df["volume"].astype(float)
    out["rvol"] = (vol / vol.rolling(20).mean()).to_numpy()

    # ═══ السياق اليوميّ ═══
    #
    # الفريم المعروض يقول «أين»، واليوميّ يقول «في أيّ اتّجاه».
    # والمحاذاة بالزمن لا بالموضع: الفهرسان مختلفا الطول.
    out["daily_up"] = np.full(len(df), np.nan)
    if daily is not None and len(daily) > 60:
        import pandas as pd

        d_close = daily["close"].astype(float)
        d_up = (d_close > ema(d_close, 50)).astype(float)
        aligned = d_up.reindex(
            pd.DatetimeIndex(df.index).tz_convert(None)
            if getattr(df.index, "tz", None) else df.index,
            method="ffill")
        out["daily_up"] = aligned.to_numpy(dtype="float64")
    return out


def _masks(s: dict) -> list[tuple[str, str, np.ndarray]]:
    """‏(المفتاح، الاسم، القناع) لكل شرط. والترتيب ثابت."""
    k, d = s["k"], s["d"]
    kp, dp = s["k_prev"], s["d_prev"]
    hist, hp = s["hist"], s["hist_prev"]
    close, e50, e200 = s["close"], s["ema50"], s["ema200"]

    def ok(x):
        return np.nan_to_num(x, nan=0.0).astype(bool)

    return [
        ("rsi_low", "‏RSI دون ٣٥", ok(s["rsi"] < 35)),
        ("rsi_high", "‏RSI فوق ٦٥", ok(s["rsi"] > 65)),
        ("above_ema50", "السعر فوق ‎EMA50‎", ok(close > e50)),
        ("golden", "‎EMA50‎ فوق ‎EMA200‎", ok(e50 > e200)),
        ("macd_rising", "مدرَّج MACD صاعد", ok(hist > hp)),
        ("macd_early", "تحسّن مبكّر (سالب وصاعد)",
         ok((hist > hp) & (hist < 0))),
        ("macd_above_signal", "‏MACD فوق إشارته", ok(s["above_signal"])),
        ("stoch_cross", "تقاطع StochRSI صاعد", ok((kp <= dp) & (k > d))),
        ("stoch_low", "‏StochRSI دون ٢٠", ok(k < 20)),
        ("stoch_riding", "تشبّع شرائي في اتّجاه صاعد",
         ok((k >= 80) & (close > e50))),
        ("st_up", "‏Supertrend صاعد", ok(s["st_dir"] > 0)),
        ("adx_strong", "‏ADX فوق ٢٥", ok(s["adx"] > 25)),
        ("rvol_high", "حجم نسبيّ فوق ١٫٥×", ok(s["rvol"] > 1.5)),
        ("daily_up", "اليوميّ فوق ‎EMA50‎", ok(s["daily_up"] > 0)),
        ("pullback", "ارتدادٌ إلى ‎EMA50‎ في اتّجاه صاعد",
         ok((e50 > e200) & (close <= e50 * 1.01) & (close >= e50 * 0.97))),
    ]


def evaluate(df, labels: dict, *, daily=None, split: float = 0.7,
             min_n: int = MIN_N, alpha: float = 0.05) -> dict:
    """يقيس كل شرطٍ على الرمز — داخل العيّنة وخارجها."""
    lab = labels["label"]
    n = len(df)
    if n < 200 or not labels.get("ok"):
        return {"ok": False, "why": "تاريخٌ غير كافٍ", "conditions": []}

    s = _build_series(df, daily)
    cut = int(n * split)

    settled_all = lab != OPEN
    base = settled_all.sum()
    base_wins = int((lab[settled_all] == WIN).sum())
    base_rate = base_wins / base if base else 0.0

    rows = []
    for key, label, mask in _masks(s):
        m_in = mask & settled_all
        m_in[cut:] = False
        m_out = mask & settled_all
        m_out[:cut] = False

        def stat(sel):
            nn = int(sel.sum())
            kk = int((lab[sel] == WIN).sum())
            p, lo, hi = _wilson(kk, nn)
            return {"n": nn, "wins": kk, "rate": p, "lo": lo, "hi": hi}

        a, b = stat(m_in), stat(m_out)
        p_val = _binom_p(a["wins"], a["n"], base_rate) if a["n"] >= min_n else 1.0
        rows.append({
            "key": key, "label": label,
            "in_sample": a, "out_sample": b,
            "p": round(p_val, 6),
            "enough": a["n"] >= min_n,
            "lift": (round(a["rate"] - base_rate * 100, 1)
                     if a["rate"] is not None else None),
        })

    keep = _bh([r["p"] for r in rows], alpha)
    for r, survived in zip(rows, keep):
        r["survives_correction"] = bool(survived and r["enough"])
        # ═══ والتحقّق خارج العيّنة هو الحكم ═══
        #
        # شرطٌ يتفوّق في النصف الأوّل ويسقط في الأخير ملاءمةٌ لا
        # اكتشاف. ويُقال ذلك بكلمةٍ لا يُترك للقارئ أن يستنتجه.
        o = r["out_sample"]
        if not r["enough"]:
            r["verdict"] = "عيّنة قصيرة — لا حكم"
        elif not r["survives_correction"]:
            r["verdict"] = "ضمن الضجيج بعد التصحيح"
        elif o["n"] < min_n:
            r["verdict"] = "صمد داخل العيّنة — ولم يُختبَر خارجها بعد"
        elif o["lo"] > base_rate * 100:
            r["verdict"] = "صمد داخل العيّنة وخارجها"
        else:
            r["verdict"] = "صمد داخلها وسقط خارجها — ملاءمة"

    rows.sort(key=lambda r: (-(r["out_sample"]["lo"] or 0),
                             -(r["in_sample"]["lo"] or 0)))
    return {
        "ok": True,
        "conditions": rows,
        "baseline": {"n": int(base), "wins": base_wins,
                     "rate": round(base_rate * 100, 1)},
        "split_at": cut,
        "tests": len(rows),
        "alpha": alpha,
        "note": (f"{len(rows)} شرطاً مكتوباً سلفاً — لا مبحوثاً في "
                 "البيانات. والتصحيح ببنجاميني–هوكبرج: مع هذا العدد، "
                 "واحدٌ بـ‎p<0.05‎ متوقَّعٌ بالصدفة وحدها."),
    }
