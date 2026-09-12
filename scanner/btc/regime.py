# -*- coding: utf-8 -*-
"""حالة البتكوين كخصائص قابلة للقياس — بلا Django ولا شبكة.

═══ لماذا وُجدت هذه الوحدة ═══

الفرضية المطروحة: «البتكوين سبب أغلب الخسائر لأنه هبط».

القياس على 243 صفقة آلية محسومة قال غير ذلك:

    البتكوين من 08-01 إلى 08-12 :  62,824 → 63,480  (+1.0%)
    حركته قبل الإشارة — رابحة    :  +0.21%
    حركته قبل الإشارة — خاسرة    :  +0.21%
    الارتباط بالنتيجة            :  +0.04   ← صفر عملياً

فلا هو هبط، ولا حالته السابقة تفرّق بين رابحة وخاسرة.

لكن «متوسط الحركة» مقياس واحد فجّ، وقد تكون العلاقة في شيء آخر:
التقلّب، أو البعد عن المتوسطات، أو ضيق المدى قبل الانفجار. فهذه
الوحدة تبني الخصائص كلها بشكل **غير معيد للرسم** (كل خاصية تُحسب من
شموع مغلقة حتى لحظتها فقط)، ويتولّى ``tools_btc_regime`` اختبار كل
واحدة على حدة.

═══ قاعدة عدم إعادة الرسم ═══

كل خاصية عند الشمعة ``i`` تُحسب من ``[0..i]`` حصراً. أي استعمال لبيانات
لاحقة يجعل النتائج ممتازة في الاختبار ومستحيلة في التشغيل — وهو أشيع
أخطاء هذا النوع من العمل وأصعبها اكتشافاً، لأنه لا يظهر كعُطل بل
كنجاح باهر.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# أسماء الخصائص وشرحها — تُعرض في اللوحة وتُستعمل مفاتيح في النموذج
FEATURES: dict[str, str] = {
    "ret_1": "عائد الشمعة الأخيرة",
    "ret_6": "عائد ست شموع",
    "ret_24": "عائد أربع وعشرين شمعة",
    "trend": "الاتجاه: فوق/تحت متوسط 50 و200",
    "dist_ema50": "البعد عن متوسط 50 بوحدات ATR",
    "dist_ema200": "البعد عن متوسط 200 بوحدات ATR",
    "atr_pct": "التقلّب: ATR نسبةً إلى السعر",
    "atr_ratio": "التقلّب الآن مقابل متوسطه",
    "range_squeeze": "ضيق المدى مقابل المعتاد",
    "rsi": "القوة النسبية",
    "vol_ratio": "الحجم مقابل متوسطه",
    "up_bars": "نسبة الشموع الصاعدة في آخر 24",
    "drawdown": "الانخفاض عن أعلى قمة في 100 شمعة",
}


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    """متوسط أسّي متّجه — بذرة من أول قيمة صالحة."""
    out = np.full(x.size, np.nan)
    if x.size == 0:
        return out
    alpha = 2.0 / (span + 1.0)
    prev = x[0]
    out[0] = prev
    for i in range(1, x.size):
        v = x[i]
        prev = v if np.isnan(prev) else (alpha * v + (1 - alpha) * prev)
        out[i] = prev
    return out


def _rma(x: np.ndarray, length: int) -> np.ndarray:
    out = np.full(x.size, np.nan)
    if x.size < length:
        return out
    seed = np.nanmean(x[:length])
    prev = seed
    out[length - 1] = seed
    a = 1.0 / length
    for i in range(length, x.size):
        prev = a * x[i] + (1 - a) * prev
        out[i] = prev
    return out


def build(df: pd.DataFrame) -> pd.DataFrame:
    """خصائص حالة السوق لكل شمعة — كلها من الماضي فقط.

    يُعاد إطار بنفس فهرس ``df`` وأعمدة ``FEATURES``. الصفوف الأولى فيها
    ``NaN`` لأن المتوسطات الطويلة لم تكتمل بعد — وتركها فارغة أصدق من
    ملئها بقيمة مخترعة.
    """
    if df is None or len(df) < 5:
        return pd.DataFrame(columns=list(FEATURES))
    need = {"open", "high", "low", "close"}
    if not need <= set(df.columns):
        return pd.DataFrame(columns=list(FEATURES))

    c = df["close"].to_numpy(dtype="float64")
    h = df["high"].to_numpy(dtype="float64")
    lo = df["low"].to_numpy(dtype="float64")
    v = (df["volume"].to_numpy(dtype="float64")
         if "volume" in df.columns else np.zeros_like(c))
    n = c.size
    out: dict[str, np.ndarray] = {}

    def shift_ratio(arr: np.ndarray, k: int) -> np.ndarray:
        r = np.full(n, np.nan)
        if n > k:
            r[k:] = arr[k:] / arr[:-k] - 1.0
        return r * 100.0

    out["ret_1"] = shift_ratio(c, 1)
    out["ret_6"] = shift_ratio(c, 6)
    out["ret_24"] = shift_ratio(c, 24)

    ema50, ema200 = _ema(c, 50), _ema(c, 200)
    # الاتجاه: ‎+1‎ فوق الاثنين · ‎−1‎ تحتهما · 0 مختلط
    trend = np.zeros(n)
    trend[(c > ema50) & (c > ema200)] = 1.0
    trend[(c < ema50) & (c < ema200)] = -1.0
    out["trend"] = trend

    prev_c = np.concatenate(([np.nan], c[:-1]))
    tr = np.nanmax(np.vstack([h - lo, np.abs(h - prev_c),
                              np.abs(lo - prev_c)]), axis=0)
    atr = _rma(tr, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["atr_pct"] = atr / c * 100.0
        out["dist_ema50"] = (c - ema50) / atr
        out["dist_ema200"] = (c - ema200) / atr
        atr_mean = pd.Series(atr).rolling(100, min_periods=20).mean().to_numpy()
        out["atr_ratio"] = atr / atr_mean
        rng = h - lo
        rng_mean = pd.Series(rng).rolling(20, min_periods=5).mean().to_numpy()
        out["range_squeeze"] = rng / rng_mean
        vol_mean = pd.Series(v).rolling(20, min_periods=5).mean().to_numpy()
        out["vol_ratio"] = np.where(vol_mean > 0, v / vol_mean, np.nan)

    delta = np.concatenate(([np.nan], np.diff(c)))
    gain = _rma(np.where(delta > 0, delta, 0.0), 14)
    loss = _rma(np.where(delta < 0, -delta, 0.0), 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = gain / loss
        out["rsi"] = 100.0 - 100.0 / (1.0 + rs)

    up = (delta > 0).astype("float64")
    out["up_bars"] = pd.Series(up).rolling(24, min_periods=6).mean().to_numpy()

    peak = pd.Series(c).rolling(100, min_periods=20).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["drawdown"] = (c / peak - 1.0) * 100.0

    frame = pd.DataFrame({k: out[k] for k in FEATURES}, index=df.index)
    return frame.replace([np.inf, -np.inf], np.nan)


def at(features: pd.DataFrame, when) -> dict:
    """حالة السوق عند وقت محدَّد — **آخر شمعة أغلقت قبله**.

    ``searchsorted(...,'right') - 1`` مقصود: الشمعة التي وقتها يساوي
    ``when`` تكون قد أُغلقت عند ذلك الوقت في اصطلاح هذا المشروع (الفهرس
    وقت الافتتاح، والقرار على الإغلاق). استعمال الشمعة **التالية** —
    وهو خطأ إزاحة بمقدار واحد — يسرّب المستقبل ويجعل كل نتيجة لاحقة
    بلا قيمة.
    """
    if features is None or features.empty:
        return {}
    ts = pd.Timestamp(when)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    idx = features.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    pos = int(idx.searchsorted(ts, side="right")) - 1
    if pos < 0 or pos >= len(features):
        return {}
    row = features.iloc[pos]
    return {k: (None if pd.isna(row[k]) else float(row[k])) for k in FEATURES}


def label_direction(df: pd.DataFrame, horizon: int = 1) -> np.ndarray:
    """هل أغلقت الشمعة بعد ``horizon`` أعلى من الحالية؟ ‎1‎ نعم · ‎0‎ لا.

    آخر ``horizon`` صفّاً تُترك ``NaN``: نتيجتها لم تقع بعد، وملؤها
    بأي قيمة يعلّم النموذج شيئاً لم يحدث.
    """
    c = df["close"].to_numpy(dtype="float64")
    y = np.full(c.size, np.nan)
    if c.size > horizon:
        y[:-horizon] = (c[horizon:] > c[:-horizon]).astype("float64")
    return y
