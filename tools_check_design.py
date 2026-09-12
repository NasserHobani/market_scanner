# -*- coding: utf-8 -*-
"""فاحص نظام التصميم — يمنع عودة ما أُصلح.

═══ العطب الذي وقع فعلاً ═══

كانت ``--warn`` و``--dim`` معرَّفتين **مرّتين** بقيمتين مختلفتين::

    base.html            --warn:#e0b341   --dim:#8b93a7
    design-system.css    --warn:#e8c05a   --dim:#97a0b5

و``base.html`` يأتي بعد الرابط فيغلب. أي أنّ نصف رموز نظام التصميم
كان ميّتاً بلا أن يصرخ شيء: تُغيَّر القيمة في «مصدر الحقيقة الوحيد»
فلا يتغيّر شيء على الشاشة.

ولا اختبارَ يكشف هذا: الصفحة تعمل، والألوان تظهر، والفرق بين
``#e0b341`` و``#e8c05a`` لا تراه العين. فالفاحص يقرأ التعريفات
ويعدّها.

═══ وما يحرسه ═══

    ١) كل رمز يُعرَّف مرّة واحدة.
    ٢) كل ``var(--x)`` مستعملٍ له تعريف.
    ٣) لا لون صلب جديد في القوالب — الرموز أو لا شيء.
    ٤) الخطوط الثلاثة لها بديل محلّي (الشبكة تنقطع).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CSS_DIR = ROOT / "web" / "dashboard" / "static" / "dashboard"
TPL_DIR = ROOT / "web" / "dashboard" / "templates" / "dashboard"

problems: list[str] = []
notes: list[str] = []

# ── ١) الرموز تُعرَّف مرّة واحدة ──
#
# التعريف داخل ``@media`` أو صنفٍ مشروط ليس تكراراً بل تخصيص —
# فلا يُحسب إلّا ما كان في ``:root`` مباشرة.
_ROOT_BLOCK = re.compile(r":root\s*\{(.*?)\}", re.S)
_MEDIA = re.compile(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", re.S)
_DEF = re.compile(r"(--[a-z0-9-]+)\s*:", re.I)

defined: dict[str, list[str]] = {}
for path in sorted(CSS_DIR.glob("*.css")) + sorted(TPL_DIR.glob("*.html")):
    text = path.read_text(encoding="utf-8")
    # ‏‎:root‎ داخل ‎@media‎ إعادةُ ضبطٍ للمقاس لا تعريفٌ ثانٍ:
    # ‎--ds-fs-display‎ يصغر على الشاشات الضيّقة عمداً.
    text = _MEDIA.sub(" ", text)
    for block in _ROOT_BLOCK.findall(text):
        for name in _DEF.findall(block):
            defined.setdefault(name, []).append(path.name)

for name, files in sorted(defined.items()):
    if len(files) > 1:
        problems.append(
            f"الرمز {name} معرَّف {len(files)} مرّات: {' · '.join(files)}"
            " — الأخير يغلب، والباقي ميّت")

# ── ٢) كل مستعمَل معرَّف ──
_USE = re.compile(r"var\(\s*(--[a-z0-9-]+)", re.I)
known = set(defined)
# رموز Bootstrap تأتي من ملفّه لا من ملفّاتنا
external = lambda n: n.startswith("--bs-")

missing: dict[str, set[str]] = {}
for path in (sorted(CSS_DIR.glob("*.css")) + sorted(TPL_DIR.glob("*.html"))
             + sorted(CSS_DIR.glob("*.js"))):
    text = path.read_text(encoding="utf-8")
    for name in _USE.findall(text):
        if name not in known and not external(name):
            missing.setdefault(name, set()).add(path.name)
for name, files in sorted(missing.items()):
    problems.append(f"الرمز {name} مستعمَل ولا تعريف له: {' · '.join(sorted(files))}")

# ── ٣) لا لون صلب جديد في القوالب ──
#
# اللون الصلب في قالبٍ ينجو من كل تغيير للسمة: تُبدَّل اللوحة
# فيبقى هو، فيبدو العنصر غريباً بلا سبب ظاهر.
_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# استثناءات مقصودة، ولكلٍّ سبب
ALLOWED_HEX = {
    "#00243f",   # نصّ فوق الأزرق النشِط — تباينٌ محسوب لا رمز
}
for path in sorted(TPL_DIR.glob("*.html")):
    text = path.read_text(encoding="utf-8")
    # التعليقات لا تُحاسَب: الشرح يذكر القيم القديمة عمداً
    text = re.sub(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "",
                  text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    hits = {h for h in _HEX.findall(text) if h.lower() not in
            {a.lower() for a in ALLOWED_HEX}}
    if hits:
        problems.append(f"{path.name}: لون صلب {' · '.join(sorted(hits))}"
                        " — استعمل رمزاً")

# ── ٤) الخطوط لها بديل محلّي ──
css = (CSS_DIR / "design-system.css").read_text(encoding="utf-8")
for token, remote in (("--ds-font-head", "Hanken Grotesk"),
                      ("--ds-font-body", "IBM Plex Sans"),
                      ("--ds-font-mono", "JetBrains Mono")):
    m = re.search(rf"{token}\s*:([^;]+);", css, re.S)
    if not m:
        problems.append(f"الخطّ {token} غير معرَّف")
        continue
    value = " ".join(m.group(1).split())
    if remote not in value:
        problems.append(f"{token} لا يذكر {remote}")
    # ═══ البديل ليس ترفاً ═══
    #
    # الخطوط من CDN. وشبكةٌ منقطعة بلا بديل تُسقط الصفحة على خطّ
    # المتصفّح الافتراضي — وهو غالباً بلا محارف عربية مقبولة.
    tail = value.split(",")[1:]
    if not any(x.strip().strip('"') in
               ("Segoe UI", "Tahoma", "system-ui", "ui-monospace", "monospace",
                "Cascadia Code", "Consolas", "sans-serif")
               for x in tail):
        problems.append(f"{token} بلا بديل محلّي — الشبكة تنقطع")

# ── ٥) الشريط الجانبي مصدرٌ واحد ──
base = (TPL_DIR / "base.html").read_text(encoding="utf-8")
if "_rail.html" not in base:
    problems.append("base.html لا يضمّ الشريط الجانبي")
rail = (TPL_DIR / "_rail.html").read_text(encoding="utf-8")
if "nav_items" not in rail:
    problems.append("_rail.html لا يقرأ nav_items — الروابط مكتوبة بخطّ اليد؟")
# ولا نسخة ثانية للتنقّل
if 'class="ds-nav"' in base:
    problems.append("base.html ما زال فيه قائمة تنقّل ثانية — نسختان تتباعدان")

# ── ٦) مفاتيح الشريط تغطّي صفحات النظام ──
sys.path.insert(0, str(ROOT / "web"))
cp = (ROOT / "web" / "dashboard" / "context_processors.py").read_text(
    encoding="utf-8")
keys = set(re.findall(r'^\s+\("([a-z]+)"', cp, re.M))
views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
used = set(re.findall(r'"nav_page"\s*:\s*"([a-z_]+)"', views))
# ‏settings في ذيل الشريط، وsearch صفحة بلا مدخل — كلاهما مقصود
extra = used - keys - {"settings", "search"}
if extra:
    problems.append(f"صفحات بلا مدخل في الشريط: {' · '.join(sorted(extra))}")
notes.append(f"رموز معرَّفة: {len(defined)} · صفحات في الشريط: {len(keys)}")

for n in notes:
    print("  " + n)
if problems:
    for p in problems:
        print("  ✗ " + p)
    print(f"\n✗ {len(problems)} مشكلة في نظام التصميم")
    sys.exit(1)
print("\n✓ نظام التصميم متّسق")
