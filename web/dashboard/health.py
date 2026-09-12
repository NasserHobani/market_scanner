# -*- coding: utf-8 -*-
"""‏/healthz/ — هل يستجيب التطبيق فعلاً؟

═══ لماذا لا تكفي الصفحة الرئيسة ═══

فحص الصحّة يُنادى كل ثلاثين ثانية. والصفحة الرئيسة تستعلم عن
الصفقات والمراقبة والمهامّ، فيصير الفحص نفسه حِملاً على القاعدة —
ويصير بطء القاعدة سبباً في «الحاوية غير صحّية» فتُعاد تشغيلاً،
فيزداد الحمل. حلقةٌ تبدأ من أداة القياس.

═══ وما يفحصه ═══

استعلامٌ واحد ‏``SELECT 1``. وهذا يفصل الحالتين اللتين تبدوان
واحدة من الخارج:

    · العملية حيّة والقاعدة مقطوعة → 503، وتُعاد الحاوية
    · العملية معلّقة كلّياً         → لا ردّ، والمهلة تكشفه

و«الحاوية تعمل» وحدها لا تقول أيّاً منهما.

═══ ولا يُحمى بتسجيل دخول ═══

فاحص Docker لا يملك جلسة. ولا يكشف هذا المسار شيئاً: كلمة واحدة
ورمز حالة، بلا نسخة ولا إعدادات ولا أسماء جداول.
"""
from __future__ import annotations

from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def healthz(request) -> HttpResponse:
    from django.db import connections

    try:
        with connections["default"].cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        # السبب يُكتب في السجلّ لا في الرد: الرد قد يُقرأ من خارج
        # الشبكة، ونصّ خطأ القاعدة يذكر المضيف واسم القاعدة.
        import logging

        logging.getLogger("dashboard.health").error(
            "فحص الصحّة فشل: %s", str(exc)[:200])
        return HttpResponse("db\n", status=503, content_type="text/plain")

    return HttpResponse("ok\n", content_type="text/plain")
