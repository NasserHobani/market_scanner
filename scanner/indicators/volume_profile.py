# -*- coding: utf-8 -*-
"""فوليوم بروفايل و VWAP المثبَّت — الحجم على السعر لا على الزمن.

═══ الفكرة ═══

الشارت المعتاد يرسم الحجم تحت كل شمعة: «كم تُودُوِل في هذه **اللحظة**».
والفوليوم بروفايل يقلب السؤال: «كم تُودُوِل عند هذا **السعر**».

والفرق عمليّ لا نظريّ. السعر الذي تبادل عنده أكبر حجم — ``POC`` —
هو السعر الذي اتّفق عليه أكثر المشترين والبائعين. ومنطقة القيمة
``VAH``–``VAL`` هي حيث دار سبعون بالمئة من التداول: نطاق ما اعتُبر
سعراً عادلاً.

وما بينهما من مستويات ضعيفة الحجم (``LVN``) مناطق عبور لا توقّف:
السعر يمرّ بها سريعاً لأن لا أحد يريد التداول عندها.

═══ ولماذا هذا الملف موجود أصلاً ═══

كان في النظام ``session_vwap`` تقول::

    day = df.index.floor("D")

أي أن الجلسة يومٌ تقويميّ. وهذا صحيح على فريم الدقائق، وينهار على
الفريم اليومي: كل شمعة جلسةٌ وحدها، فيصير VWAP مساوياً لـ
``(H+L+C)/3`` **لتلك الشمعة**.

والقياس على بياناتك::

    crypto 1d   VWAP == (H+L+C)/3 في 100.0٪ من الشموع
    saudi  1d   VWAP == (H+L+C)/3 في  95.6٪ من الشموع
    crypto 15m  VWAP == (H+L+C)/3 في   1.2٪ من الشموع

فالمكوّن يحمل وزناً في التقييم ويقيس شيئاً آخر تماماً عمّا يدّعيه:
لا «أين السعر من متوسّط المتداولين» بل «أين أغلق داخل مداه». وهذا
أخطر من مؤشّر غائب: الغائب يُنتبَه إليه، والمسمّى بغير اسمه يُبنى
عليه القرار.

والسوق السعودي كلّه يُمسَح على ``1d``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# نسبة الحجم التي تعرّف «منطقة القيمة». السبعون عرفٌ راسخ في
# ‏Market Profile — وهي انحرافٌ معياريّ واحد تقريباً لو كان التوزيع
# طبيعياً. تُترك قابلة للتعديل ولا تُغيَّر بلا قياس.
VALUE_AREA_PCT = 0.70

# عدد شرائح السعر. قليلها يُخشّن الصورة ويُضيّع الـPOC، وكثيرها
# يُشتّت الحجم على شرائح فارغة فيصير الـPOC ضجيجاً.
DEFAULT_BINS = 48


@dataclass(frozen=True)
class Profile:
    """نتيجة الفوليوم بروفايل — كل الأسعار بوحدة السعر."""

    poc: float                  # أكثر سعر تداولاً
    vah: float                  # أعلى منطقة القيمة
    val: float                  # أدنى منطقة القيمة
    high: float
    low: float
    bins: int
    hvn: tuple[float, ...]      # عُقد حجم عالية — توقّف محتمل
    lvn: tuple[float, ...]      # عُقد حجم منخفضة — عبور سريع
    total_volume: float

    @property
    def value_width(self) -> float:
        return max(0.0, self.vah - self.val)

    def position(self, price: float) -> str:
        """أين السعر من منطقة القيمة — بالعربية، للعرض والتفسير."""
        if price > self.vah:
            return "فوق منطقة القيمة"
        if price < self.val:
            return "تحت منطقة القيمة"
        return "داخل منطقة القيمة"


def build(df: pd.DataFrame, bins: int = DEFAULT_BINS,
          value_area: float = VALUE_AREA_PCT) -> Profile | None:
    """يبني البروفايل من الشموع المعطاة. ``None`` إن تعذّر.

    ═══ لماذا يُوزَّع حجم الشمعة على مداها ═══

    الشمعة الواحدة تغطّي نطاقاً لا سعراً. ووضع حجمها كلّه عند
    الإغلاق يضع الحجم حيث لم يُتداول أكثره، ويُنتج ``POC`` عند
    مستوياتٍ عبَرَها السعر مروراً.

    فيُوزَّع حجم كل شمعة بالتساوي على الشرائح التي يلمسها مداها —
    وهو تقريب «‏TPO موزون بالحجم» المعتاد حين لا تتوفّر بيانات
    التكات. وهو ما يمكن بناؤه من شموع OHLCV، ولا نزعم أكثر.
    """
    if df is None or len(df) < 5:
        return None
    need = {"high", "low", "volume"}
    if not need.issubset(df.columns):
        return None

    hi = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    vol = df["volume"].to_numpy(dtype=float)
    ok = np.isfinite(hi) & np.isfinite(lo) & np.isfinite(vol) & (vol > 0)
    if not ok.any():
        return None
    hi, lo, vol = hi[ok], lo[ok], vol[ok]

    top, bottom = float(hi.max()), float(lo.min())
    if not np.isfinite(top) or not np.isfinite(bottom) or top <= bottom:
        return None

    bins = max(8, int(bins))
    edges = np.linspace(bottom, top, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    hist = np.zeros(bins, dtype=float)

    # توزيع حجم كل شمعة على الشرائح التي يلمسها مداها
    width = (top - bottom) / bins
    lo_idx = np.clip(((lo - bottom) / width).astype(int), 0, bins - 1)
    hi_idx = np.clip(((hi - bottom) / width).astype(int), 0, bins - 1)
    for i in range(len(vol)):
        a, b = lo_idx[i], hi_idx[i]
        span = b - a + 1
        hist[a:b + 1] += vol[i] / span

    total = float(hist.sum())
    if total <= 0:
        return None

    poc_i = int(np.argmax(hist))
    poc = float(centers[poc_i])

    # ═══ توسيع منطقة القيمة ═══
    #
    # الطريقة المعيارية: ابدأ من الـPOC وضُمّ في كل خطوة الجارَ
    # **الأثقل** من الجانبين حتى تبلغ النسبة. وضمّ الجانبين
    # بالتساوي يُنتج منطقةً متماثلة حول الـPOC — وهي ليست ما يقوله
    # السوق حين يكون التوزيع مائلاً.
    target = total * float(value_area)
    lo_i = hi_i = poc_i
    acc = hist[poc_i]
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        below = hist[lo_i - 1] if lo_i > 0 else -1.0
        above = hist[hi_i + 1] if hi_i < bins - 1 else -1.0
        if above >= below:
            hi_i += 1
            acc += hist[hi_i]
        else:
            lo_i -= 1
            acc += hist[lo_i]

    val, vah = float(centers[lo_i]), float(centers[hi_i])

    # عُقد الحجم: قمم وقيعان محلّية في التوزيع
    hvn, lvn = [], []
    mean = hist.mean()
    for i in range(1, bins - 1):
        if hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1] and hist[i] > mean * 1.3:
            hvn.append(float(centers[i]))
        elif hist[i] <= hist[i - 1] and hist[i] <= hist[i + 1] and hist[i] < mean * 0.4:
            lvn.append(float(centers[i]))

    return Profile(poc=poc, vah=vah, val=val, high=top, low=bottom,
                   bins=bins, hvn=tuple(hvn), lvn=tuple(lvn),
                   total_volume=total)


# ═══════════════════════════════ VWAP ═══════════════════════════════

def _typical(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3.0


def bars_per_session(df: pd.DataFrame) -> float:
    """كم شمعة في اليوم التقويمي — يقرّر أي VWAP له معنى."""
    if df is None or df.empty:
        return 0.0
    try:
        return float(df.groupby(df.index.floor("D")).size().median())
    except Exception:  # noqa: BLE001
        return 0.0


def rolling_vwap(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """‏VWAP متدحرج على آخر ``length`` شمعة.

    هذا ما يستعمله متداولو الفوليوم على الفريم اليومي: «متوسّط السعر
    الموزون بالحجم لآخر عشرين جلسة» — سؤالٌ له معنى، بخلاف VWAP
    جلسةٍ من شمعة واحدة.
    """
    tp = _typical(df)
    pv = (tp * df["volume"]).rolling(length, min_periods=2).sum()
    vv = df["volume"].rolling(length, min_periods=2).sum()
    return pv / vv.replace(0.0, np.nan)


def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """‏VWAP مثبَّت من شمعة بعينها إلى الآن.

    يُثبَّت عادةً على قاعٍ أو قمّةٍ مهمّة أو حدثٍ (أرباح، اختراق).
    ومعناه: «متوسّط ما دفعه كل من دخل منذ تلك اللحظة» — فعبوره
    يعني أن المشترين منذ الحدث صاروا في ربح أو خسارة جماعياً.
    """
    n = len(df)
    if n == 0:
        return pd.Series(dtype=float)
    a = max(0, min(int(anchor_idx), n - 1))
    tp = _typical(df)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    pv = (tp.iloc[a:] * df["volume"].iloc[a:]).cumsum()
    vv = df["volume"].iloc[a:].cumsum()
    out.iloc[a:] = (pv / vv.replace(0.0, np.nan)).to_numpy()
    return out


def anchor_swing(df: pd.DataFrame, lookback: int = 120,
                 mode: str = "low") -> int:
    """موضع أهمّ قاع/قمّة في آخر ``lookback`` شمعة — نقطة تثبيت."""
    if df is None or len(df) == 0:
        return 0
    w = df.iloc[-int(lookback):] if lookback else df
    col = "low" if mode == "low" else "high"
    fn = w[col].idxmin if mode == "low" else w[col].idxmax
    try:
        return int(df.index.get_loc(fn()))
    except Exception:  # noqa: BLE001
        return 0


def smart_vwap(df: pd.DataFrame, length: int = 20) -> pd.Series:
    """‏VWAP الذي **له معنى** على هذا الفريم.

    داخل اليوم (أكثر من شمعتين في الجلسة): VWAP الجلسة كما هو
    متعارف. وعلى اليومي فأعلى: متدحرج على ``length`` جلسة.

    والاختيار من البيانات لا من اسم الفريم: مصدرٌ ناقص الشموع قد
    يعطي «1h» بشمعتين في اليوم، والقاعدة يجب أن تتبع ما في اليد.
    """
    per_day = bars_per_session(df)
    if per_day >= 3.0:
        tp = _typical(df)
        day = df.index.floor("D")
        pv = (tp * df["volume"]).groupby(day).cumsum()
        vv = df["volume"].groupby(day).cumsum()
        return pv / vv.replace(0.0, np.nan)
    return rolling_vwap(df, length)


__all__ = ["Profile", "build", "rolling_vwap", "anchored_vwap",
           "anchor_swing", "smart_vwap", "bars_per_session",
           "VALUE_AREA_PCT", "DEFAULT_BINS"]
