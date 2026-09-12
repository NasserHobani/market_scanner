"""نماذج الشموع اليابانية.

كلها محسوبة كسلاسل سببية: قيمة كل شمعة تعتمد على ما قبلها فقط.
الأحجام نسبية إلى ATR لا إلى قيم مطلقة، وإلا اختلف السلوك بين
سهم سعره 3 ريالات وعملة سعرها 65 ألف دولار.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators.pine import atr


def _parts(df: pd.DataFrame):
    body = (df["close"] - df["open"]).abs()
    upper = df["high"] - df[["open", "close"]].max(axis=1)
    lower = df[["open", "close"]].min(axis=1) - df["low"]
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    bullish = df["close"] > df["open"]
    return body, upper, lower, rng, bullish


def detect(df: pd.DataFrame, atr_len: int = 14, min_body_atr: float = 0.3) -> pd.DataFrame:
    """يعيد إطاراً منطقياً: عمود لكل نموذج."""
    body, upper, lower, rng, bull = _parts(df)
    a = atr(df, atr_len)
    # fill_value يتفادى تحوّل السلسلة إلى float بسبب NaN
    prev_bull = bull.shift(1, fill_value=False)
    prev2_bull = bull.shift(2, fill_value=False)
    prev_body = body.shift(1)
    o, c = df["open"], df["close"]
    po, pc = o.shift(1), c.shift(1)

    significant = body >= a * min_body_atr        # يستبعد الشموع التافهة
    small_body = body <= rng * 0.35               # جسم صغير نسبة لمدى الشمعة
    out = pd.DataFrame(index=df.index)

    # --- انعكاسية صاعدة ---
    out["bull_engulfing"] = (
        bull & ~prev_bull & (c >= po) & (o <= pc) & (body > prev_body) & significant
    )
    # الظلال تُقاس نسبةً لمدى الشمعة لا لجسمها: جسم صغير جداً يجعل
    # أي ظل علوي ضئيل يتجاوز "body * 0.8" فتسقط المطرقة بلا سبب
    # المطرقة جسمها صغير بطبيعتها، فالشرط على حجم الشمعة كاملة لا على جسمها
    meaningful = (rng >= a * 0.5) & (body > 0)
    out["hammer"] = (
        (lower >= body * 2) & (upper <= rng * 0.15) & small_body & meaningful
    )
    out["piercing"] = (
        bull & ~prev_bull & (o < pc) & (c > (po + pc) / 2) & (c < po) & significant
    )
    out["morning_star"] = (
        ~prev2_bull & (body.shift(2) >= a * 0.3)          # شمعة أولى هابطة حقيقية
        & (body.shift(1) <= a * 0.35)                     # جسم صغير في الوسط
        & bull & significant                              # شمعة ثالثة صاعدة حقيقية
        & (c > (o.shift(2) + c.shift(2)) / 2)
    )
    out["bull_harami"] = (
        bull & ~prev_bull & (c <= po) & (o >= pc)
        & (body < prev_body * 0.6) & (prev_body >= a * 0.3)
    )
    out["tweezer_bottom"] = (
        ((df["low"] - df["low"].shift(1)).abs() <= a * 0.1)
        & ~prev_bull & bull & significant & (prev_body >= a * 0.3)
    )

    # --- انعكاسية هابطة ---
    out["bear_engulfing"] = (
        ~bull & prev_bull & (c <= po) & (o >= pc) & (body > prev_body) & significant
    )
    out["shooting_star"] = (
        (upper >= body * 2) & (lower <= rng * 0.15) & small_body & meaningful
    )
    out["dark_cloud"] = (
        ~bull & prev_bull & (o > pc) & (c < (po + pc) / 2) & (c > po) & significant
    )
    out["evening_star"] = (
        prev2_bull & (body.shift(2) >= a * 0.3)
        & (body.shift(1) <= a * 0.35)
        & ~bull & significant
        & (c < (o.shift(2) + c.shift(2)) / 2)
    )
    out["bear_harami"] = (
        ~bull & prev_bull & (c >= po) & (o <= pc)
        & (body < prev_body * 0.6) & (prev_body >= a * 0.3)
    )
    out["tweezer_top"] = (
        ((df["high"] - df["high"].shift(1)).abs() <= a * 0.1)
        & prev_bull & ~bull & significant & (prev_body >= a * 0.3)
    )

    # --- حيادية / استمرارية ---
    out["doji"] = (
        (body <= rng * 0.06) & (rng >= a * 0.5)
        & (upper <= rng * 0.7) & (lower <= rng * 0.7)   # ظلال متوازنة
    )
    out["marubozu_bull"] = bull & (body >= rng * 0.9) & significant
    out["marubozu_bear"] = ~bull & (body >= rng * 0.9) & significant

    return out.fillna(False).astype(bool)


BULLISH = ["bull_engulfing", "hammer", "piercing", "morning_star",
           "bull_harami", "tweezer_bottom", "marubozu_bull"]
BEARISH = ["bear_engulfing", "shooting_star", "dark_cloud", "evening_star",
           "bear_harami", "tweezer_top", "marubozu_bear"]

ARABIC = {
    "bull_engulfing": "ابتلاع صاعد", "hammer": "مطرقة",
    "piercing": "الاختراق", "morning_star": "نجمة الصباح",
    "bull_harami": "حامل صاعد", "tweezer_bottom": "ملقاط قاع",
    "marubozu_bull": "ماروبوزو صاعد",
    "bear_engulfing": "ابتلاع هابط", "shooting_star": "الشهاب",
    "dark_cloud": "الغيمة السوداء", "evening_star": "نجمة المساء",
    "bear_harami": "حامل هابط", "tweezer_top": "ملقاط قمة",
    "marubozu_bear": "ماروبوزو هابط",
    "doji": "دوجي",
}


def summarize(df: pd.DataFrame, lookback: int = 3, **kwargs) -> dict:
    """ملخص آخر الشموع: ما ظهر، وميله، ودرجته."""
    flags = detect(df, **kwargs)
    recent = flags.tail(lookback)
    found = [c for c in flags.columns if recent[c].any()]

    bulls = [c for c in found if c in BULLISH]
    bears = [c for c in found if c in BEARISH]
    score = 1 if bulls and not bears else -1 if bears and not bulls else 0

    return {
        "patterns": [ARABIC.get(c, c) for c in found],
        "bullish": [ARABIC.get(c, c) for c in bulls],
        "bearish": [ARABIC.get(c, c) for c in bears],
        "score": score,
        "flags": flags,
    }
