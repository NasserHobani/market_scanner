"""هيكل السوق: زيجزاج، فيبوناتشي من الموجة الحقيقية، والقنوات السعرية.

منقول عن منطق مؤشر VDM: القمم والقيعان تُؤكَّد بنافذة على الجانبين،
وتُصفّى بحجم أدنى للموجة (× ATR) حتى لا يُبنى الهيكل على ضوضاء.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .pine import atr, pivot_high, pivot_low


@dataclass
class Pivot:
    index: int
    price: float
    is_high: bool


@dataclass
class Structure:
    pivots: list[Pivot]
    structure_high: float
    structure_low: float

    @property
    def last_high(self) -> float | None:
        for p in reversed(self.pivots):
            if p.is_high:
                return p.price
        return None

    @property
    def last_low(self) -> float | None:
        for p in reversed(self.pivots):
            if not p.is_high:
                return p.price
        return None


def build_structure(df: pd.DataFrame, length: int = 10,
                    min_swing_atr: float = 1.0, atr_len: int = 14) -> Structure:
    """زيجزاج بتناوب إجباري بين قمة وقاع، مع تصفية الموجات الصغيرة."""
    highs = pivot_high(df["high"], length, length)
    lows = pivot_low(df["low"], length, length)
    atr_series = atr(df, atr_len)

    # التحويل إلى مصفوفات مرّة واحدة بدل الفهرسة بالموضع داخل الحلقة.
    #
    # كان هنا ``highs.iloc[i]`` و``lows.iloc[i]`` لكل شمعة — أي أربع
    # عمليات فهرسة pandas لكل صفّ. القياس على 1628 شمعة: **21,117 نداء
    # فهرسة** في تحليل رمز واحد، وهي وحدها ربع زمن التحليل. والوصول
    # الفردي في pandas يمرّ بطبقات محاذاة وتحقّق لا لزوم لها هنا.
    h_vals = highs.to_numpy(dtype="float64")
    l_vals = lows.to_numpy(dtype="float64")
    a_vals = atr_series.to_numpy(dtype="float64")

    raw: list[Pivot] = []
    # المواضع غير NaN وحدها تُزار بدل المرور على كل الشموع
    for i in np.flatnonzero(~np.isnan(h_vals)):
        raw.append(Pivot(int(i), float(h_vals[i]), True))
    for i in np.flatnonzero(~np.isnan(l_vals)):
        raw.append(Pivot(int(i), float(l_vals[i]), False))
    # الترتيب مستقرّ: عند تساوي الموضع تسبق القمة القاع كما في الأصل،
    # حيث كان فحص القمة يأتي أولاً داخل الحلقة
    raw.sort(key=lambda p: (p.index, not p.is_high))

    pivots: list[Pivot] = []
    for p in raw:
        a = a_vals[p.index]
        threshold = 0.0 if np.isnan(a) else float(a) * min_swing_atr

        if not pivots:
            pivots.append(p)
            continue

        last = pivots[-1]
        if last.is_high == p.is_high:
            # نفس النوع مرتين: نبقي الأكثر تطرفاً بدل إضافة نقطة زائدة
            if (p.is_high and p.price > last.price) or (not p.is_high and p.price < last.price):
                pivots[-1] = p
            continue

        if abs(p.price - last.price) < threshold:
            continue  # موجة أصغر من الحد — ضوضاء
        pivots.append(p)

    sh = max((p.price for p in pivots if p.is_high), default=float(df["high"].max()))
    sl = min((p.price for p in pivots if not p.is_high), default=float(df["low"].min()))
    last_h = next((p.price for p in reversed(pivots) if p.is_high), sh)
    last_l = next((p.price for p in reversed(pivots) if not p.is_high), sl)
    return Structure(pivots=pivots, structure_high=last_h, structure_low=last_l)


# --------------------------------------------------------------- فيبوناتشي

FIB_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)


def fib_levels(high: float, low: float) -> dict[float, float]:
    diff = high - low
    return {r: high - diff * r for r in FIB_RATIOS}


def fib_confluence(close: float, levels: dict[float, float], tolerance: float,
                   key_only: bool = True) -> tuple[bool, float | None]:
    """هل السعر عند مستوى فيبو رئيسي؟ يعيد (نعم/لا، النسبة)."""
    ratios = (0.382, 0.5, 0.618) if key_only else FIB_RATIOS
    for r in ratios:
        lvl = levels.get(r)
        if lvl is not None and abs(close - lvl) <= tolerance:
            return True, r
    return False, None


# ------------------------------------------------------------------ القناة

@dataclass
class Channel:
    kind: str            # rising | falling | flat
    anchor_index: int
    anchor_low: float
    slope: float
    height: float
    touches: int
    contain_pct: float

    def bounds_at(self, index: int) -> tuple[float, float]:
        low = self.anchor_low + self.slope * (index - self.anchor_index)
        return low, low + self.height

    def zone_at(self, index: int, close: float) -> str:
        low, up = self.bounds_at(index)
        third = self.height / 3.0
        if close <= low + third:
            return "buy"
        if close >= up - third:
            return "sell"
        return "neutral"


def detect_channel(df: pd.DataFrame, structure: Structure, atr_value: float,
                   flat_atr: float = 0.5, tol_atr: float = 0.35,
                   min_bars: int = 30, min_touches: int = 4,
                   min_contain: float = 75.0) -> Channel | None:
    """قناة من ثلاث نقاط (قاع-قمة-قاع أو قمة-قاع-قمة)، أو أفقية من أربع.

    لا تُعتمد إلا بعد اجتياز اختبارات الطول واللمسات والاحتواء.
    """
    pv = structure.pivots
    if len(pv) < 3 or atr_value <= 0 or np.isnan(atr_value):
        return None

    last = len(df) - 1
    flat_tol = atr_value * flat_atr
    p0, p1, p2 = pv[-1], pv[-2], pv[-3]

    kind = anchor = anchor_low = slope = height = None

    # أفقية: قمتان متقاربتان وقاعان متقاربان
    if len(pv) >= 4:
        p3 = pv[-4]
        his = [p.price for p in (p0, p1, p2, p3) if p.is_high]
        los = [p.price for p in (p0, p1, p2, p3) if not p.is_high]
        if len(his) == 2 and len(los) == 2:
            if abs(his[0] - his[1]) <= flat_tol and abs(los[0] - los[1]) <= flat_tol:
                kind, anchor = "flat", p3.index
                anchor_low = sum(los) / 2
                slope, height = 0.0, sum(his) / 2 - anchor_low

    # صاعدة: قاع - قمة - قاع، والقاع الأحدث أعلى
    if kind is None and not p0.is_high and p1.is_high and not p2.is_high:
        if p0.price > p2.price and (p0.price - p2.price) > flat_tol and p0.index > p2.index:
            s = (p0.price - p2.price) / (p0.index - p2.index)
            low_at_mid = p2.price + s * (p1.index - p2.index)
            if p1.price > low_at_mid:
                kind, anchor, anchor_low = "rising", p2.index, p2.price
                slope, height = s, p1.price - low_at_mid

    # هابطة: قمة - قاع - قمة، والقمة الأحدث أدنى
    if kind is None and p0.is_high and not p1.is_high and p2.is_high:
        if p0.price < p2.price and (p2.price - p0.price) > flat_tol and p0.index > p2.index:
            s = (p0.price - p2.price) / (p0.index - p2.index)
            high_at_mid = p2.price + s * (p1.index - p2.index)
            if p1.price < high_at_mid:
                h = high_at_mid - p1.price
                kind, anchor, slope, height = "falling", p2.index, s, h
                anchor_low = p2.price - h

    if kind is None or height is None or height <= 0:
        return None

    span = last - anchor
    if span < min_bars:
        return None

    idx = np.arange(max(anchor, 0), last + 1)
    lows_line = anchor_low + slope * (idx - anchor)
    ups_line = lows_line + height
    tol = atr_value * tol_atr

    lo = df["low"].to_numpy()[idx]
    hi = df["high"].to_numpy()[idx]
    cl = df["close"].to_numpy()[idx]

    touch_lo = int(np.sum((lo <= lows_line + tol) & (lo >= lows_line - tol * 2)))
    touch_hi = int(np.sum((hi >= ups_line - tol) & (hi <= ups_line + tol * 2)))
    inside = int(np.sum((cl <= ups_line + tol) & (cl >= lows_line - tol)))
    contain = inside / len(idx) * 100.0

    if touch_lo < 1 or touch_hi < 1:
        return None
    if (touch_lo + touch_hi) < min_touches or contain < min_contain:
        return None

    return Channel(kind, anchor, float(anchor_low), float(slope), float(height),
                   touch_lo + touch_hi, contain)


# -------------------------------------------------------------- الدايفرجنس

def detect_divergence(df: pd.DataFrame, oscillators: dict[str, pd.Series],
                      pivot_len: int = 5, max_bars: int = 60,
                      active_bars: int | None = None) -> tuple[bool, bool]:
    """انحراف السعر عن المذبذبات. يعيد (صاعد، هابط)."""
    if active_bars is None:
        active_bars = max_bars // 2

    lows = pivot_low(df["low"], pivot_len, pivot_len)
    highs = pivot_high(df["high"], pivot_len, pivot_len)
    last = len(df) - 1

    def _scan(pivots: pd.Series, bullish: bool) -> bool:
        idx = np.flatnonzero(~np.isnan(pivots.to_numpy()))
        if len(idx) < 2:
            return False
        b, a = idx[-1], idx[-2]
        if (b - a) > max_bars or (last - b) > active_bars:
            return False
        pb, pa = float(pivots.iloc[b]), float(pivots.iloc[a])
        price_ok = pb < pa if bullish else pb > pa
        if not price_ok:
            return False
        for series in oscillators.values():
            ob, oa = series.iloc[b], series.iloc[a]
            if np.isnan(ob) or np.isnan(oa):
                continue
            if (ob > oa) if bullish else (ob < oa):
                return True
        return False

    return _scan(lows, True), _scan(highs, False)
