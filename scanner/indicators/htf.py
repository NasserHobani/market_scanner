"""فلتر الفريم الأعلى بإعادة التجميع، لا بطلب شبكة إضافي.

سبب هذا الخيار: جلب الفريم الأعلى لكل رمز يضاعف عدد الطلبات بلا فائدة —
البيانات نفسها موجودة، وإعادة تجميعها تعطي النتيجة ذاتها بلا كلفة.
"""
from __future__ import annotations

import pandas as pd

from .pine import ema

# تحويل فريم الشارت إلى الفريم الأعلى المناسب — نفس منطق autoHTF في المؤشر
AUTO_HTF = {
    "1m": "15min", "3m": "30min", "5m": "1h", "15m": "4h", "30m": "4h",
    "1h": "4h", "2h": "12h", "4h": "1D", "6h": "1D", "12h": "1D",
    "1d": "1W", "3d": "1W", "1w": "1ME",
}

AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

# هامش الأمان: EMA بطول N تحتاج أكثر من N شمعة لتعطي تاريخاً مفيداً لا قيمة أو اثنتين.
# بدونه يخرج الفلتر «محايداً» في أغلب التاريخ، فيحجب كل الإشارات بصمت.
SAFETY = 1.4


def adaptive_lengths(available: int, fast: int, slow: int):
    """يخفّض أطوال المتوسطات إذا كان تاريخ الفريم الأعلى قصيراً."""
    if available >= int(slow * SAFETY):
        return slow, fast
    usable = int(available / SAFETY)
    if usable < 20:
        return None, None
    slow_eff = max(20, usable)
    fast_eff = max(5, min(fast, slow_eff // 3))
    return slow_eff, fast_eff


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="right", closed="right").agg(AGG).dropna()
    return out


def htf_bias(df: pd.DataFrame, timeframe: str, fast: int = 50, slow: int = 200,
             mode: str = "both") -> tuple[int, str]:
    """يعيد (1 صاعد / -1 هابط / 0 مختلط، وصف نصي)."""
    rule = AUTO_HTF.get(timeframe)
    if rule is None:
        return 0, "غير مدعوم"

    htf = resample(df, rule)
    slow, fast = adaptive_lengths(len(htf), fast, slow)
    if slow is None:
        return 0, f"تاريخ غير كافٍ ({rule}: {len(htf)} شمعة)"

    ef = ema(htf["close"], fast).iloc[-1]
    es = ema(htf["close"], slow).iloc[-1]
    price = htf["close"].iloc[-1]

    ema_bull = ef > es
    price_bull = price > es
    if mode == "ema":
        bull, bear = ema_bull, not ema_bull
    elif mode == "price":
        bull, bear = price_bull, not price_bull
    else:
        bull = ema_bull and price_bull
        bear = (not ema_bull) and (not price_bull)

    if bull:
        return 1, f"صاعد ↑ ({rule})"
    if bear:
        return -1, f"هابط ↓ ({rule})"
    return 0, f"مختلط — ({rule})"
