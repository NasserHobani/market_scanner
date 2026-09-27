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

DEFAULT_PATHS = ["/healthz/", "/accounts/login/", "/"]


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

    paths = sys.argv[1:] or DEFAULT_PATHS
    bad = 0

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


def _host(settings) -> str:
    """اسمٌ يقبله ``ALLOWED_HOSTS`` — وإلّا ردّ كل طلبٍ بـ400.

    و‏``testserver`` يُقبل تلقائياً في الاختبارات لا هنا.
    """
    hosts = [h for h in (settings.ALLOWED_HOSTS or []) if h not in ("*",)]
    return hosts[0] if hosts else "localhost"


if __name__ == "__main__":
    raise SystemExit(main())
