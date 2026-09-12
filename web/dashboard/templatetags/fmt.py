# -*- coding: utf-8 -*-
"""مرشّحات عرض الأرقام في القوالب.

المشروع فيه تنسيق موحّد للأسعار في ``scanner.formatting`` — ثلاث خانات
معنوية — وتستعمله كل شاشة تُبنى في JavaScript عبر ``format.js``. أمّا
الجداول المبنيّة في الخادم فكانت تطبع الأرقام خاماً، فيظهر
``0.0759999999999`` مبتوراً في خلية ضيّقة بدل ``0.076``.

الفرق ليس تجميلياً: رقم مبتور يُقرأ خطأً، وسعر بأربع عشرة خانة يوحي
بدقة لا وجود لها — السعر نفسه لا يُنفَّذ بهذه الدقة أصلاً.
"""
from __future__ import annotations

from django import template

from scanner import formatting

register = template.Library()


@register.filter(name="price")
def price(value):
    """سعر بثلاث خانات معنوية — نفس ما يعرضه JavaScript تماماً."""
    return formatting.price(value)


@register.filter(name="rmult")
def rmult(value, digits: int = 2):
    """مضاعف R: خانتان تكفيان، والإشارة تُظهَر صراحةً.

    2.744 تُقرأ «2.74» — الخانة الثالثة ضجيج ناتج عن قسمة لا معلومة.
    """
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v != v:                      # NaN
        return "—"
    return f"{v:+.{int(digits)}f}"


@register.filter(name="num")
def num(value, digits: int = 1):
    """رقم عادي بلا إشارة مفروضة.

    ‏rmult تفرض ‎+‎ لأن مضاعف R يُقرأ ربحاً أو خسارة، أمّا RSI و RVOL
    فموجبان دائماً و«+55.0» فيهما تشويش لا إفادة.
    """
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    d = int(digits)
    text = f"{v:,.{d}f}" if abs(v) >= 1000 else f"{v:.{d}f}"
    return text.rstrip("0").rstrip(".") if "." in text and d else text


@register.filter(name="ratio")
def ratio(value):
    """نسبة العائد إلى المخاطرة بصيغة 1:2.5"""
    return formatting.ratio(value)


@register.filter(name="pct")
def pct(value, digits: int = 1):
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    return f"{v:.{int(digits)}f}%"


@register.filter(name="money")
def money(value):
    """حجم تداول مختصر: 1.2م · 340ألف"""
    from scanner import liquidity

    return liquidity.human(value)


@register.filter(name="span")
def span(value, until=None):
    """مدة بين وقتين بصيغة مقروءة: «3س 20د» · «يومان» · «—».

    تُقاس بأوقات السوق لا أوقات المعالجة — الفرق جوهري: صفقة نُفّذت قبل
    ثلاثة أيام وحُسمت الآن مدتها ثلاثة أيام لا صفر.
    """
    if value is None or until is None:
        return "—"
    try:
        seconds = (until - value).total_seconds()
    except (TypeError, AttributeError):
        return "—"
    if seconds != seconds or seconds < 0:
        return "—"

    days, rest = divmod(int(seconds), 86_400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days >= 1:
        return f"{days}ي" + (f" {hours}س" if hours else "")
    if hours >= 1:
        return f"{hours}س" + (f" {minutes}د" if minutes else "")
    return f"{minutes}د" if minutes else "أقل من دقيقة"
