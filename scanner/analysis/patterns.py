"""النماذج السعرية الكلاسيكية، مبنية على قمم وقيعان الزيجزاج المؤكدة.

لا تُبنى على أسعار خام: النموذج تعريفه علاقة بين نقاط انعكاس، والزيجزاج
هو ما يحوّل الضوضاء إلى نقاط. لذلك دقّة النموذج مقيّدة بدقّة الهيكل.

كل نموذج يحمل ثقة (0-1) لا "موجود/غير موجود"، لأن التماثل التام نادر
في السوق الحقيقي والعتبة الصارمة تُسقط نماذج صحيحة.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..indicators.structure import Pivot, Structure


@dataclass
class ChartPattern:
    name: str
    arabic: str
    direction: int          # 1 صاعد، -1 هابط، 0 محايد
    confidence: float       # 0-1
    neckline: float | None  # مستوى التأكيد
    target: float | None    # الهدف المقاس
    start_index: int
    end_index: int

    def as_dict(self) -> dict:
        return {
            "name": self.name, "arabic": self.arabic, "direction": self.direction,
            "confidence": round(self.confidence, 2), "neckline": self.neckline,
            "target": self.target,
        }


def _similar(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _confidence(values: list[float], tol: float) -> float:
    """كلما تقاربت النقاط زادت الثقة."""
    if len(values) < 2 or tol <= 0:
        return 0.0
    spread = max(values) - min(values)
    return float(max(0.0, min(1.0, 1.0 - spread / (tol * 2))))


def detect(structure: Structure, df: pd.DataFrame, atr_value: float,
           tol_atr: float = 0.6, min_confidence: float = 0.35) -> list[ChartPattern]:
    pv = structure.pivots
    if len(pv) < 4 or atr_value <= 0 or np.isnan(atr_value):
        return []

    tol = atr_value * tol_atr
    found: list[ChartPattern] = []
    last = len(df) - 1

    highs = [p for p in pv if p.is_high]
    lows = [p for p in pv if not p.is_high]

    # ── قمة مزدوجة / قاع مزدوج ─────────────────────────────────
    # قمتان متساويتان مع قيعان صاعدة = مثلث صاعد لا قمة مزدوجة.
    # الفارق في القيعان لا في القمم، وهو ما يقلب اتجاه النموذج تماماً.
    rising_lows = len(lows) >= 2 and lows[-1].price > lows[-2].price + tol * 0.5
    falling_highs = len(highs) >= 2 and highs[-1].price < highs[-2].price - tol * 0.5

    # قمتان متساويتان وقاعان متساويان معاً = نطاق عرضي.
    # قراءتهما كقمة مزدوجة وقاع مزدوج تعطي إشارتين متعاكستين تُلغيان بعضهما.
    flat_range = (
        len(highs) >= 2 and len(lows) >= 2
        and _similar(highs[-1].price, highs[-2].price, tol)
        and _similar(lows[-1].price, lows[-2].price, tol)
    )
    if flat_range:
        top = (highs[-1].price + highs[-2].price) / 2
        bottom = (lows[-1].price + lows[-2].price) / 2
        found.append(ChartPattern(
            "rectangle", "نطاق عرضي", 0,
            _confidence([highs[-1].price, highs[-2].price], tol) * 0.9,
            bottom, top, min(highs[-2].index, lows[-2].index), last))

    if len(highs) >= 2 and len(lows) >= 1 and not rising_lows and not flat_range:
        h1, h2 = highs[-2], highs[-1]
        mid = [p for p in lows if h1.index < p.index < h2.index]
        if mid and _similar(h1.price, h2.price, tol):
            neck = mid[0].price
            conf = _confidence([h1.price, h2.price], tol)
            height = (h1.price + h2.price) / 2 - neck
            if conf >= min_confidence and height > 0:
                found.append(ChartPattern(
                    "double_top", "قمة مزدوجة", -1, conf, neck, neck - height,
                    h1.index, h2.index))

    if len(lows) >= 2 and len(highs) >= 1 and not falling_highs and not flat_range:
        l1, l2 = lows[-2], lows[-1]
        mid = [p for p in highs if l1.index < p.index < l2.index]
        if mid and _similar(l1.price, l2.price, tol):
            neck = mid[0].price
            conf = _confidence([l1.price, l2.price], tol)
            height = neck - (l1.price + l2.price) / 2
            if conf >= min_confidence and height > 0:
                found.append(ChartPattern(
                    "double_bottom", "قاع مزدوج", 1, conf, neck, neck + height,
                    l1.index, l2.index))

    # ── الرأس والكتفين ─────────────────────────────────────────
    if len(highs) >= 3 and len(lows) >= 2:
        s1, head, s2 = highs[-3], highs[-2], highs[-1]
        necks = [p for p in lows if s1.index < p.index < s2.index]
        if len(necks) >= 2 and head.price > s1.price and head.price > s2.price:
            if _similar(s1.price, s2.price, tol * 1.5):
                neck = (necks[-2].price + necks[-1].price) / 2
                conf = _confidence([s1.price, s2.price], tol * 1.5) * 0.9
                height = head.price - neck
                if conf >= min_confidence and height > 0:
                    found.append(ChartPattern(
                        "head_shoulders", "رأس وكتفان", -1, conf, neck,
                        neck - height, s1.index, s2.index))

    if len(lows) >= 3 and len(highs) >= 2:
        s1, head, s2 = lows[-3], lows[-2], lows[-1]
        necks = [p for p in highs if s1.index < p.index < s2.index]
        if len(necks) >= 2 and head.price < s1.price and head.price < s2.price:
            if _similar(s1.price, s2.price, tol * 1.5):
                neck = (necks[-2].price + necks[-1].price) / 2
                conf = _confidence([s1.price, s2.price], tol * 1.5) * 0.9
                height = neck - head.price
                if conf >= min_confidence and height > 0:
                    found.append(ChartPattern(
                        "inv_head_shoulders", "رأس وكتفان مقلوب", 1, conf, neck,
                        neck + height, s1.index, s2.index))

    # ── المثلثات والأوتاد ──────────────────────────────────────
    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = highs[-2], highs[-1]
        l1, l2 = lows[-2], lows[-1]
        flat_high = _similar(h1.price, h2.price, tol)
        flat_low = _similar(l1.price, l2.price, tol)
        falling_high = h2.price < h1.price - tol * 0.5
        rising_low = l2.price > l1.price + tol * 0.5

        span = max(1, last - min(h1.index, l1.index))
        base_conf = float(min(1.0, span / 60.0)) * 0.8 + 0.2

        if flat_high and rising_low:
            found.append(ChartPattern(
                "ascending_triangle", "مثلث صاعد", 1, base_conf,
                (h1.price + h2.price) / 2,
                (h1.price + h2.price) / 2 + (h1.price - l1.price),
                min(h1.index, l1.index), last))
        elif flat_low and falling_high:
            found.append(ChartPattern(
                "descending_triangle", "مثلث هابط", -1, base_conf,
                (l1.price + l2.price) / 2,
                (l1.price + l2.price) / 2 - (h1.price - l1.price),
                min(h1.index, l1.index), last))
        elif falling_high and rising_low:
            found.append(ChartPattern(
                "symmetric_triangle", "مثلث متماثل", 0, base_conf * 0.8,
                (h2.price + l2.price) / 2, None,
                min(h1.index, l1.index), last))
        elif falling_high and (l2.price < l1.price - tol * 0.5):
            # قمم وقيعان هابطة معاً وتضيق المسافة = وتد هابط، انعكاسه صاعد غالباً
            if (h1.price - l1.price) > (h2.price - l2.price):
                found.append(ChartPattern(
                    "falling_wedge", "وتد هابط", 1, base_conf * 0.8,
                    h2.price, h2.price + (h1.price - l1.price),
                    min(h1.index, l1.index), last))
        elif rising_low and (h2.price > h1.price + tol * 0.5):
            if (h1.price - l1.price) > (h2.price - l2.price):
                found.append(ChartPattern(
                    "rising_wedge", "وتد صاعد", -1, base_conf * 0.8,
                    l2.price, l2.price - (h1.price - l1.price),
                    min(h1.index, l1.index), last))

    return _resolve(found)


# النموذج الأكثر تحديداً يلغي الأعم منه على النقاط نفسها.
# بدون هذا: قمتان متساويتان تُقرأان "قمة مزدوجة" و"مثلث صاعد" معاً،
# واتجاهاهما متعاكسان فيلغي أحدهما الآخر في الحساب.
SPECIFICITY = {
    "head_shoulders": 3, "inv_head_shoulders": 3,
    "rectangle": 2,
    "double_top": 2, "double_bottom": 2,
    "ascending_triangle": 1, "descending_triangle": 1,
    "symmetric_triangle": 1, "rising_wedge": 1, "falling_wedge": 1,
}


def _overlaps(a: ChartPattern, b: ChartPattern) -> bool:
    return not (a.end_index < b.start_index or b.end_index < a.start_index)


def _resolve(found: list[ChartPattern]) -> list[ChartPattern]:
    found.sort(key=lambda p: (SPECIFICITY.get(p.name, 0), p.confidence), reverse=True)
    kept: list[ChartPattern] = []
    for pat in found:
        if any(_overlaps(pat, k) and SPECIFICITY.get(k.name, 0) > SPECIFICITY.get(pat.name, 0)
               for k in kept):
            continue
        kept.append(pat)
    kept.sort(key=lambda p: p.confidence, reverse=True)
    return kept


def summarize(patterns: list[ChartPattern]) -> dict:
    if not patterns:
        return {"patterns": [], "score": 0, "best": None}
    best = patterns[0]
    bulls = sum(p.confidence for p in patterns if p.direction == 1)
    bears = sum(p.confidence for p in patterns if p.direction == -1)
    score = 1 if bulls > bears + 0.2 else -1 if bears > bulls + 0.2 else 0
    return {
        "patterns": [p.as_dict() for p in patterns],
        "score": score,
        "best": best.as_dict(),
    }
