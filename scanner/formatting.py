"""تنسيق موحّد للأسعار عبر المشروع.

المشكلة التي يحلّها: السعر 65029.98 و0.011230 و510.4 لا يمكن تنسيقها
بعدد ثابت من الخانات. ثلاث خانات معنوية بعد أول رقم مؤثر تعطي دقة كافية
للتداول ومظهراً موحّداً مهما اختلف حجم السعر.
"""
from __future__ import annotations

import math

SIGNIFICANT = 3


def price(value, digits: int = SIGNIFICANT) -> str:
    """صيغة السعر: ثلاث خانات معنوية، مع فاصل الآلاف للأرقام الكبيرة."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(v):
        return "—"
    if v == 0:
        return "0"

    magnitude = abs(v)
    if magnitude >= 1000:
        return f"{v:,.2f}"
    if magnitude >= 1:
        return _trim(f"{v:.{digits}f}")

    # أقل من واحد: نحسب الخانات اللازمة لإظهار ثلاث خانات معنوية
    leading_zeros = -math.floor(math.log10(magnitude)) - 1
    return _trim(f"{v:.{leading_zeros + digits}f}")


def _trim(text: str) -> str:
    """حذف الأصفار الزائدة: 510.400 → 510.4 و 27.000 → 27"""
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def percent(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(v):
        return "—"
    return f"{v:+.{digits}f}%"


def ratio(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"1:{v:.{digits}f}".rstrip("0").rstrip(".") if math.isfinite(v) else "—"
