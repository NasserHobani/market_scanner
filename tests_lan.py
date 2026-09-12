# -*- coding: utf-8 -*-
"""اختبارات الفتح على الشبكة — بلا Django.

ثلاثة أعطال تظهر عند الفتح على 0.0.0.0 وكلها رسائلها غامضة:
«Bad Request (400)» من ALLOWED_HOSTS، و403 عند كل زرّ من
CSRF_TRUSTED_ORIGINS، وتسريب أثر الاستثناء من DEBUG. تُختبر هنا
بتنفيذ الكود الحقيقي من settings.py لا نسخة منه.

    python tests_lan.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SETTINGS = ROOT / "web" / "config" / "settings.py"

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


SRC = SETTINGS.read_text(encoding="utf-8")
BLOCK = SRC[SRC.index("def _secret_key()"):
            SRC.index("CSRF_TRUSTED_ORIGINS = [")]
BLOCK += SRC[SRC.index("CSRF_TRUSTED_ORIGINS = ["):
             SRC.index("]", SRC.index("CSRF_TRUSTED_ORIGINS = [")) + 1]


def run(env: dict, project_root: Path) -> dict:
    """ينفّذ كتلة إعدادات الشبكة ببيئة مضبوطة ويعيد الأسماء الناتجة."""
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    ns = {"os": os, "PROJECT_ROOT": project_root, "print": lambda *a, **k: None}
    try:
        exec(compile(BLOCK, str(SETTINGS), "exec"), ns)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return ns


import tempfile

TMP = Path(tempfile.mkdtemp())

# ── الوضع المحلي ──
local = run({}, TMP)
check("محلياً: DEBUG مشتغل", local["DEBUG"] is True)
check("محلياً: المضيفون localhost فقط",
      set(local["ALLOWED_HOSTS"]) == {"localhost", "127.0.0.1", "[::1]"},
      local["ALLOWED_HOSTS"])

# ── وضع الشبكة ──
lan = run({"SCANNER_LAN": "1"}, TMP)
check("على الشبكة: DEBUG ينطفئ تلقائياً", lan["DEBUG"] is False,
      "تركُه يعرض المسارات والإعدادات لكل زائر")
check("على الشبكة: تُضاف عناوين الجهاز",
      len(lan["ALLOWED_HOSTS"]) > 3 and "127.0.0.1" in lan["ALLOWED_HOSTS"],
      lan["ALLOWED_HOSTS"])
check("وأصول CSRF تغطّي كل مضيف بمنفذيه",
      all(f"http://{h}:8000" in lan["CSRF_TRUSTED_ORIGINS"]
          for h in lan["ALLOWED_HOSTS"] if "*" not in h),
      lan["CSRF_TRUSTED_ORIGINS"][:3])
check("والأصول تبدأ بمخطط صالح",
      all(re.match(r"^https?://", o) for o in lan["CSRF_TRUSTED_ORIGINS"]))

# ── الحالة التي وقعت فعلاً: .env يحمل قيماً من التنصيب ──
# _load_env في settings يضع ما في .env في البيئة قبل قراءتها، فبيئة
# «نظيفة» في الاختبار تخفي عطباً حقيقياً.
from_env = run({"SCANNER_LAN": "1",
                "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
                "DJANGO_DEBUG": "1"}, TMP)
check("‏.env بمضيفَي localhost لا يمنع إضافة عنوان الشبكة",
      len(from_env["ALLOWED_HOSTS"]) > 2,
      from_env["ALLOWED_HOSTS"])
check("والمضيفون المكتوبون في .env يبقون",
      "localhost" in from_env["ALLOWED_HOSTS"]
      and "127.0.0.1" in from_env["ALLOWED_HOSTS"])

# ── التجاوز اليدوي ──
manual = run({"SCANNER_LAN": "1", "DJANGO_ALLOWED_HOSTS": "10.0.0.5, box.local"},
             TMP)
check("المضيف المحدّد يدوياً يُضاف لا يُلغى",
      {"10.0.0.5", "box.local"} <= set(manual["ALLOWED_HOSTS"]),
      manual["ALLOWED_HOSTS"])
check("والمسافات تُنظَّف", "box.local" in manual["ALLOWED_HOSTS"])

off = run({"DJANGO_ALLOWED_HOSTS": "10.0.0.5,box.local"}, TMP)
check("خارج وضع الشبكة تبقى القائمة حصرية",
      off["ALLOWED_HOSTS"] == ["10.0.0.5", "box.local"], off["ALLOWED_HOSTS"])

debugged = run({"SCANNER_LAN": "1", "DJANGO_DEBUG": "1"}, TMP)
check("DEBUG يبقى قابلاً للتشغيل صراحةً", debugged["DEBUG"] is True)

# ── المفتاح السرّي ──
fresh = Path(tempfile.mkdtemp())
one = run({}, fresh)
check("يُولَّد مفتاح حقيقي بدل الافتراضي",
      one["SECRET_KEY"] not in ("", "dev-only-change-me")
      and len(one["SECRET_KEY"]) >= 40, len(one["SECRET_KEY"]))
env_file = fresh / ".env"
check("ويُحفظ في .env ليثبت بين التشغيلات",
      env_file.exists() and "DJANGO_SECRET_KEY=" in env_file.read_text("utf-8"))

given = run({"DJANGO_SECRET_KEY": "مفتاحي-الخاص"}, fresh)
check("المفتاح المحدّد يُحترم ولا يُستبدل",
      given["SECRET_KEY"] == "مفتاحي-الخاص")

old = run({"DJANGO_SECRET_KEY": "dev-only-change-me"}, Path(tempfile.mkdtemp()))
check("المفتاح الافتراضي القديم يُستبدل لا يُقبل",
      old["SECRET_KEY"] != "dev-only-change-me")

readonly = run({}, Path("/لا/يوجد/مسار"))
check("تعذّر الكتابة لا يُسقط التشغيل",
      isinstance(readonly["SECRET_KEY"], str) and readonly["SECRET_KEY"])

# ── المشغّل ──
serve = (ROOT / "serve_lan.py").read_text(encoding="utf-8")
check("المشغّل يربط على 0.0.0.0", "0.0.0.0:" in serve)
check("ويمرّر --insecure (وإلا فلا CSS ولا JS مع DEBUG مطفأ)",
      '"--insecure"' in serve,
      "runserver لا يخدم الملفات الساكنة حين DEBUG=False")
check("ويضبط وضع الشبكة", 'SCANNER_LAN"] = "1"' in serve)
check("ويحذّر من غياب الحماية", "بلا كلمة مرور" in serve)
check("ويرشد لجدار الحماية", "netsh advfirewall" in serve)
check("ويفرض المضيفين فوق .env",
      'env["DJANGO_ALLOWED_HOSTS"]' in serve,
      "بدونه يغلب DJANGO_ALLOWED_HOSTS المكتوب في .env")
check("ويفرض إطفاء DEBUG فوق .env",
      'env["DJANGO_DEBUG"] = "0"' in serve,
      "‏.env من التنصيب فيه DJANGO_DEBUG=1")
check("ويضيف عنوان الشبكة المكتشف للمضيفين",
      "hosts.add(ip)" in serve)
bat = (ROOT / "serve_lan.bat").read_bytes()
check("ملف bat بترميز ASCII خالص (cmd يفسد غيره)",
      all(b < 128 for b in bat))

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
