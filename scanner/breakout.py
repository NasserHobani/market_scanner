# -*- coding: utf-8 -*-
"""رصد الشمعة الأولى من حركة عنيفة — تنبيه لا توصية.

لماذا هذا التمييز جوهري وليس لغوياً:

اختُبرت أولاً فرضية «حجم مرتفع بلا حركة سعر يسبق الانفجار» على كل
البيانات المتاحة، فكان رفعها 0.4–0.9× — أي أسوأ من الصدفة. فأُسقطت.

ثم اختُبر ما هنا (حجم منفجر مع اختراق مدى) فكانت النتيجة مركّبة:
الحركات التالية أضخم فعلاً (5–6.5×ATR مقابل 2.3 للأساس)، لكن التراجع
المعاكس ضخم بدوره (2.5–3.4×ATR)، وعند محاكاة صفقة كاملة كان التوقّع
سالباً على 4h في كل تركيبات الوقف والهدف، وموجباً على 15m بعيّنة 25
صفقة فقط — أي ضمن حدود الضجيج.

فالخلاصة الأمينة: **هذه ليست إشارة دخول مثبتة**. تُرسل لتقول «هذا
الرمز يتحرك الآن» وتُسجَّل كمصدر صفقات مستقل حتى يقيس نظام الأداء
جدواها بأرقام حقيقية. إن ظهر توقّعها سالباً بعد عيّنة كافية فتُطفأ.

تحديث بعد أول عيّنة حيّة (خمس صفقات، خمس خسائر):

الرقم السالب لم يكن حكماً على الإشارة بل على الوقف. كان الوقف يُقاس
بـ ATR14 — متوسط أربع عشرة شمعة — ويُطبَّق على سوق ضاعف الانفجار
تقلّبه عشر مرات، فيقع داخل الضجيج ويُضرب بحركة عادية. تفصيل البرهان
في ``_stop_price``.

وبعد تصحيح الوقف صار التوقّع **صفراً** على 2893 اختراقاً في ثلاثة
فريمات (‏+0.02R و+0.01R و+0.00R). وقُسّمت العيّنة على الصعود السابق
وشدّة الحجم واتساع الوقف وموضع الإغلاق، فلم تصمد شريحة موجبة على
فريمين معاً. فالحكم الحالي: تنبيه بلا أفضلية قابلة للقياس — لا يُتداول
بلا سبب آخر يسنده.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .indicators.pine import atr, ema
from .indicators.volume import rvol as rvol_series

# العتبات الافتراضية — من القياس لا من الذوق
MIN_RVOL = 8.0          # دونها لا تتميّز الحالات عن الأساس
LOOKBACK = 20           # قمة المدى المخترَق
STOP_ATR = 1.5          # حدّ أدنى لا أكثر — انظر _stop_price
TARGET_ATR = 3.0
MIN_BODY = 0.35         # جسم الشمعة نسبة إلى مداها — يستبعد فتيل الاصطياد
LOW_BUFFER = 0.10       # هامش تحت قاع الشمعة، كسراً من مداها


def _stop_price(close: float, low: float, span: float, atr_val: float,
                stop_atr: float, low_buffer: float = LOW_BUFFER) -> float:
    """الوقف: الأوسع بين مقياس ATR وقاع شمعة الاختراق نفسها.

    كان الوقف ‏stop_atr×ATR14 وحده، وهو عطب قابل للبرهان لا مسألة ذوق:

    ATR متوسط أربع عشرة شمعة. فحين تنفجر شمعة واحدة إلى عشرة أضعاف
    مداها المعتاد، يقسّم المتوسط الانفجار على أربعة عشر ويبتلعه —
    ‏(13×0.62 + 4.78)/14 ≈ 0.92٪ — فيخرج وقف عند 1.38٪ في سوق صار مدى
    شمعته 4.78٪. الوقف حينئذ **داخل الضجيج**: يُضرب بحركة عادية مهما
    كان الاتجاه صحيحاً.

    وهذا ما حدث حرفياً: خمس صفقات حيّة، خمس خسائر، كلها في شمعة واحدة
    وكلها خرجت عند الوقف بالضبط، والوقف في الخمس أضيق من مدى الشمعة
    التالية وحدها.

    القياس على 2893 اختراقاً في ثلاثة فريمات:

        الفريم   الوقف القديم   الوقف هنا
        4h         −0.27R        +0.02R
        1h         −0.23R        +0.01R
        15m        −0.02R        +0.00R

    فلينتبه القارئ إلى ما لا يقوله هذا الجدول: التصحيح **لا يصنع
    أفضلية**، بل يزيل نزفاً كان يُوهم بوجود إشارة قوية معاكسة. النتيجة
    بعده صفر — وهو ما يُنتظر من دخول بلا أفضلية ووقف عادل. يبقى
    الاختراق تنبيهاً على حركة، لا توصية دخول.

    قاع الشمعة مقياس للتقلّب الجديد لا القديم: هو أدنى نقطة قبلها
    السوق فعلاً أثناء الانفجار. والهامش تحته لأن القاع بالضبط يُلمس
    كثيراً — الوقف عليه تماماً يجعله هدفاً لا حماية.
    """
    by_atr = close - stop_atr * atr_val
    by_low = low - low_buffer * span
    return min(by_atr, by_low)


@dataclass
class Breakout:
    symbol: str
    timeframe: str
    close: float
    entry: float
    stop: float
    target: float
    rvol: float
    atr: float
    broke: float            # القمة المخترَقة
    body_ratio: float
    change_pct: float
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe,
            "close": self.close, "entry": self.entry, "stop": self.stop,
            "target": self.target, "rvol": round(self.rvol, 1),
            "atr": self.atr, "broke": self.broke,
            "body_ratio": round(self.body_ratio, 2),
            "change_pct": round(self.change_pct, 2),
            "reasons": list(self.reasons),
            "rr": round((self.target - self.entry) / (self.entry - self.stop), 2)
            if self.entry > self.stop else None,
        }


def detect(df: pd.DataFrame, symbol: str, timeframe: str, *,
           min_rvol: float = MIN_RVOL, lookback: int = LOOKBACK,
           stop_atr: float = STOP_ATR, target_atr: float = TARGET_ATR,
           min_body: float = MIN_BODY,
           low_buffer: float = LOW_BUFFER) -> Breakout | None:
    """يفحص الشمعة **المغلقة الأخيرة** وحدها.

    الفحص على شمعة مغلقة لا جارية: الشمعة الجارية قد تنقلب قبل إغلاقها
    فيصير التنبيه إعادة رسم — وهو ما تجنّبه هذا المشروع من أوله.
    """
    need = max(lookback, 50, 20) + 5   # EMA50 و ATR14 يحتاجان إحماءً
    if df is None or len(df) < need:
        return None
    if not {"open", "high", "low", "close", "volume"} <= set(df.columns):
        return None

    close = df["close"]
    last = len(df) - 1

    # نفس تعريف RVOL المستعمل في بقية المشروع (المتوسط يشمل الشمعة
    # الحالية)، وهو التعريف الذي قيست عليه العتبات — تغييره هنا يجعل
    # الرقم 8 يعني شيئاً آخر غير الذي اختُبر
    rv = rvol_series(df, 20)
    if not np.isfinite(rv.iloc[last]):
        return None
    rvol = float(rv.iloc[last])
    if rvol < min_rvol:
        return None

    # القمة المخترَقة تُحسب من الشموع السابقة فقط — إدخال الشمعة الحالية
    # يجعل الشرط يقارن الشمعة بنفسها فلا يتحقق أبداً
    prior_high = float(df["high"].iloc[last - lookback:last].max())
    c = float(close.iloc[last])
    if c <= prior_high:
        return None

    trend = ema(close, 50)
    if not np.isfinite(trend.iloc[last]) or c <= float(trend.iloc[last]):
        return None

    hi, lo = float(df["high"].iloc[last]), float(df["low"].iloc[last])
    span = hi - lo
    body = abs(c - float(df["open"].iloc[last]))
    body_ratio = (body / span) if span > 0 else 0.0
    # فتيل طويل بجسم صغير: السعر ارتدّ عن قمته داخل الشمعة نفسها،
    # وهذا اصطياد سيولة أقرب منه إلى اختراق
    if body_ratio < min_body:
        return None

    a = atr(df, 14)
    atr_val = float(a.iloc[last]) if np.isfinite(a.iloc[last]) else 0.0
    if atr_val <= 0:
        return None

    prev = float(close.iloc[last - 1])
    change = (c - prev) / prev * 100 if prev else 0.0

    stop = _stop_price(c, lo, span, atr_val, stop_atr, low_buffer)
    if stop >= c:
        return None       # لا خطة بوقف فوق الدخول

    return Breakout(
        symbol=symbol, timeframe=timeframe, close=c,
        entry=c,                                  # الدخول عند الإغلاق
        stop=stop,
        target=c + target_atr * atr_val,
        rvol=rvol, atr=atr_val, broke=prior_high,
        body_ratio=body_ratio, change_pct=change,
        reasons=[f"حجم ×{rvol:.0f} من المعتاد",
                 f"اختراق قمة {lookback} شمعة",
                 f"جسم {body_ratio * 100:.0f}% من المدى"],
    )
