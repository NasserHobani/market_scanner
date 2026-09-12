# -*- coding: utf-8 -*-
"""‏Trend-Based Fibonacci Extension — ثلاث نقاط، لا اثنتان.

═══ الرسم ═══

    P1 = قاع بداية الموجة
    P2 = قمّة الموجة
    P3 = قاع التصحيح

    المستوى = P3 + (P2 − P1) × النسبة

وهي غير ``Fib Retracement`` (نقطتان، ومستوياتٌ **بين**هما) وغير
الامتداد ذي النقطتين. والفرق أنّ هذه تُسقط الموجة الأولى **من
نهاية التصحيح**، فتقول: إن استُؤنف الاتجاه بالقوّة نفسها فإلى أين؟

═══ وما هي عليه فعلاً ═══

أداةُ **أهداف** لا أداةُ إشارات. والمصدر الذي بُنيت عليه يقول ذلك
صراحةً: تُستعمل غالباً لتحديد جني الأرباح. فلا تُنتج هنا إشارة
شراء، ولا تُضاف نقاطاً إلى تقييمٍ يقيس شيئاً آخر.

═══ وأكبر عيوبها: ذاتيّة اختيار النقاط ═══

المصدر يضع هذا أوّل قائمة العيوب: متداولان يختاران محورين
مختلفين فيحصلان على مستوياتٍ مختلفة، ثمّ يختلفان في «أين
المقاومة». وفي الرسم اليدوي لا حلّ لهذا.

أمّا هنا فالنقاط تُختار **بقاعدةٍ واحدة مكتوبة**: آخر ثلاثة
محاور مؤكَّدة من الزيجزاج نفسه الذي يبني بقيّة التحليل. فالنتيجة
تتكرّر، وتُقاس، ويمكن الاختلاف معها بتغيير القاعدة لا بالجدال.

وهذا لا يجعلها «صحيحة» — يجعلها **قابلة للقياس**، وهذا كل ما
نطلبه قبل أن تُستعمل.

═══ ومنع النظر إلى المستقبل ═══

المحاور مؤكَّدة بنافذةٍ على الجانبين، و``pivot_high`` يُبطل آخر
``right`` شمعة صراحةً — فلا محور يُعرف قبل أن تمرّ شمعاته. ثمّ
تُسقط الشمعة الجارية فوق ذلك.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

__all__ = ["measure", "levels_from", "find_swings", "DEFAULTS", "RATIOS"]

# النسب المعروضة. و‏1.618 هي النسبة الذهبية، و‏1.0 إسقاطُ الموجة
# بطولها. والباقي مراتب بينها وبعدها.
RATIOS = (0.618, 1.0, 1.272, 1.382, 1.618, 2.0, 2.618, 4.236)

DEFAULTS = {
    # نافذة تأكيد المحور — نفس ما يستعمله بقيّة التحليل
    "pivot_length": 10,
    "min_swing_atr": 1.0,
    "atr_len": 14,

    # ═══ حدّا عمق التصحيح ═══
    #
    # تصحيحٌ ‎5٪‎ من الموجة ليس تصحيحاً بل توقّفاً، وقياسُ امتدادٍ
    # منه يعطي مستوياتٍ ملاصقة للقمّة بلا معنى.
    #
    # وتصحيحٌ يتجاوز ‎88.6٪‎ يعني أنّ الموجة أُلغيت عملياً — وما
    # يُبنى عليه امتدادٌ لموجةٍ لم تعد قائمة.
    "min_retracement": 0.236,
    "max_retracement": 0.886,

    # موجةٌ أقصر من هذا ضجيج — تُقاس بمضاعف ATR لا بنسبةٍ ثابتة،
    # فرمزٌ يتحرّك ‎1٪‎ يومياً ورمزٌ يتحرّك ‎15٪‎ لا يقاسان بمسطرة
    "min_leg_atr": 2.0,

    # تقاربٌ دون هذا يُسمّى «التقاءً» بين مستوى فيب والمقاومة
    "confluence_pct": 1.0,

    # فوق هذا المستوى: الحركة جرت — لا «ما قبلها»
    "extended_ratio": 1.618,
}


@dataclass
class Swings:
    """النقاط الثلاث — أو سببُ عدم وجودها."""
    ok: bool = False
    why: str = ""
    p1: float | None = None
    p2: float | None = None
    p3: float | None = None
    p1_at: object = None
    p2_at: object = None
    p3_at: object = None
    retracement: float | None = None
    leg_pct: float | None = None


def _closed(df: pd.DataFrame) -> pd.DataFrame:
    """يُسقط الشمعة الجارية — القرار على المغلق وحده."""
    return df.iloc[:-1] if df is not None and len(df) > 1 else df


def _cfg(params: dict | None, key: str):
    node = (params or {}).get("fib_extension") or {}
    return node.get(key, DEFAULTS[key])


def find_swings(df: pd.DataFrame, params: dict | None = None) -> Swings:
    """آخر ‏قاع → قمّة → قاع مؤكَّدة، مع شروط صحّتها.

    ═══ الترتيب من الأحدث للأقدم ═══

    يُبحث عن آخر قاع (P3)، ثمّ آخر قمّة قبله (P2)، ثمّ آخر قاع قبلها
    (P1). فإن لم يكتمل النمط فلا امتداد — ويُقال السبب.
    """
    from .structure import build_structure

    d = _closed(df)
    length = int(_cfg(params, "pivot_length"))
    if d is None or len(d) < length * 4:
        return Swings(why=f"يلزم {length * 4} شمعة على الأقلّ")

    st = build_structure(d, length,
                         float(_cfg(params, "min_swing_atr")),
                         int(_cfg(params, "atr_len")))
    pv = st.pivots
    if len(pv) < 3:
        return Swings(why="لا محاور كافية في الهيكل")

    # آخر قاع، ثمّ قمّة قبله، ثمّ قاع قبلها
    i3 = next((i for i in range(len(pv) - 1, -1, -1) if not pv[i].is_high),
              None)
    if i3 is None:
        return Swings(why="لا قاع مؤكَّد")
    i2 = next((i for i in range(i3 - 1, -1, -1) if pv[i].is_high), None)
    if i2 is None:
        return Swings(why="لا قمّة قبل القاع الأخير")
    i1 = next((i for i in range(i2 - 1, -1, -1) if not pv[i].is_high), None)
    if i1 is None:
        return Swings(why="لا قاع قبل القمّة")

    p1, p2, p3 = pv[i1].price, pv[i2].price, pv[i3].price
    idx = d.index
    at = (idx[pv[i1].index], idx[pv[i2].index], idx[pv[i3].index])

    # ═══ الشروط ═══
    if not (p2 > p1):
        return Swings(why="الموجة ليست صاعدة")

    leg = p2 - p1
    if leg <= 0:
        return Swings(why="طول الموجة صفر")

    # ‏P3 تحت P1 يعني أنّ الموجة كُسرت — ليس تصحيحاً بل انعكاساً.
    # وامتدادٌ يُسقَط من نقطةٍ تحت بداية الموجة لا معنى له.
    if p3 <= p1:
        return Swings(why="التصحيح كسر بداية الموجة — لا امتداد")

    retr = (p2 - p3) / leg
    lo = float(_cfg(params, "min_retracement"))
    hi = float(_cfg(params, "max_retracement"))
    if retr < lo:
        return Swings(why=f"التصحيح {retr:.0%} أقلّ من {lo:.0%} — توقّفٌ "
                          "لا تصحيح")
    if retr > hi:
        return Swings(why=f"التصحيح {retr:.0%} أعمق من {hi:.0%} — الموجة "
                          "أُلغيت")

    # حجم الموجة بمضاعف ATR: مسطرةٌ تناسب كل رمز
    from .pine import atr

    a = float(atr(d, int(_cfg(params, "atr_len"))).iloc[-1])
    if np.isfinite(a) and a > 0:
        if leg < a * float(_cfg(params, "min_leg_atr")):
            return Swings(why=f"الموجة {leg / a:.1f}×ATR — أصغر من "
                              f"{_cfg(params, 'min_leg_atr')}×")

    return Swings(ok=True, p1=p1, p2=p2, p3=p3,
                  p1_at=at[0], p2_at=at[1], p3_at=at[2],
                  retracement=round(retr, 3),
                  leg_pct=round(leg / p1 * 100, 2))


def levels_from(p1: float, p2: float, p3: float,
                ratios=RATIOS) -> list[dict]:
    """‏P3 + (P2 − P1) × النسبة — لكل نسبة."""
    leg = float(p2) - float(p1)
    return [{"ratio": r, "price": round(float(p3) + leg * r, 8)}
            for r in ratios]


def measure(df: pd.DataFrame, params: dict | None = None,
            *, resistance: float | None = None) -> dict:
    """المستويات، وموضع السعر منها، والمسافة إلى الهدف التالي."""
    sw = find_swings(df, params)
    if not sw.ok:
        return {"ok": False, "why": sw.why}

    d = _closed(df)
    close = float(d["close"].iloc[-1])
    lv = levels_from(sw.p1, sw.p2, sw.p3)

    # ═══ الهدف التالي ═══
    #
    # أوّل مستوىً **فوق** السعر. وهو الرقم الوحيد القابل للاستعمال
    # مباشرةً: كم يبعد الهدف الواقعي التالي؟
    above = [x for x in lv if x["price"] > close]
    nxt = above[0] if above else None
    room = (round((nxt["price"] - close) / close * 100, 2)
            if nxt else None)

    # ═══ أين السعر من السلّم ═══
    #
    # هذا هو الاستعمال الأنفع للأداة في استراتيجيةٍ اسمها «ما قبل
    # الانفجار»: سعرٌ تجاوز ‎1.618‎ لم يعد «ما قبل» — الحركة جرت.
    ext_ratio = float(_cfg(params, "extended_ratio"))
    ext_level = next((x["price"] for x in lv
                      if abs(x["ratio"] - ext_ratio) < 1e-9), None)
    passed = [x["ratio"] for x in lv if close >= x["price"]]
    stage = max(passed) if passed else 0.0
    extended = ext_level is not None and close >= ext_level

    # ═══ التقاء مع المقاومة ═══
    #
    # مستوى فيب يقع على مقاومةٍ مرصودة أقوى من كلٍّ منهما وحده —
    # وهو ما يوصي به المصدر: البحث عن التقاءٍ لا الاكتفاء بالفيب.
    conf = None
    if resistance:
        tol = float(_cfg(params, "confluence_pct"))
        for x in lv:
            gap = abs(x["price"] - float(resistance)) / close * 100
            if gap <= tol:
                conf = {"ratio": x["ratio"], "price": x["price"],
                        "gap_pct": round(gap, 2)}
                break

    return {
        "ok": True,
        "p1": sw.p1, "p2": sw.p2, "p3": sw.p3,
        "p1_at": sw.p1_at, "p2_at": sw.p2_at, "p3_at": sw.p3_at,
        "retracement": sw.retracement,
        "leg_pct": sw.leg_pct,
        "close": close,
        "levels": lv,
        "next_level": nxt,
        "room_pct": room,
        "stage": stage,
        "extended": bool(extended),
        "extended_at": ext_level,
        "confluence": conf,
        # ═══ ما لا تدّعيه ═══
        #
        # المصدر نفسه يعدّد: ذاتيّة النقاط، وعجزها في السوق
        # العرضي، وأنّ كثرة استعمالها تصنع ارتداداً لأنّ الناس
        # يتوقّعونه لا لأنّ السوق يقتضيه. فهي مناطق اهتمام لا
        # نقاط انعكاسٍ مؤكَّدة.
        "note": "مناطق اهتمام لا نقاط انعكاس — والأداة للأهداف",
    }
