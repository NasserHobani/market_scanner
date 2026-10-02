# -*- coding: utf-8 -*-
"""مناطق ارتدادٍ تاريخية — ومعها ما جرى بعد كل لمسة.

═══ المسألة ═══

«أفضل موضع دخول» تُقرأ غالباً: أين ارتدّ السعر من قبل؟ وهو سؤالٌ
مشروع — لكنّ جوابه يصير خرافةً بسهولة: ترسم خطّاً تحت كل قاعٍ
وتقول «دعمٌ قويّ»، وتنسى المرّات التي اخترقه فيها.

فالمنطقة هنا لا تُقبَل بلمسةٍ ولا لمستين. تُعدّ لمساتُها كلّها،
وتُوسَم كلّ لمسةٍ بنتيجتها بالحاجزين — فتصير «ارتدّ ٧ من ١١»
لا «دعمٌ قويّ».

═══ والتجميع بـ‏ATR لا بنسبةٍ مئوية ═══

قاعان يفصلهما ٠٫٣٪ منطقةٌ واحدة في رمزٍ هادئ، وشيئان مختلفان في
رمزٍ يتحرّك ٨٪ يومياً. والمسافة بـ‏ATR تعني الشيء نفسه في
الاثنين.

═══ وما لا تدّعيه ═══

«ارتدّ ٧ من ١١» ليست «يرتدّ ٦٤٪ من المرّات القادمة». إحدى عشرة
لمسة عيّنةٌ صغيرة، وفاصلُها الواسع معروضٌ بجانبها — وهو الذي
يقول كم تعرف فعلاً.

ولا تُرتَّب المناطق بالنسبة وحدها: منطقةٌ ٣ من ٣ تتصدّر كل شيء
وهي لا تعني شيئاً. فالترتيب بالحدّ الأدنى للفاصل — أي بأسوأ ما
تحتمله البيانات.
"""
from __future__ import annotations

import math

import numpy as np

from .labels import LOSS, OPEN, WIN

__all__ = ["pivots", "build", "MIN_TOUCHES"]

#: أقلّ عدد لمساتٍ قبل عرض منطقة
MIN_TOUCHES = 4
#: نصف عرض المنطقة بمضاعف ATR
ZONE_ATR = 0.5
#: كم شمعةً على كلّ جانبٍ تصنع قاعاً
PIVOT_SPAN = 3

Z95 = 1.959963985


def _wilson(k: int, n: int) -> tuple[float, float, float]:
    if n <= 0:
        return (0.0, 0.0, 100.0)
    p = k / n
    d = 1 + Z95 * Z95 / n
    c = (p + Z95 * Z95 / (2 * n)) / d
    h = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * max(0.0, c - h), 1),
            round(100 * min(1.0, c + h), 1))


def pivots(low: np.ndarray, span: int = PIVOT_SPAN) -> list[int]:
    """قيعانٌ محلّية: أدنى من ``span`` شمعةً على كلّ جانب.

    ═══ والجانب الأيمن يعني تأخّراً ═══

    القاع لا يُعرَف قاعاً إلّا بعد ``span`` شمعةً منه. فهذه الدالّة
    **لا تصلح للقرار اللحظي** — وهي هنا لدراسة التاريخ حيث
    الجانبان معلومان. واستعمالُها إشارةً حيّة نظرٌ إلى المستقبل.
    """
    out: list[int] = []
    n = low.size
    for i in range(span, n - span):
        window = low[i - span: i + span + 1]
        if low[i] == window.min() and np.isfinite(low[i]):
            out.append(i)
    return out


def build(df, labels: dict, *, atr_len: int = 14,
          min_touches: int = MIN_TOUCHES) -> list[dict]:
    """مناطق الارتداد مرتّبةً بأسوأ ما تحتمله البيانات."""
    from scanner.indicators.pine import atr as atr_fn

    low = df["low"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    close = df["close"].astype(float).to_numpy()
    a = atr_fn(df, atr_len).to_numpy(dtype="float64")
    lab = labels["label"]

    idx = pivots(low)
    if not idx:
        return []

    # ── تجميع القيعان المتقاربة ──
    groups: list[list[int]] = []
    for i in sorted(idx, key=lambda k: low[k]):
        placed = False
        for g in groups:
            ref = low[g[0]]
            tol = ZONE_ATR * (a[g[0]] if np.isfinite(a[g[0]]) else 0.0)
            if tol > 0 and abs(low[i] - ref) <= tol:
                g.append(i)
                placed = True
                break
        if not placed:
            groups.append([i])

    last = float(close[-1])
    zones: list[dict] = []

    for g in groups:
        prices = [low[i] for i in g]
        lo, hi = min(prices), max(prices)
        mid = (lo + hi) / 2.0
        band = ZONE_ATR * float(np.nanmedian([a[i] for i in g]) or 0.0)
        z_lo, z_hi = lo - band / 2.0, hi + band / 2.0

        # ═══ كل لمسةٍ لا كل قاع ═══
        #
        # المنطقة قد يدخلها السعر مرّاتٍ بلا أن يصنع قاعاً. وعدُّ
        # القيعان وحدها يُحصي النجاحات ويُسقط الاختراقات — وهو
        # بالضبط ما يصنع «الدعم القويّ» الوهميّ.
        touches: list[int] = []
        inside = False
        for i in range(len(low)):
            within = low[i] <= z_hi and high[i] >= z_lo
            if within and not inside:
                touches.append(i)
            inside = within

        settled = [int(lab[i]) for i in touches
                   if i < lab.size and lab[i] != OPEN]
        if len(settled) < min_touches:
            continue
        k = sum(1 for x in settled if x == WIN)
        p, lo_ci, hi_ci = _wilson(k, len(settled))

        zones.append({
            "low": round(z_lo, 10), "high": round(z_hi, 10),
            "mid": round(mid, 10),
            "touches": len(touches),
            "settled": len(settled),
            "held": k, "broke": len(settled) - k,
            "rate": p, "lo": lo_ci, "hi": hi_ci,
            "distance_pct": round((mid - last) / last * 100.0, 2)
            if last else None,
            "above": mid > last,
            "last_touch": int(max(touches)) if touches else None,
        })

    # ═══ الترتيب بالحدّ الأدنى ═══
    #
    # منطقةٌ ٣ من ٣ نسبتها ١٠٠٪ وفاصلها ‎[31–100]‎ — وتصدّرُها
    # الترتيب خداعٌ. والحدّ الأدنى يرتّب بأسوأ ما تحتمله البيانات،
    # فتتقدّم المنطقة ذات العيّنة الأكبر.
    zones.sort(key=lambda z: (-z["lo"], -z["settled"]))
    return zones
