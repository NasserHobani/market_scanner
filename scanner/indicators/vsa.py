# -*- coding: utf-8 -*-
"""تحليل الحجم والمدى (VSA) — ماذا يقول اتّساع الشمعة مع حجمها.

═══ الفكرة ═══

منهج وايكوف: الشمعة ثلاثة أرقام لا رقم واحد — **المدى** (كم تحرّك
السعر)، و**الحجم** (كم تُودُوِل)، و**موضع الإغلاق** داخل المدى (من
كسب المعركة في النهاية).

والعلاقة بينها تقول ما لا يقوله أيٌّ منها وحده:

  · حجمٌ هائل ومدىً ضيّق  →  أحدهم يمتصّ البيع (أو العرض).
  · حجمٌ هائل وإغلاقٌ في الأسفل بعد صعود  →  توزيع.
  · صعودٌ بمدىً واسع وحجمٍ ضعيف  →  لا طلب حقيقيّ خلفه.

═══ ولماذا يُحترس منه ═══

هذه الأنماط **وصفٌ** لا قاعدة قرار. تُحسَب هنا كخصائص تُقاس على
الصفقات المحسومة، ولا تُدخَل في التقييم حتى تُثبت أنّها تفصل
الرابح عن الخاسر على بياناتك أنت.

فأنماط الشموع مشهورةٌ بأنّها تصف الماضي ببلاغة ولا تتنبّأ. والفرق
بين الاثنين رقمٌ يُقاس لا حكايةٌ تُروى.

═══ ولماذا النسب لا الأرقام المطلقة ═══

«حجم كبير» بلا مرجع بلا معنى: سهمٌ يتداول مليوناً وآخر ألفاً. فكل
شيء هنا نسبةٌ إلى متوسّط متدحرج — قابلٌ للمقارنة بين الرموز
والأسواق.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

# عتبات النسب. ليست مقدّسة — تُقاس وتُعايَر، وهي مكتوبة هنا
# لتُرى وتُناقَش لا لتُخفى داخل الشيفرة.
HIGH_VOL = 1.8         # ضعف متوسّط الحجم تقريباً
LOW_VOL = 0.6
WIDE_RANGE = 1.5       # نسبةً إلى متوسّط المدى
NARROW_RANGE = 0.6
CLOSE_HIGH = 0.70      # موضع الإغلاق داخل المدى
CLOSE_LOW = 0.30


@dataclass(frozen=True)
class Bar:
    """قراءة VSA لشمعة واحدة."""

    vol_ratio: float          # الحجم ÷ متوسّطه
    range_ratio: float        # المدى ÷ متوسّطه
    close_pos: float          # 0 = أدنى المدى، 1 = أعلاه
    spread_per_volume: float  # المدى ÷ الحجم — كفاءة الحركة
    signals: tuple[str, ...]  # أسماء الأنماط المرصودة
    arabic: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


ARABIC = {
    "stopping_volume": "حجم إيقاف",
    "climax_up": "ذروة شرائية",
    "climax_down": "ذروة بيعية",
    "no_demand": "لا طلب",
    "no_supply": "لا عرض",
    "upthrust": "دفعة كاذبة للأعلى",
    "spring": "زنبرك",
    "effort_no_result": "جهد بلا نتيجة",
    "ease_of_move_up": "سهولة حركة صاعدة",
    "ease_of_move_down": "سهولة حركة هابطة",
}


def _safe_div(a, b):
    return a / np.where(np.abs(b) < 1e-12, np.nan, b)


def features(df: pd.DataFrame, length: int = 20) -> pd.DataFrame:
    """خصائص VSA لكل شمعة — أعمدة عدديّة صالحة للقياس.

    كلّها من الشمعة نفسها ومتوسّطات **سابقة** — لا نظرة إلى الأمام.
    """
    hi = df["high"].astype(float)
    lo = df["low"].astype(float)
    cl = df["close"].astype(float)
    op = df["open"].astype(float)
    vo = df["volume"].astype(float)

    rng = (hi - lo)
    # المتوسّطات **مزاحة بشمعة**: متوسّطٌ يشمل الشمعة الحالية يُسرّب
    # معلومةً منها إلى مرجعها، فتبدو كل شمعة أقرب إلى «عاديّة».
    vol_ma = vo.rolling(length, min_periods=5).mean().shift(1)
    rng_ma = rng.rolling(length, min_periods=5).mean().shift(1)

    out = pd.DataFrame(index=df.index)
    out["vol_ratio"] = _safe_div(vo, vol_ma)
    out["range_ratio"] = _safe_div(rng, rng_ma)
    # ═══ الحصر بين صفر وواحد ═══
    #
    # الشمعة السليمة إغلاقها داخل مداها دائماً. لكنّ مصدراً معطوباً
    # أو تجميعاً خاطئاً قد يعطي إغلاقاً خارجه، فينتج «موضع» يساوي
    # 1.4 — ويمرّ في كل حساب لاحق بلا شكوى، ويُخالف تعريفه.
    #
    # فالحصر يجعل الرقم يحترم معناه: نسبةٌ داخل المدى لا خارجه.
    out["close_pos"] = _safe_div(cl - lo, rng).clip(0.0, 1.0)
    out["body_ratio"] = _safe_div((cl - op).abs(), rng).clip(0.0, 1.0)
    # كفاءة الحركة: كم مدىً أنتجت وحدة الحجم. انخفاضها مع حجم عالٍ
    # هو «الجهد بلا نتيجة» — أوضح إشارات وايكوف على الامتصاص.
    out["spread_per_volume"] = _safe_div(rng / rng_ma.replace(0, np.nan),
                                         vo / vol_ma.replace(0, np.nan))
    return out


def classify(df: pd.DataFrame, length: int = 20,
             i: int = -1) -> Bar | None:
    """تصنيف شمعة واحدة (الأخيرة افتراضاً)."""
    if df is None or len(df) < length + 2:
        return None
    f = features(df, length)
    row = f.iloc[i]
    vr = float(row["vol_ratio"])
    rr = float(row["range_ratio"])
    cp = float(row["close_pos"])
    spv = float(row["spread_per_volume"])
    if not np.isfinite(vr) or not np.isfinite(rr) or not np.isfinite(cp):
        return None

    # السياق: هل نحن بعد صعود أم هبوط؟ الأنماط نفسها تعني عكس
    # بعضها بحسب ما سبقها — «حجم إيقاف» بعد هبوط شراء، وبعد صعود بيع.
    close = df["close"].astype(float)
    j = len(df) + i if i < 0 else i
    prior = close.iloc[max(0, j - length):j]
    up_before = bool(len(prior) > 2 and close.iloc[j - 1] > prior.mean())
    down_before = bool(len(prior) > 2 and close.iloc[j - 1] < prior.mean())

    sig: list[str] = []
    if vr >= HIGH_VOL and rr <= NARROW_RANGE:
        sig.append("effort_no_result")
        sig.append("stopping_volume" if down_before else "upthrust"
                   if up_before else "effort_no_result")
    if vr >= HIGH_VOL and rr >= WIDE_RANGE:
        if cp >= CLOSE_HIGH:
            sig.append("climax_up" if up_before else "ease_of_move_up")
        elif cp <= CLOSE_LOW:
            sig.append("climax_down" if down_before else "ease_of_move_down")
    if vr <= LOW_VOL and rr <= NARROW_RANGE:
        sig.append("no_demand" if up_before else "no_supply")
    if (cp <= CLOSE_LOW and rr >= WIDE_RANGE and vr >= HIGH_VOL
            and up_before):
        sig.append("upthrust")
    if (cp >= CLOSE_HIGH and rr >= WIDE_RANGE and vr >= HIGH_VOL
            and down_before):
        sig.append("spring")

    uniq = tuple(dict.fromkeys(sig))
    return Bar(vol_ratio=vr, range_ratio=rr, close_pos=cp,
               spread_per_volume=spv if np.isfinite(spv) else float("nan"),
               signals=uniq,
               arabic=tuple(ARABIC.get(s, s) for s in uniq))


__all__ = ["Bar", "features", "classify", "ARABIC",
           "HIGH_VOL", "LOW_VOL", "WIDE_RANGE", "NARROW_RANGE"]
