"""عدّ موجات إليوت — بقيود صارمة واعتراف صريح بحدوده.

تحذير يجب أن يُقرأ قبل الاستخدام:
عدّ الموجات اجتهادي بطبيعته. محلّلان خبيران يعطيان العدّ نفسه عدّاً مختلفاً
على الشارت نفسه، والعدّ يتغيّر أثراً رجعياً كلما تكوّنت موجة جديدة. أي أداة
تدّعي عدّاً قاطعاً تبيع وهماً.

ما تفعله هذه الوحدة: تختبر آخر خمس نقاط هيكلية على قواعد إليوت الثلاث
غير القابلة للكسر، وتعطي نتيجة مع درجة ثقة. إن سقطت أي قاعدة فلا عدّ —
لا "عدّ ضعيف". القواعد:

  1. الموجة الثانية لا تصحّح أكثر من 100% من الأولى
  2. الموجة الثالثة ليست أقصر الموجات الدافعة الثلاث
  3. الموجة الرابعة لا تتداخل مع نطاق الموجة الأولى

والنسب المفضّلة (لا الملزمة) تُستخدم لرفع الثقة لا لإسقاط العدّ.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..indicators.structure import Structure


@dataclass
class WaveCount:
    direction: int              # 1 دافعة صاعدة، -1 دافعة هابطة
    waves: list[float]          # أسعار النقاط الست (0..5)
    current_wave: int           # رقم الموجة الجارية
    confidence: float           # 0-1
    notes: list[str]
    next_target: float | None
    invalidation: float | None  # المستوى الذي يُلغي العدّ
    offset: int = 0             # كم نقطة يبعد نهاية العدّ عن الحاضر
    bar_indices: list[int] = field(default_factory=list)   # مواضع النقاط الست
    is_high: list[bool] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "current_wave": self.current_wave,
            "confidence": round(self.confidence, 2),
            "notes": self.notes,
            "next_target": self.next_target,
            "invalidation": self.invalidation,
            "offset": self.offset,
            "bar_indices": self.bar_indices,
            "label": self.label,
        }

    @property
    def label(self) -> str:
        d = "صاعدة" if self.direction == 1 else "هابطة"
        if self.current_wave == 0:
            return f"تصحيح بعد دافعة {d}"
        return f"الموجة {self.current_wave} ({d})"


FIB = (0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618, 2.618)


def _closest_fib(ratio: float) -> tuple[float, float]:
    """أقرب نسبة فيبوناتشي ومدى القرب منها (0-1)."""
    if not np.isfinite(ratio) or ratio <= 0:
        return 0.0, 0.0
    best = min(FIB, key=lambda f: abs(f - ratio))
    closeness = max(0.0, 1.0 - abs(best - ratio) / max(best, 0.1))
    return best, closeness


def _validate(prices: list[float], direction: int) -> tuple[bool, float, list[str]]:
    """يفحص نافذة من ست نقاط. يعيد (صالحة، ثقة، ملاحظات)."""
    p0, p1, p2, p3, p4, p5 = prices
    w1, w2, w3 = abs(p1 - p0), abs(p2 - p1), abs(p3 - p2)
    w4, w5 = abs(p4 - p3), abs(p5 - p4)
    if min(w1, w3, w5) <= 0:
        return False, 0.0, []

    # القواعد الثلاث غير القابلة للكسر
    if direction == 1 and p2 <= p0:
        return False, 0.0, []
    if direction == -1 and p2 >= p0:
        return False, 0.0, []
    if w3 < w1 and w3 < w5:
        return False, 0.0, []
    if direction == 1 and p4 <= p1:
        return False, 0.0, []
    if direction == -1 and p4 >= p1:
        return False, 0.0, []

    notes = ["القواعد الثلاث الأساسية مستوفاة"]
    confidence = 0.5

    fib2, close2 = _closest_fib(w2 / w1)
    if close2 > 0.85:
        confidence += 0.12
        notes.append(f"تصحيح الموجة 2 قرب {fib2:.3f}".rstrip("0").rstrip("."))

    r3 = w3 / w1
    if r3 >= 1.5:
        confidence += 0.15
        notes.append(f"امتداد الموجة 3 = {r3:.2f}× الأولى")
    elif _closest_fib(r3)[1] > 0.85:
        confidence += 0.08

    fib4, close4 = _closest_fib(w4 / w3)
    if close4 > 0.85:
        confidence += 0.1
        notes.append(f"تصحيح الموجة 4 قرب {fib4:.3f}".rstrip("0").rstrip("."))

    if w3 >= max(w1, w5):
        confidence += 0.1
        notes.append("الموجة 3 هي الأطول — الشكل النموذجي")

    return True, min(1.0, confidence), notes


def count(structure: Structure, close: float, min_confidence: float = 0.4,
          max_windows: int = 14) -> WaveCount | None:
    """يبحث عن أفضل عدّ صالح عبر تاريخ النقاط، لا في آخر ست فقط.

    كان الفحص مقتصراً على آخر ست نقاط، وهي في الغالب تذبذب داخل موجة
    أكبر — فلا يُعثر على عدّ صالح أبداً رغم وجوده. الآن نمسح النوافذ
    من الأحدث للأقدم ونأخذ أعلاها ثقة، مع تفضيل الأحدث عند التساوي.
    """
    pv = structure.pivots
    if len(pv) < 6:
        return None

    best: WaveCount | None = None
    best_key = (-1.0, -1)

    limit = min(max_windows, len(pv) - 5)
    for back in range(limit):
        end = len(pv) - back
        window = pv[end - 6:end]
        flags = [x.is_high for x in window]
        prices = [x.price for x in window]

        up = flags == [False, True, False, True, False, True]
        down = flags == [True, False, True, False, True, False]
        if not (up or down):
            continue

        direction = 1 if up else -1
        valid, confidence, notes = _validate(prices, direction)
        if not valid or confidence < min_confidence:
            continue

        # الحداثة أثقل من الثقة: عدّ ينتهي قبل عشرين نقطة قد يكون
        # مثالياً شكلياً ولا يفيد قرار اليوم في شيء
        recency = 1.0 - back / max(limit, 1)
        key = (confidence * 0.4 + recency * 0.6, -back)
        if key <= best_key:
            continue

        p0, p1, p2, p3, p4, p5 = prices
        w3 = abs(p3 - p2)
        if direction == 1:
            completed = close < p4
            target = p5 + w3 * 0.382
        else:
            completed = close > p4
            target = p5 - w3 * 0.382

        current = 5
        local_notes = list(notes)
        if completed:
            current = 0
            local_notes.append("الدافعة الخماسية اكتملت — تصحيح جارٍ")
            target = p2
        if back > 0:
            local_notes.append(f"العدّ ينتهي قبل {back} نقطة من الحاضر")

        best_key = key
        best = WaveCount(
            direction=direction, waves=prices, current_wave=current,
            confidence=confidence, notes=local_notes,
            next_target=float(target), invalidation=float(p4),
            offset=back,
            bar_indices=[x.index for x in window],
            is_high=[x.is_high for x in window],
        )

    return best
