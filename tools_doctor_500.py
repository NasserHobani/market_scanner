# -*- coding: utf-8 -*-
"""ما الذي يسقط في صفحةٍ تعطي ‏500 — بالأثر الحقيقيّ لا بالتخمين.

    docker exec <web> python tools_doctor_500.py
    docker exec <web> python tools_doctor_500.py /accounts/login/

═══ لماذا أداة ═══

‏``DEBUG=0`` يعطي «Server Error (500)» وحدها — وهو الصواب: صفحة
الأثر تعرض الإعدادات والمسارات وأجزاءً من البيئة، وعرضُها على
خادمٍ مكشوف تسريب.

والأثر موجودٌ في سجلّ الحاوية، لكنّه يضيع بين سطور gunicorn
وطلبات الفحص الصحّي كل ثلاثين ثانية.

وهذه تستدعي الصفحة **داخل العملية** بعميل اختبار Django، فيُرفَع
الاستثناء كما هو ويُطبع أثره كاملاً — بلا تشغيل ``DEBUG=1`` ولا
كشف شيء للشبكة.

═══ وما تفحصه افتراضياً ═══

المسارات التي يمرّ بها كل شيء: الدخول، والصحّة، والجذر. فإن سقط
أوّلها أُقفلت اللوحة كلّها مهما سلم سواها.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# ═══ كل صفحةٍ مسّها التعديل الأخير ═══
#
# الفحص على ثلاث صفحاتٍ كان يترك الباقي مجهولاً — وصفحةٌ لا تُطلَب
# لا يُكتشَف عطبها حتى تُفتح. والطلب هنا بلا جلسة، فالمحميّة تردّ
# ‏302 إلى الدخول — وهو **نجاح**: يعني أنّ الوسيط يعمل والصفحة
# سليمة إلى حدّ التحويل.
DEFAULT_PATHS = [
    "/healthz/", "/accounts/login/", "/",
    "/wallet/", "/watches/", "/trades/", "/scanner/", "/btc/",
    "/strategies/", "/board/", "/symbols/", "/topdown/", "/jobs/",
    "/settings/", "/paper/",
]


def main() -> int:
    import django

    print(__doc__.strip().splitlines()[0])
    print()

    try:
        django.setup()
    except Exception:  # noqa: BLE001
        print("✗ سقط ``django.setup()`` نفسه — الخطأ في الإعدادات:")
        traceback.print_exc()
        return 1

    from django.conf import settings
    from django.test import Client

    print(f"‏DEBUG={settings.DEBUG} · "
          f"ALLOWED_HOSTS={settings.ALLOWED_HOSTS}")
    print(f"خزّان الملفّات الساكنة: "
          f"{settings.STORAGES.get('staticfiles', {}).get('BACKEND', '—')}"
          if hasattr(settings, "STORAGES") else "")
    print()

    # ═══ كل قالبٍ يُترجَم أوّلاً ═══
    #
    # الطلبُ يمسّ ما يمسّه: صفحةٌ لا تُطلَب لا يُكتشَف عطبها حتى
    # تُفتح. والترجمة تمرّ على الجميع في أجزاء من الثانية، وتمسك
    # ``TemplateSyntaxError`` كلّه — لا نمطاً واحداً منه.
    bad = _compile_templates()

    paths = sys.argv[1:] or DEFAULT_PATHS

    for path in paths:
        # ═══ ``raise_request_exception`` هي الفائدة كلّها ═══
        #
        # بدونها يبتلع العميل الاستثناء ويعيد 500 كالمتصفّح تماماً
        # — فلا تضيف الأداة شيئاً.
        client = Client(raise_request_exception=True,
                        SERVER_NAME=_host(settings))
        print(f"── {path}")
        try:
            resp = client.get(path, follow=False)
        except Exception:  # noqa: BLE001
            bad += 1
            print("   ✗ استثناء — وهذا هو سبب الـ500:")
            print()
            traceback.print_exc()
            print()
            continue

        code = resp.status_code
        mark = "✓" if code < 400 else "✗"
        if code >= 400:
            bad += 1
        extra = ""
        if code in (301, 302):
            extra = f" ← {resp.headers.get('Location', '')}"
        print(f"   {mark} {code}{extra}")

    print()
    if bad:
        print("⇒ انسخ الأثر أعلاه كاملاً. والسطر الأخير فيه هو السبب،")
        print("  والسطر الذي قبله يقول في أيّ ملفٍّ ورقم سطر.")
    else:
        print("⇒ كل المسارات تستجيب. فإن بقي 500 في المتصفّح فالسبب")
        print("  خارج التطبيق: وكيلٌ عكسيّ أمامه، أو ترويسة Host لا")
        print("  تطابق DJANGO_ALLOWED_HOSTS.")
    return 1 if bad else 0


def _compile_templates() -> int:
    """يترجم كل قالبٍ في المشروع ويعيد عدد الساقط.

    ═══ الترجمة لا التصيير ═══

    ``get_template`` يحلّل الوسوم ولا ينفّذها — فلا يحتاج سياقاً
    ولا قاعدةً ولا بيان بصمات. وهو ما يمسك:

        ‏{# كتلةٌ متعدّدة الأسطر   →  ‎{#‎ يعلّق سطراً واحداً فقط،
                                     فما بعده يُحلَّل قالباً
        وسمٌ بلا ‎{% load %}‎      →  ``Invalid block tag``
        ‎{% if %}‎ بلا ‎{% endif %}‎

    وكلّها أخطاءٌ لا تظهر إلّا عند فتح الصفحة — وقد لا تُفتح حتى
    ينشر المرء ويستعمل.
    """
    from django.template.loader import get_template
    from django.template.exceptions import TemplateSyntaxError

    root = Path(__file__).parent / "web"
    files = sorted(root.rglob("templates/**/*.html"))
    if not files:
        print("⚠ لم يُعثر على قوالب — تخطّي الترجمة")
        return 0

    bad = 0
    for f in files:
        # الاسم كما يراه المحمّل: ما بعد ``templates/``
        parts = f.parts
        try:
            i = len(parts) - 1 - parts[::-1].index("templates")
        except ValueError:
            continue
        name = "/".join(parts[i + 1:])
        try:
            get_template(name)
        except TemplateSyntaxError as exc:
            bad += 1
            print(f"   ✗ {name}")
            print(f"     {exc}")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print(f"   ✗ {name} — {type(exc).__name__}: {str(exc)[:160]}")

    mark = "✓" if not bad else "✗"
    print(f"── ترجمة القوالب: {mark} {len(files) - bad}/{len(files)}")
    print()
    return bad


def _host(settings) -> str:
    """اسمٌ يقبله ``ALLOWED_HOSTS`` — وإلّا ردّ كل طلبٍ بـ400.

    و‏``testserver`` يُقبل تلقائياً في الاختبارات لا هنا.
    """
    hosts = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*",)]
    return hosts[0] if hosts else "localhost"


if __name__ == "__main__":
    raise SystemExit(main())
