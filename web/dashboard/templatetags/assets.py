"""وسم أصول ثابتة يحمل بصمة التعديل.

الحاجة: أثناء تطوير الواجهة يبقى المتصفّح على نسخة قديمة من CSS أو JS بعد
التعديل، فيظهر عطب غير موجود في المصدر — عمود لا يمتلئ، أو زر بلا سلوك. إضافة
وقت آخر تعديل إلى الرابط تجعل كل تغيير في الملف رابطاً جديداً، فيسقط التخزين
المؤقّت من نفسه بلا حاجة إلى تفريغ يدوي.
"""
from __future__ import annotations

import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

_stamps: dict[str, str] = {}


def _mtime(path: str) -> str:
    try:
        found = finders.find(path)
        return str(int(os.path.getmtime(found))) if found else ""
    except OSError:
        # ‏بصمة مفقودة أهون بكثير من صفحة ساقطة
        return ""


@register.simple_tag
def asset(path: str) -> str:
    """يعيد رابط الملف الثابت مذيَّلاً ببصمة وقت تعديله."""
    url = static(path)
    # ‏في التطوير نقرأ البصمة كل مرّة: الخادم لا يُعاد تشغيله عند تعديل CSS،
    # فبصمة محفوظة تُبقي المتصفّح على النسخة القديمة — وهو العطب نفسه.
    if settings.DEBUG:
        stamp = _mtime(path)
    else:
        stamp = _stamps.get(path)
        if stamp is None:
            stamp = _mtime(path)
            _stamps[path] = stamp
    return f"{url}?v={stamp}" if stamp else url
