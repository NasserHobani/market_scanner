# -*- coding: utf-8 -*-
"""تصنيف السيولة من حجم التداول اليومي.

الغرض ليس التزيين: بعد خفض عتبة الحجم صارت أزواج حجمها مئات الآلاف
تدخل المسح. إشارة على زوج كهذا ليست كإشارة على زوج بمئات الملايين —
أمر واحد كبير يحرّك الأول، والانزلاق عند التنفيذ قد يبتلع الربح
المتوقّع كله. فالتصنيف تحذير مرافق للإشارة لا حكم عليها.
"""
from __future__ import annotations

# (المفتاح، الحدّ الأدنى بالدولار، العنوان)
TIERS = [
    ("high", 50_000_000, "عالية"),
    ("mid", 5_000_000, "متوسطة"),
    ("low", 1_000_000, "منخفضة"),
    ("micro", 0, "دقيقة"),
]
LABELS = {k: label for k, _, label in TIERS}
LABELS["unknown"] = "غير معروفة"

# دون هذا الحدّ نعدّ التنفيذ الواقعي مشكوكاً فيه
THIN = "micro"


def tier(quote_volume: float | None, tiers=None) -> str:
    """المفتاح الموافق للحجم — ``unknown`` إن غاب الحجم.

    ``tiers`` تسمح بعتبات من إعدادات المستخدم بدل الثابتة؛ غيابها يعني
    الافتراضية، فتبقى الوحدة صالحة للاستعمال بلا Django.
    """
    if quote_volume is None:
        return "unknown"
    try:
        qv = float(quote_volume)
    except (TypeError, ValueError):
        return "unknown"
    if qv < 0 or qv != qv:          # سالب أو NaN
        return "unknown"
    for key, floor, _ in (tiers or TIERS):
        if qv >= floor:
            return key
    return "micro"


def label(key: str) -> str:
    return LABELS.get(key, LABELS["unknown"])


def is_thin(key: str) -> bool:
    """هل تحتاج الإشارة تحذيراً بسبب ضعف السيولة؟"""
    return key in (THIN, "unknown")


def human(quote_volume: float | None) -> str:
    """حجم مختصر للعرض: 1.2م · 340ألف."""
    if quote_volume is None:
        return "—"
    try:
        qv = float(quote_volume)
    except (TypeError, ValueError):
        return "—"
    if qv != qv:
        return "—"
    if qv >= 1_000_000_000:
        return f"{qv / 1_000_000_000:.1f}مليار"
    if qv >= 1_000_000:
        return f"{qv / 1_000_000:.1f}م"
    if qv >= 1_000:
        return f"{qv / 1_000:.0f}ألف"
    return f"{qv:.0f}"


def from_candles(df, timeframe: str) -> float | None:
    """حجم التداول بالعملة المسعّرة خلال 24 ساعة، محسوباً من الشموع.

    لماذا لا نكتفي بما يعطيه المحوّل: بينانس وحده يوفّر حجم 24 ساعة
    جاهزاً، أمّا أسواق الأسهم فتُقرأ رموزها من قائمة ولا مرحلة اكتشاف
    فيها تجلب الأحجام. والشموع في اليد أصلاً وفيها العمود المطلوب،
    فالحساب منها يجعل عمود السيولة يعمل في كل الأسواق بلا طلب إضافي.
    """
    try:
        from .live import timeframe_seconds
    except ImportError:      # pragma: no cover
        return None

    if df is None or getattr(df, "empty", True):
        return None
    if "close" not in df.columns or "volume" not in df.columns:
        return None

    # فريم غير مدعوم يرفع استثناءً — وهذا حقل مرافق لا يجوز أن يُسقط
    # المسح لأجله، فالغياب أفضل من الانهيار
    try:
        seconds = timeframe_seconds(timeframe) or 0
    except (ValueError, KeyError, TypeError):
        return None
    if seconds <= 0:
        return None

    if seconds >= 86_400:
        # شمعة أطول من يوم: نأخذ الأخيرة ونقسّمها على أيامها
        tail = df.tail(1)
        scale = 86_400 / seconds
    else:
        bars = max(1, int(round(86_400 / seconds)))
        tail = df.tail(bars)
        scale = 1.0

    try:
        product = tail["close"] * tail["volume"]
        # sum() في pandas يتجاهل NaN ويعيد 0.0، فعمودُ حجمٍ فارغ تماماً
        # كان يُصنَّف «سيولة دقيقة» بدل «غير معروفة» — وهذا ادّعاء علم
        # لا نملكه، وقد يُخفي رمزاً صالحاً خلف فلتر السيولة
        if product.notna().sum() == 0:
            return None
        total = float(product.sum()) * scale
    except (TypeError, ValueError, AttributeError):
        return None
    if total != total or total < 0:      # NaN أو سالب
        return None
    return total
