# -*- coding: utf-8 -*-
"""كل ملفٍّ ساكن يُشار إليه موجودٌ فعلاً.

═══ العطب الذي أوجب هذا الفحص ═══

كُتب في صفحة الدخول:

    {% static 'dashboard/ds.css' %}

وهو اسمٌ **لا وجود له** — الملفّ الحقيقيّ ``design-system.css``.

ولم يظهر شيء محلّياً: ``DEBUG=1`` يقدّم الملفّات من القرص ويكتفي
بـ‏404 على الناقص، فتُفتح الصفحة بلا نمطٍ وتعمل.

وعلى الخادم ``DEBUG=0`` وخزّانُ الملفّات
``CompressedManifestStaticFilesStorage``: يبحث عن الاسم في بيان
البصمات، فإن لم يجده **رمى ``ValueError``**. فصارت صفحة الدخول
‏500 — وهي الصفحة التي يمرّ بها كل شيء بعد إضافة الاستيثاق.

أي أنّ خطأ حرفٍ في اسم ملفٍّ أقفل اللوحة كلّها، ولم يظهر إلّا في
الإنتاج.

═══ ولماذا فحصٌ نصّيّ لا تشغيل ═══

التحقّق الحقيقيّ يحتاج Django مُقلِعاً وبياناً مبنيّاً
(``collectstatic``). وهذا يقرأ القوالب ويطابق الأسماء بالقرص —
أرخص بكثير، ويُمسك الصنف نفسه من الأخطاء: اسمٌ مكتوبٌ خطأً.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from tests_helpers import Checks  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

TPL = ROOT / "web" / "dashboard" / "templates"
STATIC = ROOT / "web" / "dashboard" / "static"

# ‏{% asset 'x' %} و {% static "x" %} — بأيّ نوعٍ من الاقتباس
REF = re.compile(r"{%\s*(?:asset|static)\s+['\"]([^'\"]+)['\"]")

templates = sorted(TPL.rglob("*.html"))
c("١ القوالب تُقرأ", len(templates) > 10, str(len(templates)))

missing: list[str] = []
checked = 0

for t in templates:
    try:
        text = t.read_text(encoding="utf-8")
    except OSError:
        continue
    for ref in REF.findall(text):
        # الروابط الخارجية لا تُفحص هنا
        if ref.startswith(("http://", "https://", "//")):
            continue
        checked += 1
        if not (STATIC / ref).exists():
            missing.append(f"{t.name}: {ref}")

c("  ومراجعُها تُعدّ", checked > 20, str(checked))
c("٢ لا ملفّ ساكن مفقود", not missing,
  " · ".join(missing[:6]) or "")

# ═══ والملفّ الذي أسقط الإنتاج ═══
#
# فحصٌ صريحٌ عليه: نسيانُ العلاج أسهل من كتابته.
login = TPL / "dashboard" / "login.html"
c("٣ صفحة الدخول موجودة", login.exists())
if login.exists():
    txt = login.read_text(encoding="utf-8")
    c("  ولا تشير إلى ‎ds.css‎", "ds.css" not in txt, "عاد الاسم الخاطئ")
    c("  وتحمّل ملفّ النظام", "design-system.css" in txt)
    # ═══ وتعمل بلا شبكةٍ خارجية ═══
    #
    # الشبكة التي تحجب cdnjs تترك الصفحة بلا نمط، فتبدو معطوبة
    # ويُظنّ الخادم ساقطاً.
    c("  وألوانٌ احتياطية فيها", "background:#0f1115" in txt)

# ═══════════ ٣ب) ‎{#‎ يعلّق سطراً لا كتلة ═══════════
#
# ═══ العطب الثاني في الملفّ نفسه ═══
#
# ‏‎{#‎ في قوالب Django يعلّق **سطراً واحداً**. فكتلةٌ تمتدّ أسطراً
# تُحلَّل قالباً عادياً بعد سطرها الأوّل:
#
#   ١. نصّ الشرح يظهر في الصفحة للزائر.
#   ٢. وإن ضمّ الشرح وسماً بين ‎{% %}‎ — ولو داخل اقتباسٍ في
#      الشرح — حاول المحلّل تنفيذه.
#
# وهذا ما وقع: شرحٌ يذكر ``{% static %}`` أسقط صفحة الدخول كلّها
# بـ``TemplateSyntaxError: Invalid block tag on line 8``. وهي
# الصفحة التي يمرّ بها كل شيء بعد الاستيثاق.
#
# والكتلة تُكتب ‎{% comment %}…{% endcomment %}‎.
multiline: list[str] = []
for t in templates:
    try:
        lines = t.read_text(encoding="utf-8").splitlines()
    except OSError:
        continue
    for i, line in enumerate(lines, start=1):
        if "{#" in line and "#}" not in line:
            multiline.append(f"{t.name}:{i}")

c("٣ب لا تعليق ‎{#‎ متعدّد الأسطر", not multiline,
  " · ".join(multiline[:6]) or "")


# ═══════════ ٤) الخروج استمارة لا رابط ═══════════
#
# ‏Django 5 يرفض GET على ``LogoutView`` ويردّ 405.
base = TPL / "dashboard" / "base.html"
if base.exists():
    b = base.read_text(encoding="utf-8")
    c("٤ زرّ الخروج موجود", "url 'logout'" in b)
    _seg = b.split("url 'logout'")[0][-260:] if "url 'logout'" in b else ""
    c("  وبـ‎POST‎ لا رابط", 'method="post"' in _seg, _seg[-120:])
    c("  ومحميّ بـ‎csrf‎",
      "csrf_token" in b.split("url 'logout'")[1][:200]
      if "url 'logout'" in b else False)

# ═══════════ ٥) قائمة السماح تشمل ما تحتاجه صفحة الدخول ═══════════
ag = (ROOT / "web" / "dashboard" / "authgate.py").read_text(encoding="utf-8")
for p in ("/healthz", "/accounts/login", "/static/"):
    c(f"٥ {p} مستثنى", f'"{p}"' in ag)
# ═══ والخروج مستثنى أيضاً ═══
#
# جلسةٌ انتهت ثمّ ضغطُ «خروج» يعني تحويلاً إلى الدخول ثمّ إلى
# الخروج — حلقةٌ تبدو تعليقاً.
c("  والخروج كذلك", '"/accounts/logout"' in ag)


sys.exit(c.report())
