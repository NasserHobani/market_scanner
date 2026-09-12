"""مؤشرات الفوليوم المستخدمة في محرك التسجيل."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .pine import ema, sma


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0.0))
    return (direction * df["volume"]).cumsum()


def money_flow_multiplier(df: pd.DataFrame) -> pd.Series:
    rng = df["high"] - df["low"]
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng.replace(0.0, np.nan)
    return mfm.fillna(0.0)


def cmf(df: pd.DataFrame, length: int) -> pd.Series:
    mfv = money_flow_multiplier(df) * df["volume"]
    return mfv.rolling(length, min_periods=length).sum() / df["volume"].rolling(
        length, min_periods=length
    ).sum().replace(0.0, np.nan)


def ad_line(df: pd.DataFrame) -> pd.Series:
    return (money_flow_multiplier(df) * df["volume"]).cumsum()


def mfi(df: pd.DataFrame, length: int) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    raw = tp * df["volume"]
    up = raw.where(tp.diff() > 0, 0.0)
    dn = raw.where(tp.diff() < 0, 0.0)
    pos = up.rolling(length, min_periods=length).sum()
    neg = dn.rolling(length, min_periods=length).sum()
    ratio = pos / neg.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + ratio))
    out[neg == 0.0] = 100.0
    return out


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """ta.vwap يعيد التصفير مع كل جلسة. للعملات: الجلسة يوم UTC."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    day = df.index.floor("D")
    pv = (tp * df["volume"]).groupby(day).cumsum()
    vv = df["volume"].groupby(day).cumsum()
    return pv / vv.replace(0.0, np.nan)


def obv_macd(obv_series: pd.Series, fast: int, slow: int, signal: int) -> pd.Series:
    macd_line = ema(obv_series, fast) - ema(obv_series, slow)
    return macd_line - ema(macd_line, signal)


def delta_approx(df: pd.DataFrame) -> pd.Series:
    """تقدير صافي التدفق بلون الشمعة.

    المرحلة 1 تستبدل هذا بدلتا حقيقية من فريم أدنى؛ المرحلة 0 تكتفي بالتقدير.
    """
    buy = df["volume"].where(df["close"] > df["open"], 0.0)
    sell = df["volume"].where(df["close"] < df["open"], 0.0)
    total = buy + sell
    return ((buy - sell) / total.replace(0.0, np.nan)).fillna(0.0)


def rvol(df: pd.DataFrame, length: int) -> pd.Series:
    return df["volume"] / sma(df["volume"], length).replace(0.0, np.nan)
