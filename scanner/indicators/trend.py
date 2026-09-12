# -*- coding: utf-8 -*-
"""‏ADX و MACD و Supertrend — ومعها ميولها.

═══ لماذا الميل لا القيمة وحدها ═══

الاستراتيجية تطلب «‏ADX صاعد» لا «‏ADX مرتفع». والفرق جوهريّ::

    18 → 20 → 23 → 26     اتجاهٌ يتكوّن الآن
    42 → 45 → 47          اتجاهٌ بدأ ونضج — فات أوانه

القيمة وحدها لا تفرّق بينهما: كلتاهما «‏ADX فوق ٢٥». والميل يفرّق.

وكذلك ‏MACD: التقاطع حدثٌ متأخّر، وارتفاع المدرَّج (histogram) من
سالبٍ نحو الصفر يسبقه::

    -0.08 → -0.06 → -0.04 → -0.02 → +0.01

فالزخم تحسّن قبل أن يتقاطع الخطّان.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .pine import ema, rma, true_range


def adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """‏ADX و ‎+DI‎ و ‎-DI‎ بطريقة وايلدر.

    التنعيم بـ ``rma`` لا ``sma`` — وهو ما يستعمله وايلدر أصلاً،
    وما تحسبه به منصّات التداول. والفرق بينهما ليس تجميلاً: قيمة
    ‏ADX تختلف اختلافاً يغيّر القرار عند العتبات.
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    up = high.diff()
    down = -low.diff()
    # حركةٌ اتجاهية: تُحتسب للأقوى وحدها، وإلّا حُسبت الشمعة مرّتين
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0),
                        index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0),
                         index=df.index)

    atr_ = rma(true_range(df), length)
    safe = atr_.replace(0, np.nan)
    plus_di = 100 * rma(plus_dm, length) / safe
    minus_di = 100 * rma(minus_dm, length) / safe
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    return pd.DataFrame({"adx": rma(dx, length), "plus_di": plus_di,
                         "minus_di": minus_di}, index=df.index)


def macd(src: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> pd.DataFrame:
    """خطّ MACD وإشارته ومدرّجه."""
    src = src.astype(float)
    line = ema(src, fast) - ema(src, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig},
                        index=src.index)


def supertrend(df: pd.DataFrame, length: int = 10,
               mult: float = 3.0) -> pd.DataFrame:
    """‏Supertrend — الاتجاه والخطّ.

    الحدّان يُثبَّتان تصاعدياً: الحدّ الأدنى لا ينزل ما دام الاتجاه
    صاعداً. وبلا هذا التثبيت يتذبذب الخطّ مع كل شمعة ويفقد معناه.
    """
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    close = df["close"].astype(float).to_numpy()
    atr_ = rma(true_range(df), length).to_numpy()
    hl2 = (high + low) / 2.0

    upper = hl2 + mult * atr_
    lower = hl2 - mult * atr_
    n = len(close)
    fu = np.full(n, np.nan)
    fl = np.full(n, np.nan)
    dirn = np.ones(n)

    for i in range(1, n):
        if not np.isfinite(atr_[i]):
            continue
        pu = fu[i - 1] if np.isfinite(fu[i - 1]) else upper[i]
        pl = fl[i - 1] if np.isfinite(fl[i - 1]) else lower[i]
        fu[i] = upper[i] if (upper[i] < pu or close[i - 1] > pu) else pu
        fl[i] = lower[i] if (lower[i] > pl or close[i - 1] < pl) else pl
        if close[i] > fu[i]:
            dirn[i] = 1
        elif close[i] < fl[i]:
            dirn[i] = -1
        else:
            dirn[i] = dirn[i - 1]

    line = np.where(dirn == 1, fl, fu)
    return pd.DataFrame({"supertrend": line, "direction": dirn},
                        index=df.index)


def slope(series: pd.Series, window: int = 5) -> float:
    """ميل آخر ``window`` قيمة — بالانحدار لا بالطرح.

    ``last - first`` تخدعه قفزةٌ واحدة في الطرف. والانحدار الخطّي
    يستعمل النقاط كلّها، فيقول «يصعد باطّراد» لا «انتهى أعلى ممّا
    بدأ».

    والقيمة تُطبَّع على متوسّط السلسلة، فتُقارَن بين رمزٍ ‏ADX له
    عشرون وآخر له خمسون.
    """
    s = series.dropna()
    if len(s) < max(3, window):
        return 0.0
    y = s.iloc[-window:].to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    denom = ((x - x.mean()) ** 2).sum()
    if denom <= 0:
        return 0.0
    m = float(((x - x.mean()) * (y - y.mean())).sum() / denom)
    scale = float(np.abs(y).mean()) or 1.0
    return round(m / scale, 6)


def rising(series: pd.Series, window: int = 5, *,
           min_slope: float = 0.0) -> bool:
    return slope(series, window) > min_slope


__all__ = ["adx", "macd", "supertrend", "slope", "rising"]
