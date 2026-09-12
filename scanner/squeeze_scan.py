# -*- coding: utf-8 -*-
"""مسح الانضغاط — من ينتظر تمدّداً، وباحتمالٍ مقيس.

═══ ما قِيس قبل بناء هذا ═══

على شموع مخزّنة حقيقية، بأفقٍ اثنتي عشرة شمعة وتمدّدٍ = ٣× ATR::

    crypto 4h   منضغط  6202/9936  = 62.4٪ [61–63]
                الأساس 28506/52612 = 54.2٪ [54–55]   الفارق +8.2

    us 1d       منضغط  5116/7550  = 67.8٪ [67–69]
                الأساس 26823/45306 = 59.2٪ [59–60]   الفارق +8.6

الفواصل لا تتقاطع والعيّنات بالآلاف — فالانضغاط يرفع الاحتمال
فعلاً. ولو لم يرفعه لقيل ذلك وعُرضت الصفحة بلا احتمال.

═══ ومن أين يأتي كل رقم ═══

    الاحتمال    — من تاريخ السوق والفريم نفسه، لا من الرمز وحده:
                  رمزٌ له خمس حالات لا تُبنى عليه نسبة.
    الوقت      — وسيط عدد الشموع حتى التمدّد بين الحالات التي
                  تمدّدت، مضروباً في طول الشمعة.
    الترتيب    — رتبة الانضغاط الحالية: كم هو ضيّق الآن مقارنةً
                  بآخر ١٢٠ شمعة له.

والاحتمال **للسوق والفريم**، لا لهذا الرمز بعينه. وعرضُه بجانب
رمزٍ يوحي بأنّه تنبؤٌ له — ولذلك يُذكر معه معدّل الأساس دائماً،
فيُقرأ الفارق لا الرقم وحده.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
import time
from pathlib import Path

log = logging.getLogger("scanner.squeeze_scan")

# أفق الانتظار بالشموع لكل فريم — يقارب أسبوعاً في كل حالة
HORIZONS = {"15m": 24, "1h": 24, "4h": 12, "1d": 10, "1w": 8}

# طول الشمعة بالدقائق — لتحويل الشموع إلى وقتٍ مفهوم
TF_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}

# أقلّ عدد حالات قبل النطق باحتمال
MIN_SAMPLE = 200


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def cache_path(market: str, timeframe: str) -> Path:
    return _root() / "data" / "squeeze" / f"{market}_{timeframe}.json"


def _wilson(k: int, n: int) -> tuple[float, float, float]:
    """نسبة بفاصل ويلسون — يصلح للعيّنات الصغيرة."""
    if not n:
        return (0.0, 0.0, 0.0)
    z = 1.959963985
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * max(0.0, centre - half)),
            round(100 * min(1.0, centre + half)))


def build(market: str, timeframe: str, *, limit: int = 0) -> dict:
    """يقيس السوق والفريم، ويرصد المنضغطين الآن.

    القياس والرصد في مرورٍ واحد على الشموع: تحميل ثلاثمئة ملفّ
    مرّتين يضاعف الزمن بلا فائدة.
    """
    from scanner import storage
    from scanner.indicators import squeeze

    horizon = HORIZONS.get(timeframe, 12)
    symbols = storage.stored_symbols(market, timeframe)
    if limit:
        symbols = symbols[:limit]

    tot = {"squeezed": 0, "squeezed_hits": 0, "base": 0, "base_hits": 0}
    bars: list[int] = []
    now_squeezed: list[dict] = []
    scanned = 0
    t0 = time.perf_counter()

    for sym in symbols:
        try:
            df = storage.load(market, sym, timeframe)
        except Exception:  # noqa: BLE001
            continue
        if df is None or len(df) < 200:
            continue
        scanned += 1
        m = squeeze.measure(df, horizon=horizon)
        for k in tot:
            tot[k] += m[k]
        bars += m["bars_to_hit"]

        state = squeeze.current_state(df)
        if state.get("is_squeezed"):
            state["symbol"] = sym
            state["last_candle"] = str(df.index[-1])
            now_squeezed.append(state)

    p, lo, hi = _wilson(tot["squeezed_hits"], tot["squeezed"])
    bp, blo, bhi = _wilson(tot["base_hits"], tot["base"])
    minutes = TF_MINUTES.get(timeframe, 60)
    median_bars = statistics.median(bars) if bars else None

    # ═══ الأضيق أوّلاً ═══
    #
    # رتبة أدنى تعني انضغاطاً أشدّ. والترتيب بالسعر أو بالحجم
    # يخلط سؤالاً بسؤال.
    now_squeezed.sort(key=lambda r: r.get("squeeze_rank", 100))

    return {
        "market": market, "timeframe": timeframe,
        "horizon_bars": horizon,
        "measured_at": time.time(),
        "symbols_scanned": scanned,
        "elapsed_sec": round(time.perf_counter() - t0, 1),
        "probability": {
            "sample": tot["squeezed"], "hits": tot["squeezed_hits"],
            "pct": p, "low": lo, "high": hi,
            "base_sample": tot["base"], "base_hits": tot["base_hits"],
            "base_pct": bp, "base_low": blo, "base_high": bhi,
            "edge": round(p - bp, 1),
            # ═══ متى يُنطق بالاحتمال ═══
            #
            # عيّنةٌ صغيرة أو فاصلان متقاطعان يعنيان أنّنا لا نعرف.
            # وعرضُ رقمٍ في الحالين ادّعاءٌ لا قياس.
            "readable": tot["squeezed"] >= MIN_SAMPLE,
            "beats_base": lo > bhi,
        },
        "timing": {
            "median_bars": median_bars,
            "median_minutes": (int(median_bars * minutes)
                               if median_bars else None),
            "horizon_minutes": horizon * minutes,
            "sample": len(bars),
        },
        "candidates": now_squeezed,
    }


def save(payload: dict) -> Path:
    p = cache_path(payload["market"], payload["timeframe"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str),
                   encoding="utf-8")
    tmp.replace(p)          # استبدالٌ ذرّي: لا يُقرأ ملفٌّ نصف مكتوب
    return p


def load(market: str, timeframe: str) -> dict | None:
    p = cache_path(market, timeframe)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def humanize(minutes: int | None) -> str:
    """دقائق → نصّ عربيّ مفهوم."""
    if not minutes:
        return "—"
    if minutes < 60:
        return f"{minutes} دقيقة"
    if minutes < 1440:
        h = round(minutes / 60)
        return f"{h} ساعة" if h != 2 else "ساعتان"
    d = round(minutes / 1440)
    return f"{d} يوم" if d != 2 else "يومان"


__all__ = ["build", "save", "load", "cache_path", "humanize",
           "HORIZONS", "TF_MINUTES", "MIN_SAMPLE"]
