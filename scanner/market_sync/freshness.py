# -*- coding: utf-8 -*-
"""Data freshness assessment — timeframe-aware."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

import pandas as pd

from scanner import sessions, storage
from scanner.live import timeframe_seconds

from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    CRITICAL = "critical"
    # ═══ لماذا «ميّت» حالةٌ مستقلّة ═══
    #
    # ‏POLYUSDT آخر شمعة له 2022-10-10 — متأخّر ٨٤٧٢ شمعة. وهذا ليس
    # «بيانات متأخّرة» بل رمزٌ **شُطب من المنصّة**: الملف باقٍ على
    # القرص والجلب التراكمي يطلب الناقص فلا يعود بشيء، إلى الأبد.
    #
    # وعدُّه ``critical`` كان يخلطه بعطلٍ حقيقيّ قابل للإصلاح. وحين
    # بلغ عدد المشطوبين ١٣٨ من ٥٢٦ تجاوز «الحرج» نصف السوق، فأعلنت
    # البوابة الكريبتو متأخّراً وأوقفت المسح — منذ ٢٠ أغسطس، بلا
    # دورة ولا مراقبة ولا صفقة.
    #
    # أي أنّ مقبرةً على القرص كانت تحجب سوقاً حيّاً.
    DEAD = "dead"
    ERROR = "error"
    MISSING = "missing"


def expected_open_candle(timeframe: str, *, now: float | None = None) -> pd.Timestamp:
    """UTC open time of the currently forming candle."""
    import time
    from scanner.live import WEEK_ANCHOR

    period = timeframe_seconds(timeframe)
    now = time.time() if now is None else now
    if timeframe == "1w":
        open_epoch = ((int(now) - WEEK_ANCHOR) // period) * period + WEEK_ANCHOR
    else:
        open_epoch = (int(now) // period) * period
    return pd.Timestamp(open_epoch, unit="s", tz="UTC")


def assess_freshness(
    market: str,
    symbol: str,
    timeframe: str,
    *,
    df: pd.DataFrame | None = None,
    last_sync: str | None = None,
    error: str | None = None,
    config: MarketSyncConfig = DEFAULT_SYNC_CONFIG,
    now: float | None = None,
) -> dict[str, Any]:
    """Return freshness metadata for one symbol/timeframe."""
    if error:
        return {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "latest_candle": None,
            "last_sync": last_sync,
            "age_seconds": None,
            "bars_behind": None,
            "status": FreshnessStatus.ERROR.value,
            "error": error,
        }

    # ═══ لماذا لا يُحمَّل الملف كاملاً ═══
    #
    # كل ما يلزم هنا طابع آخر شمعة. وتحميل 1200 شمعة لقراءته هدر
    # يتضاعف 1588 مرّة في ``global_status`` — وهو ما جعل نداءً واحداً
    # يستغرق 26 ثانية ويُعلّق كل صفحة.
    #
    # فإن لم يُمرَّر إطار، يُقرأ الذيل. وإن تعذّر يسقط إلى التحميل
    # الكامل، فلا يُبنى حكم على قراءة ناقصة.
    frame = df
    if frame is None:
        last = storage.last_time_on_disk(market, symbol, timeframe)
        if last is None:
            frame = storage.load(market, symbol, timeframe)
            last = storage.last_time(frame)
    else:
        last = storage.last_time(frame)
    if last is None:
        return {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "latest_candle": None,
            "last_sync": last_sync,
            "age_seconds": None,
            "bars_behind": None,
            "status": FreshnessStatus.MISSING.value,
            "error": None,
        }

    # حسبة واحدة للمسارين: من الإطار أو من الطابع، الدالّة نفسها.
    #
    # و``market`` يُمرَّر كي يُقاس التأخّر بزمن السوق المفتوح لا
    # بساعة الحائط. بدونه كان كل سبت يُعلَن عطلاً.
    behind = storage.bars_behind_from(last, timeframe, now=now, market=market)
    try:
        period = timeframe_seconds(timeframe)
    except ValueError:
        period = 3600
    age_seconds = None if behind is None else round(float(behind) * period, 1)

    if behind is None:
        status = FreshnessStatus.ERROR.value
    elif behind <= config.fresh_max_bars:
        status = FreshnessStatus.FRESH.value
    elif behind <= config.stale_max_bars:
        status = FreshnessStatus.STALE.value
    elif behind <= config.dead_max_bars:
        status = FreshnessStatus.CRITICAL.value
    else:
        # ما تجاوز مئة شمعة لا يُصلحه تحديث: رمزٌ توقّف تداوله.
        status = FreshnessStatus.DEAD.value

    latest = last
    if hasattr(latest, "isoformat"):
        latest_s = latest.isoformat()
    else:
        latest_s = str(latest)

    # حالة السوق تُرافق الحكم دائماً: «متأخّر ساعتين والسوق مغلق»
    # و«متأخّر ساعتين والسوق مفتوح» حالتان مختلفتان تماماً، وعرضهما
    # برقمٍ واحد بلا سياق هو ما جعل الإنذار بلا معنى.
    at = None if now is None else pd.Timestamp(now, unit="s", tz="UTC")
    try:
        market_open = sessions.is_open(market, at)
        nxt = sessions.next_open(market, at)
        delay = sessions.feed_delay_seconds(market)
    except Exception:  # noqa: BLE001
        market_open, nxt, delay = True, None, 0

    return {
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "latest_candle": latest_s,
        "last_sync": last_sync,
        "age_seconds": age_seconds,
        "bars_behind": None if behind is None else round(float(behind), 3),
        "status": status,
        "error": None,
        "candle_count": 0 if frame is None else len(frame),
        "expected_open": expected_open_candle(timeframe, now=now).isoformat(),
        "market_open": bool(market_open),
        "next_open": None if nxt is None else nxt.isoformat(),
        "feed_delay_seconds": int(delay),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
