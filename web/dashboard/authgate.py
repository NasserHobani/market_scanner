# -*- coding: utf-8 -*-
"""بوّابة الاستيثاق — كل صفحةٍ إلّا ما استُثني صراحةً.

═══ لماذا الآن ═══

لم يكن في هذا المشروع ``login_required`` واحد. وكان ذلك مقبولاً
حين كانت الشاشات تعرض نتائج مسحٍ عامّة: من بلغ المنفذ رأى تحليلاً
لا يخصّه.

وربطُ المحفظة يغيّر ذلك تماماً. الرصيد والصفقات وتاريخ الشراء
بياناتٌ تخصّ صاحبها وحده، ومسحٌ روتينيّ للشبكة يكفي لقراءتها.

═══ وقائمة سماحٍ لا قائمة منع ═══

القائمة هنا **بيضاء**: كل شيء محميّ إلّا ما ذُكر. والعكس — منعُ
ما يُذكر — يعني أنّ كل صفحةٍ جديدة تُولد مكشوفة، ويُنسى إضافتها.

═══ و‎/healthz/‎ أوّل المستثنيات ═══

فحص صحّة Docker ينادي ``curl http://127.0.0.1:8000/healthz/`` بلا
جلسة. وتحويلُه إلى صفحة دخول يعيد ‎302‎، فيراه ``curl -f`` نجاحاً
مزيّفاً أو فشلاً دائماً بحسب الراية — وفي الحالتين الحاوية تكذب
عن حالتها.

═══ والملفّات الساكنة ═══

‏whitenoise يخدمها قبل هذا الوسيط في أغلب الإعدادات، لكن ترتيب
الوسائط قد يتغيّر. واستثناؤها هنا يجعل صفحة الدخول نفسها تصل
بتنسيقها — وصفحةُ دخولٍ بلا CSS تبدو عطباً.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import JsonResponse

#: مسارات تُخدَم بلا جلسة. البادئة تكفي — لا حاجة لمطابقةٍ تامّة.
PUBLIC_PREFIXES = (
    "/healthz",
    "/accounts/login",
    "/accounts/logout",
    "/static/",
)


def _enabled() -> bool:
    """البوّابة مُفعَّلة ما لم تُطفأ صراحةً.

    ═══ والافتراض هو التشغيل ═══

    راية تُشغّل الحماية تعني أنّ نسيانها يترك الباب مفتوحاً. وراية
    تُطفئها تعني أنّ نسيانها يترك الباب مغلقاً. والثاني هو
    الاتّجاه الآمن للفشل.
    """
    return os.environ.get("REQUIRE_LOGIN", "1").strip() != "0"


def is_public(path: str) -> bool:
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


class LoginRequiredMiddleware:
    """يفرض جلسةً على كل طلبٍ غير مستثنى."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not _enabled() or is_public(request.path):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return self.get_response(request)

        # ═══ نداء البيانات لا يُحوَّل ═══
        #
        # صفحةٌ تُحوَّل إلى الدخول. أمّا ``fetch`` فيتبع التحويل
        # بصمت ويستقبل **صفحة HTML** يحاول تحليلها JSON — فيسقط
        # بـ«Unexpected token <» الذي لا يدلّ على شيء.
        #
        # فالنداء يُردّ بـ‎401‎ وسببٍ مكتوب، والواجهة تعرف ما تفعل.
        if request.path.startswith("/api/"):
            return JsonResponse(
                {"ok": False, "auth": False,
                 "reason": "انتهت الجلسة — سجّل الدخول ثمّ أعد المحاولة"},
                status=401)

        return redirect_to_login(
            request.get_full_path(),
            settings.LOGIN_URL or "/accounts/login/")
