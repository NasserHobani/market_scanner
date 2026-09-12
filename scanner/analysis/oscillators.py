# -*- coding: utf-8 -*-
"""لوحتا الزخم تحت الشارت — ‏StochRSI و MACD جاهزتين للرسم.

═══ لماذا لوحتان منفصلتان لا طبقةٌ فوق السعر ═══

‏StochRSI مقياسه ٠–١٠٠. و MACD بوحدة السعر — قيمته لبتكوين
بالآلاف ولرمزٍ سعودي بالكسور. ووضعهما على محور السعر يسحق أحدهما
في خطٍّ مسطّح عند حافّة الشاشة.

═══ والحساب على كامل التاريخ ثمّ القصّ ═══

‏RSI‏(14) ثمّ ستوكاستيك‏(14) ثمّ تنعيمان — أي أنّ أوّل ٣١ شمعة بلا
قيمة. وحسابُه على نافذة العرض وحدها يجعل أوائلها خاطئة، ثمّ
تتغيّر القيم كلّما مرّر المستخدم الشارت.

فالحساب على ``df`` كاملاً، والقصّ بعده على نافذة الشموع نفسها.

═══ والقراءة النصّية من المغلق ═══

الخطوط تُرسم إلى الشمعة الجارية — هذا ما يتوقّعه من يقارن بشارته.
أمّا **الأرقام والحالة** المكتوبة فمن آخر شمعة مغلقة: تقاطعٌ يظهر
في منتصف الشمعة ويختفي قبل إغلاقها ليس تقاطعاً.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators.momentum import (
    OVERBOUGHT, OVERSOLD, macd_state, stoch_rsi, stoch_rsi_state,
)
from ..indicators.trend import macd

__all__ = ["build"]

# ═══ أقلّ عدد شمعات يعطي قيمةً واحدة صحيحة ═══
#
# الإحماء الفعليّ ٣١ شمعة: ‏RSI(14) أوّل قيمةٍ له عند الفهرس ١٤،
# ثمّ نافذة ستوكاستيك تضيف ١٣، و‎%K‎ يضيف ٢، و‎%D‎ يضيف ٢.
# (النوافذ المتتالية تتداخل عند حوافّها، فجمع أطوالها يبالغ.)
#
# والحدّ هنا ٣٤ عمداً: قيمةٌ واحدة صحيحة لا تكفي لرسمٍ ولا
# لقراءة تقاطع — وهذه تحتاج شمعتين مغلقتين على الأقلّ.
WARMUP_BARS = 14 + 13 + 2 + 2      # = 31
MIN_BARS = WARMUP_BARS + 3

UP = "#3ddc97"
DOWN = "#ff6b6b"


def _points(series: pd.Series, index) -> list[dict]:
    """نقاط ‎{time, value}‎ بلا ‎NaN‎.

    ‏NaN يمرّ في JSON بـ ``NaN`` الحرفية — وهي **ليست** JSON صالحاً،
    فيرفضها ``JSON.parse`` في المتصفّح ويسقط الرسم كلّه لا هذه
    النقطة وحدها. فالغائب يُحذف ولا يُرسَل.
    """
    out = []
    for t, v in zip(index, series):
        f = float(v)
        if np.isfinite(f):
            out.append({"time": int(t.timestamp()), "value": round(f, 6)})
    return out


def build(df: pd.DataFrame, since_ts: int | None = None) -> dict:
    """يحسب اللوحتين ويقصّهما على نافذة العرض.

    ``since_ts`` هو زمن أوّل شمعة معروضة — يُؤخذ من مخرَج
    ``overlay.build`` نفسه لا يُخمَّن، فنافذته تتوسّع أحياناً لتشمل
    بداية الموجة. وعدمُ التطابق يجعل اللوحتين تنزلقان عن الشارت.
    """
    if df is None or len(df) < MIN_BARS:
        return {"ok": False,
                "reason": f"يلزم {MIN_BARS} شمعة على الأقلّ، والمتاح "
                          f"{0 if df is None else len(df)}"}

    close = df["close"].astype(float)
    srsi = stoch_rsi(close)
    m = macd(close)

    # الحالة تُقرأ من السلسلة الكاملة قبل القصّ — آخر شمعة مغلقة
    # هي آخر شمعة مغلقة في التاريخ كلّه، لا في نافذة العرض.
    srsi_state = stoch_rsi_state(srsi)
    m_state = macd_state(m)

    view_idx = df.index
    if since_ts is not None:
        keep = view_idx.map(lambda t: int(t.timestamp()) >= int(since_ts))
        view_idx = view_idx[np.asarray(keep, dtype=bool)]

    srsi_v = srsi.loc[view_idx]
    m_v = m.loc[view_idx]

    # ═══ لون المدرّج ═══
    #
    # أربع حالات لا اثنتان: فوق الصفر متمدّداً/متقلّصاً، وتحته
    # كذلك. والتقلّص فوق الصفر يعني زخماً صاعداً **يخفّ** — وهو
    # ما يسبق التقاطع. ولونٌ واحد للجانب يخفي ذلك تماماً.
    hist_pts = []
    prev = None
    for t, v in zip(view_idx, m_v["hist"]):
        f = float(v)
        if not np.isfinite(f):
            prev = None
            continue
        growing = prev is None or abs(f) >= abs(prev)
        if f >= 0:
            color = UP if growing else "rgba(61,220,151,.40)"
        else:
            color = DOWN if growing else "rgba(255,107,107,.40)"
        hist_pts.append({"time": int(t.timestamp()), "value": round(f, 6),
                         "color": color})
        prev = f

    return {
        "ok": True,
        "stoch_rsi": {
            "k": _points(srsi_v["k"], view_idx),
            "d": _points(srsi_v["d"], view_idx),
            "overbought": OVERBOUGHT,
            "oversold": OVERSOLD,
            "state": srsi_state,
            "params": "RSI 14 · ستوكاستيك 14 · ‎%K‎ 3 · ‎%D‎ 3",
        },
        "macd": {
            "line": _points(m_v["macd"], view_idx),
            "signal": _points(m_v["signal"], view_idx),
            "hist": hist_pts,
            "state": m_state,
            "params": "12 · 26 · 9",
        },
        # ═══ يُعلَن أنّهما خارج القرار ═══
        #
        # مؤشّرٌ مرسوم في الصفحة يُفترَض أنّه يؤثّر. وهذان لم
        # يُقاسا على صفقاتك بعد، فلا يمسّان النقاط ولا التوصية.
        # وسكوتُ الواجهة عن ذلك يجعل القارئ ينسب إليهما قراراً
        # لم يصنعاه.
        "scored": False,
        "disclaimer": "عرضٌ فقط — لا يدخلان النقاط ولا التوصية",
    }
