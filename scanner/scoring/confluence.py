"""عناصر الالتقاء، محسوبة كسلاسل سببية (causal).

لماذا سلاسل لا قيمة واحدة: الماسح الحي والاختبار التاريخي يجب أن يستخدما
المنطق نفسه حرفياً. لو حسبنا الالتقاء بطريقة للحاضر وأخرى للتاريخ، لأصبحت
نتائج الاختبار بلا معنى — تقيس شيئاً غير الذي سيُنفَّذ.

«سببية» تعني: قيمة كل شمعة تعتمد على ما كان معلوماً عندها فقط. القمة تُؤكَّد
بعد `right` شمعة من حدوثها، لذا تُزاح بهذا المقدار قبل الاستخدام.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import MarketConfig
from ..indicators.pine import atr, pivot_high, pivot_low, rsi
from ..indicators.structure import FIB_RATIOS
from ..indicators.volume import obv

KEY_RATIOS = (0.382, 0.5, 0.618)


def confirmed_pivots(src: pd.Series, left: int, right: int, is_high: bool) -> pd.Series:
    """قيمة آخر قمة/قاع *مؤكد ومعلوم* عند كل شمعة."""
    pv = pivot_high(src, left, right) if is_high else pivot_low(src, left, right)
    return pv.shift(right).ffill()


def _previous_confirmed(series: pd.Series) -> pd.Series:
    """القيمة السابقة لسلسلة مؤكدة (تتغير فقط عند تأكد نقطة جديدة)."""
    changed = series.ne(series.shift(1)) & series.notna()
    prev = series.where(changed).shift(1).ffill()
    return prev.where(changed).ffill()


def confluence_frame(df: pd.DataFrame, cfg: MarketConfig) -> pd.DataFrame:
    p = cfg.params
    atr_series = atr(df, p.atr_len)
    close = df["close"]

    swing_high = confirmed_pivots(df["high"], p.zigzag_len, p.zigzag_len, True)
    swing_low = confirmed_pivots(df["low"], p.zigzag_len, p.zigzag_len, False)

    valid = swing_high.notna() & swing_low.notna() & (swing_high > swing_low)
    diff = (swing_high - swing_low).where(valid)
    tol = atr_series * p.fib_tol_atr

    fib_hit = pd.Series(False, index=df.index)
    fib_which = pd.Series(np.nan, index=df.index)
    for r in KEY_RATIOS:
        level = swing_high - diff * r
        hit = (close - level).abs() <= tol
        hit = hit.fillna(False)
        fib_which = fib_which.mask(hit & fib_which.isna(), r)
        fib_hit |= hit

    equilibrium = (swing_high + swing_low) / 2
    discount = (close < equilibrium).fillna(False) & valid

    bull_div, bear_div = divergence_series(df, cfg)

    out = pd.DataFrame(
        {
            "fib": fib_hit,
            "discount": discount,
            "bull_div": bull_div,
            "bear_div": bear_div,
            "fib_ratio": fib_which,
            "swing_high": swing_high,
            "swing_low": swing_low,
        }
    )
    out["count"] = out[["fib", "discount", "bull_div"]].sum(axis=1).astype(int)
    return out


def divergence_series(df: pd.DataFrame, cfg: MarketConfig) -> tuple[pd.Series, pd.Series]:
    """انحراف السعر عن OBV/RSI، محسوباً سببياً لكل شمعة."""
    p = cfg.params
    left = right = p.div_pivot_len
    active = max(1, p.div_max_bars // 2)

    obv_s = obv(df)
    rsi_s = rsi(df["close"], p.rsi_len)

    def _side(src: pd.Series, bullish: bool) -> pd.Series:
        pv = pivot_low(src, left, right) if bullish else pivot_high(src, left, right)
        marks = pv.notna()
        idx = np.flatnonzero(marks.to_numpy())
        flags = np.zeros(len(df), dtype=bool)

        for k in range(1, len(idx)):
            b, a = idx[k], idx[k - 1]
            if (b - a) > p.div_max_bars:
                continue
            pb, pa = float(pv.iloc[b]), float(pv.iloc[a])
            if (pb < pa) if bullish else (pb > pa):
                osc_ok = False
                for series in (obv_s, rsi_s):
                    ob, oa = series.iloc[b], series.iloc[a]
                    if np.isnan(ob) or np.isnan(oa):
                        continue
                    if (ob > oa) if bullish else (ob < oa):
                        osc_ok = True
                        break
                if osc_ok:
                    # معلوم فقط بعد تأكيد القمة/القاع بـ right شمعة
                    start = b + right
                    flags[start : start + active] = True

        return pd.Series(flags, index=df.index)

    return _side(df["low"], True), _side(df["high"], False)
