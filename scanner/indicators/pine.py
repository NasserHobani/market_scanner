"""دوال مطابقة لسلوك Pine Script.

سبب وجود هذا الملف بدل استخدام مكتبة تحليل فني جاهزة:
Pine يستخدم تنعيم RMA (Wilder) في ta.rsi و ta.atr، ويهيّئ ta.ema بمتوسط بسيط
لأول قيمة. أغلب المكتبات تخالف هذه التفاصيل فتعطي أرقاماً مختلفة عن الشارت.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(src: pd.Series, length: int) -> pd.Series:
    return src.rolling(length, min_periods=length).mean()


def _smooth(src: pd.Series, length: int, alpha: float) -> pd.Series:
    """تنعيم أسّي مهيّأ بمتوسط بسيط، مع تخطي القيم الفارغة في البداية.

    تخطي الفراغات ضروري: مدخلات مثل خط MACD لا تبدأ إلا بعد استقرار
    المتوسطات، ولو هيّأنا من أول عنصر لخرجت السلسلة كلها فارغة.
    """
    out = pd.Series(np.nan, index=src.index, dtype="float64")
    vals = src.to_numpy(dtype="float64")
    n = len(vals)
    valid = np.flatnonzero(~np.isnan(vals))
    if valid.size < length:
        return out

    start = valid[length - 1]          # موضع اكتمال أول نافذة صالحة
    seed = np.nanmean(vals[valid[:length]])
    res = np.full(n, np.nan)
    res[start] = seed
    prev = seed
    for i in range(start + 1, n):
        v = vals[i]
        if np.isnan(v):
            res[i] = prev
            continue
        prev = alpha * v + (1.0 - alpha) * prev
        res[i] = prev
    out.iloc[:] = res
    return out


def ema(src: pd.Series, length: int) -> pd.Series:
    """مطابق لـ ta.ema: القيمة الأولى متوسط بسيط ثم تنعيم أسّي."""
    return _smooth(src, length, 2.0 / (length + 1.0))


def rma(src: pd.Series, length: int) -> pd.Series:
    """تنعيم Wilder المستخدم في ta.rsi و ta.atr (alpha = 1/length)."""
    return _smooth(src, length, 1.0 / length)


def rsi(src: pd.Series, length: int) -> pd.Series:
    delta = src.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = rma(gain, length)
    avg_loss = rma(loss, length)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out[avg_loss == 0.0] = 100.0
    out[(avg_gain == 0.0) & (avg_loss > 0.0)] = 0.0
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    a = df["high"] - df["low"]
    b = (df["high"] - prev_close).abs()
    c = (df["low"] - prev_close).abs()
    tr = pd.concat([a, b, c], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return tr


def atr(df: pd.DataFrame, length: int) -> pd.Series:
    return rma(true_range(df), length)


def _rolling_extreme(vals: np.ndarray, width: int, high: bool) -> np.ndarray:
    """أقصى كل نافذة متتالية بعرض ``width``.

    الناتج بطول ``n - width + 1``؛ العنصر ``j`` يقابل ``vals[j:j+width]``.

    ``sliding_window_view`` يبني عرضاً للنوافذ بلا نسخ الذاكرة، فتُحسب
    كلها دفعةً واحدة. وكانت النسخة السابقة تدور على كل شمعة وتستدعي
    ``np.nanmax`` على شريحة صغيرة ثم تكتب بـ ``out.iloc[i]`` — وكتابة
    pandas بالموضع من أبطأ ما فيه. القياس: 21,117 نداء فهرسة في تحليل
    رمز واحد.
    """
    import warnings

    from numpy.lib.stride_tricks import sliding_window_view

    fn = np.nanmax if high else np.nanmin
    with warnings.catch_warnings():
        # نافذة كلها NaN تُنتج NaN مع تحذير. وNaN هو المطلوب تماماً:
        # المقارنة معه تعطي False أي «ليست محوَّراً» — وهو سلوك النسخة
        # القديمة نفسه، إذ ``np.nanmax`` كان يفعل الشيء ذاته.
        warnings.simplefilter("ignore", RuntimeWarning)
        return fn(sliding_window_view(vals, width), axis=1)


def _side_extremes(vals: np.ndarray, left: int, right: int, high: bool
                   ) -> tuple[np.ndarray, np.ndarray]:
    """لكل موضع ``i``: أقصى ``vals[i-left:i]`` وأقصى ``vals[i+1:i+right+1]``.

    الإزاحتان هما كل الدقّة المطلوبة هنا، وخطأ واحد فيهما يزيح المحوّرات
    شمعةً كاملة — وهو خطأ لا يظهر كعُطل بل كإشارات مختلفة بصمت. لذلك
    يتحقّق ``tests_pivots`` من التطابق التام مع النسخة القديمة.
    """
    n = vals.size
    left_ext = np.full(n, np.nan, dtype="float64")
    right_ext = np.full(n, np.nan, dtype="float64")

    # نافذة اليسار عند i هي الصفّ (i-left) ⇒ تملأ المواضع left..n-1
    if left > 0 and n >= left:
        agg = _rolling_extreme(vals, left, high)      # طولها n-left+1
        take = min(n - left, agg.size)
        left_ext[left:left + take] = agg[:take]

    # نافذة اليمين عند i هي الصفّ (i+1) ⇒ تملأ المواضع 0..n-right-1
    if right > 0 and n >= right:
        agg = _rolling_extreme(vals, right, high)     # طولها n-right+1
        take = max(0, min(n - right, agg.size - 1))
        right_ext[:take] = agg[1:1 + take]

    return left_ext, right_ext


def _pivots(src: pd.Series, left: int, right: int, high: bool) -> pd.Series:
    n = len(src)
    vals = src.to_numpy(dtype="float64")
    out = pd.Series(np.nan, index=src.index, dtype="float64")
    if n <= left + right:
        return out

    left_ext, right_ext = _side_extremes(vals, left, right, high)
    with np.errstate(invalid="ignore"):
        if high:
            ok = (vals > left_ext) & (vals >= right_ext)
        else:
            ok = (vals < left_ext) & (vals <= right_ext)
    ok &= ~np.isnan(vals)

    # خارج المدى الصالح لا محوَّر: اليسار يحتاج ``left`` شمعة قبله،
    # واليمين ``right`` بعده
    ok[:left] = False
    ok[n - right:] = False

    out.iloc[:] = np.where(ok, vals, np.nan)
    return out


def pivot_high(src: pd.Series, left: int, right: int) -> pd.Series:
    """قمة مؤكدة: أعلى تماماً من كل ما على اليسار، ولا يعلوها شيء على اليمين.

    شرط اليمين متساهل (>=) عمداً: تساوي قمتين متجاورتين يحدث فعلاً في السوق
    (سيولة ضعيفة، أو بيانات نهاية يوم). لو اشترطنا التفوق التام على الجانبين
    لسقطت هذه القمم بصمت، ومعها ينهار الهيكل وفيبوناتشي والقناة كلها.
    عند التساوي تُختار أول شمعة في المستوى.
    """
    return _pivots(src, left, right, high=True)


def pivot_low(src: pd.Series, left: int, right: int) -> pd.Series:
    """قاع مؤكد — انظر ملاحظة التساوي في pivot_high."""
    return _pivots(src, left, right, high=False)
