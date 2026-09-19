# -*- coding: utf-8 -*-
"""خطّ Supertrend للشارت — مقطّعاً بلونه عند كل انقلاب.

═══ لماذا مقاطع لا خطٌّ واحد ═══

‏Supertrend خطٌّ واحد يقفز من تحت السعر إلى فوقه عند الانقلاب.
ورسمُه سلسلةً واحدة يصل القفزة بخطٍّ مائل عبر الشارت — وهو ليس
خطأ تجميل: القفزة تُقرأ اتّجاهاً حادّاً وهي لا شيء.

فالمخرَج مقاطعُ منفصلة، كلٌّ بلونه: أخضر صاعد وأحمر هابط. وبينها
انقطاع، كما يرسمها TradingView تماماً.

═══ والإحماء يسبق نافذة العرض ═══

‏ATR يحتاج عشر شمعاتٍ قبل أن يستقرّ، والحدّان يُثبَّتان تصاعدياً
من أوّل شمعة. فالحساب على التاريخ **كلّه** ثمّ القصّ — لا العكس.
والحساب على النافذة وحدها يعطي خطّاً يختلف عن خطّ TradingView
في أوّل عشرين شمعة، ويصحّ بعدها، فيبدو المؤشّر «تقريبياً».

═══ والشمعة الجارية ═══

تُرسَم. فالمستخدم يقارن بشارته وهي ترسمها، وحذفُها يجعل الخطّ
يتأخّر شمعةً عن كل شارتٍ آخر. لكنّ **الحالة** المُعادة أدناه
(``state``) تُقرأ من آخر شمعة **مغلقة** — لأنّ القرار عليها،
والعرض شيءٌ والقرار شيء.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scanner.indicators.trend import supertrend, supertrend_state

#: ‏ATR بطول ١٠ يستقرّ بعد نحو ثلاثة أضعافه
WARMUP_BARS = 30
MIN_BARS = WARMUP_BARS + 5

UP = "#3ddc97"
DOWN = "#ff6b6b"


def build(df: pd.DataFrame, since_ts: int | None = None,
          *, length: int = 10, mult: float = 3.0) -> dict:
    """مقاطع الخطّ + الحالة. لا يرمي أبداً — يعيد ``ok: False``."""
    if df is None or len(df) < MIN_BARS:
        return {"ok": False,
                "reason": f"يلزم {MIN_BARS} شمعة، والمتاح "
                          f"{0 if df is None else len(df)}",
                "segments": []}

    st = supertrend(df, length, mult)

    view = df.index
    if since_ts is not None:
        keep = view.map(lambda t: int(t.timestamp()) >= int(since_ts))
        view = view[np.asarray(keep, dtype=bool)]
    if len(view) == 0:
        return {"ok": False, "reason": "نافذة العرض فارغة", "segments": []}

    line = st["supertrend"].loc[view]
    dirn = st["direction"].loc[view]

    # ═══ القطع عند تغيّر الاتجاه أو عند فجوة ═══
    #
    # و``NaN`` يقطع أيضاً: تمريرها إلى JSON يجعلها ``NaN`` الحرفية
    # — وهي ليست JSON صالحاً، فيسقط ``JSON.parse`` والرسم كلّه.
    segments: list[dict] = []
    cur: list[dict] = []
    cur_dir = 0
    for t, v, d in zip(view, line, dirn):
        f = float(v)
        di = int(d) if np.isfinite(float(d)) else 0
        if not np.isfinite(f) or di == 0:
            if len(cur) > 1:
                segments.append({"direction": cur_dir, "points": cur})
            cur, cur_dir = [], 0
            continue
        if di != cur_dir and cur:
            if len(cur) > 1:
                segments.append({"direction": cur_dir, "points": cur})
            cur = []
        cur_dir = di
        cur.append({"time": int(t.timestamp()), "value": round(f, 8)})
    if len(cur) > 1:
        segments.append({"direction": cur_dir, "points": cur})

    lines = [{"layer": "supertrend",
              "color": UP if s["direction"] > 0 else DOWN,
              "width": 2, "style": "solid",
              "points": s["points"]}
             for s in segments]

    state = supertrend_state(df, length, mult)
    return {
        "ok": True,
        "length": length,
        "multiplier": mult,
        "segments": segments,
        "lines": lines,
        # الحالة من آخر شمعة **مغلقة** — لا من الجارية المرسومة
        "state": state,
        "flips_in_view": max(0, len(segments) - 1),
    }


__all__ = ["build", "WARMUP_BARS", "MIN_BARS", "UP", "DOWN"]
