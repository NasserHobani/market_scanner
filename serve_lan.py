# -*- coding: utf-8 -*-
"""تشغيل اللوحة على الشبكة المحلية.

    python serve_lan.py            # المنفذ 8000
    python serve_lan.py 8080

لماذا ملف مستقل بدل تمرير 0.0.0.0 لـ runserver مباشرة:

الفتح على الشبكة يحتاج ثلاثة أشياء معاً وإلا ظهرت أخطاء غامضة —
ALLOWED_HOSTS وإلا «Bad Request (400)»، و CSRF_TRUSTED_ORIGINS وإلا
عملت الصفحات وفشلت كل الأزرار بـ 403، وإطفاء DEBUG وإلا عُرض أثر
الاستثناء كاملاً لكل زائر. هذا الملف يضبطها ويطبع العنوان الذي
تفتحه من جوالك.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANAGE = ROOT / "web" / "manage.py"


def lan_ip() -> str | None:
    """عنوان الجهاز على الشبكة — بلا إرسال أي بيانات."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip if not ip.startswith("127.") else None
    except OSError:
        return None


def main(argv: list[str]) -> int:
    port = "8000"
    for arg in argv[1:]:
        if arg.isdigit():
            port = arg

    if not MANAGE.exists():
        print(f"لم أجد {MANAGE}")
        return 1

    ip = lan_ip()
    env = dict(os.environ)
    env["SCANNER_LAN"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    # تُفرض هنا لا تُترك للاكتشاف: ملف .env يحمل DJANGO_ALLOWED_HOSTS
    # و DJANGO_DEBUG من التنصيب، و_load_env في settings يضع ما في .env
    # في البيئة إن لم يكن موجوداً — فوضعها هنا يجعلها هي الغالبة.
    hosts = {"localhost", "127.0.0.1", "[::1]", socket.gethostname()}
    if ip:
        hosts.add(ip)
    for extra in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(","):
        if extra.strip():
            hosts.add(extra.strip())
    env["DJANGO_ALLOWED_HOSTS"] = ",".join(sorted(h for h in hosts if h))
    # DEBUG مطفأ قسراً: تركه يعرض المسارات والإعدادات لكل زائر، ولا
    # يجوز أن يعتمد ذلك على قيمة في .env كتبها التنصيب
    env["DJANGO_DEBUG"] = "0"

    bar = "═" * 60
    print(bar)
    print("  ماسح الأسواق — مفتوح على الشبكة المحلية")
    print(bar)
    if ip:
        print(f"  من هذا الجهاز : http://127.0.0.1:{port}/")
        print(f"  من الشبكة     : http://{ip}:{port}/")
    else:
        print(f"  http://127.0.0.1:{port}/")
        print("  ⚠ لم أتعرّف على عنوان الشبكة — تحقّق من اتصالك بالواي فاي")
    print()
    print("  ⚠ الواجهة بلا كلمة مرور: كل من على الشبكة يستطيع تشغيل")
    print("     المسح وتغيير الإعدادات وإرسال رسائل تيليجرام.")
    print("     لا تستعملها على شبكة عامة (مقهى، فندق، مكتب مشترك).")
    print()
    print("  إن لم تفتح من جهاز آخر فالسبب غالباً جدار حماية ويندوز —")
    print("  اسمح لـ Python بالوصول عند ظهور النافذة، أو من PowerShell")
    print("  بصلاحيات مدير:")
    print(f'    netsh advfirewall firewall add rule name="MarketScanner" '
          f"dir=in action=allow protocol=TCP localport={port}")
    print(bar)
    print()

    # ‎--insecure‎ ضروري لا اختياري: runserver يخدم الملفات الساكنة حين
    # DEBUG مشتغل فقط، وقد أطفأناه لأمان الشبكة. بدونه تُفتح اللوحة
    # بلا CSS ولا JavaScript — صفحة بيضاء بنصّ عارٍ.
    cmd = [sys.executable, str(MANAGE), "runserver", "--insecure",
           f"0.0.0.0:{port}"]
    try:
        return subprocess.call(cmd, env=env, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\nتوقّف.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
