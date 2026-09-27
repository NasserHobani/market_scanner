# -*- coding: utf-8 -*-
"""ينشئ المستخدم الأوّل — أو يضبط كلمته.

    python web/manage.py ensure_admin
    python web/manage.py ensure_admin --user nasser

═══ لماذا أمرٌ لا ``createsuperuser`` ═══

``createsuperuser`` تفاعليّ: يسأل ثمّ ينتظر. وتشغيلُه داخل حاوية
عبر ``docker exec`` بلا ‎-it‎ يعلّق بلا رسالة.

وهذا يقرأ من البيئة إن وُجدت، ويولّد كلمةً قويّة إن لم توجد
ويطبعها **مرّة واحدة**.

═══ والكلمة لا تُكتب في ‎docker-compose.yml‎ ═══

ما يدخل ملفّ الـcompose يدخل ``docker history`` ويُقرأ. والمكان
الصحيح متغيّرات البيئة في بورتينر، أو هذا الأمر بلا متغيّر أصلاً
فيُطبع المولَّد ويُنسخ إلى مدير كلمات.
"""
from __future__ import annotations

import os
import secrets
import string

from django.core.management.base import BaseCommand


def _strong(n: int = 20) -> str:
    """كلمةٌ عشوائية من ``secrets`` لا ``random``.

    ``random`` مولّدٌ حتميّ مبذور بالوقت — يصلح للمحاكاة ولا يصلح
    لسرّ. و``secrets`` يقرأ من مصدر النظام.
    """
    alpha = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alpha) for _ in range(n))


class Command(BaseCommand):
    help = "ينشئ مستخدم اللوحة أو يضبط كلمته"

    def add_arguments(self, parser):
        parser.add_argument("--user", default=None)
        parser.add_argument("--password", default=None)
        parser.add_argument("--reset", action="store_true",
                            help="اضبط كلمة الموجود بدل تخطّيه")

    def handle(self, *args, **opts):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        name = (opts.get("user")
                or os.environ.get("ADMIN_USERNAME", "").strip()
                or "admin")
        given = (opts.get("password")
                 or os.environ.get("ADMIN_PASSWORD", "").strip())
        pwd = given or _strong()

        user = User.objects.filter(username=name).first()
        if user and not opts.get("reset"):
            self.stdout.write(
                f"✓ المستخدم «{name}» موجود — لم يُمسّ.\n"
                f"  لضبط كلمته: ensure_admin --user {name} --reset")
            return

        if user:
            user.set_password(pwd)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            action = "ضُبطت كلمة"
        else:
            user = User.objects.create_superuser(username=name, password=pwd)
            action = "أُنشئ"

        self.stdout.write(f"✓ {action} المستخدم «{name}»")
        if given:
            # ═══ لا تُطبع كلمةٌ جاء بها المستخدم ═══
            #
            # سجلّات الحاوية تُقرأ وتُنقل. وطباعةُ ما يعرفه صاحبه
            # أصلاً كشفٌ بلا فائدة.
            self.stdout.write("  الكلمة من البيئة — لم تُطبع.")
        else:
            self.stdout.write(f"  الكلمة (تظهر مرّة واحدة): {pwd}")
            self.stdout.write(
                "  انسخها إلى مدير كلماتك الآن — لا تُحفظ في أيّ ملفّ.")
