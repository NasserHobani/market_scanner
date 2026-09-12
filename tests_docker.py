# -*- coding: utf-8 -*-
"""النشر بـ Docker — ما ينكسر بصمت على خادمٍ لا تراه.

═══ ثلاثة أعطال تُنتج نتيجةً معقولة المظهر ═══

**مجدولٌ في كل عامل.** ``cron.start()`` يعمل في ``ready()`` — أي في
كل عامل gunicorn. وثلاثة عمّال يعني كل مسحٍ ثلاث مرّات وكل صفقةٍ
ورقية ثلاثاً. ولا خطأ يظهر: أرقامٌ تُكتب، وسجلٌّ يمتلئ، وتبدو
الصفقات كأنّها فرصٌ متكرّرة.

**منفذٌ مفتوح بلا استيثاق.** لا ``login_required`` في هذا المشروع
كلّه. فحذف ``127.0.0.1`` من ربط المنفذ يفتح الصفقات والإعدادات
والمفاتيح للإنترنت — وكل شيء يعمل تماماً، وهذا هو الخطر.

**‏.env داخل الصورة.** مفاتيح Alpaca تفتح الحساب وتسمح بإرسال
الأوامر. وملفٌّ يدخل الصورة يُقرأ بـ ``docker history`` — ولو لم
يُرفع إلى GitHub قطّ.

ولا يشغّل هذا الملفّ Docker: يقرأ الوصف ويقيس نيّته.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


DF = (ROOT / "Dockerfile").read_text(encoding="utf-8")
DI = (ROOT / ".dockerignore").read_text(encoding="utf-8")
EP = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
SC = (ROOT / "docker-scheduler.sh").read_text(encoding="utf-8")
_raw_compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
CJ = yaml.safe_load(_raw_compose)
SVC = CJ["services"]

# سطور الأمر بلا تعليقات — التعليق يشرح ولا يُنفَّذ
df_code = "\n".join(l for l in DF.splitlines() if not l.strip().startswith("#"))
ep_code = "\n".join(l for l in EP.splitlines() if not l.strip().startswith("#"))


# ═══ ١) مجدولٌ واحد ═══
check("١ الويب بلا جدولة",
      str(SVC["web"]["environment"].get("SCHEDULER_ENGINE")).lower() == "off")
check("  والمسح التلقائي مطفأ فيه",
      str(SVC["web"]["environment"].get("AUTO_SCAN")) == "0")
check("  وخدمة مجدول مستقلّة", "scheduler" in SVC)
check("  بنسخة واحدة", int(SVC["scheduler"].get("scale", 1)) == 1)
check("  تنادي run_jobs", "run_jobs" in SC)
# والحلقة لا تموت بفشل دورة: انقطاع شبكةٍ يجب ألّا يوقف الجدولة
check("  ولا تسقط بفشل دورة", "set -uo pipefail" in SC and "set -e" not in SC)
check("  والانتظار يُقاس من بداية الدورة", "elapsed=" in SC)
check("  وتستجيب لـ SIGTERM", "trap" in SC and "TERM" in SC)


# ═══ ٢) المنفذ مغلق افتراضاً ═══
#
# لا استيثاق في النظام. والربط بـ 127.0.0.1 يجعل الفتح فعلاً
# مقصوداً لا نتيجةً لنسخ أمرٍ من دليل.
# ═══ الربط مغلقٌ افتراضاً ═══
#
# صار متغيّراً لأنّ الخادم البعيد لا يصله المستخدم على
# ‎127.0.0.1‎. والمهمّ أنّ **الافتراض** مغلق: فتحُه يحتاج كتابةً
# صريحة، فيكون القرار واعياً لا نتيجةَ نسخ أمرٍ من دليل.
ports = [str(x) for x in (SVC["web"].get("ports") or [])]
check("٢ الربط متغيّر لا ثابت",
      any("${WEB_BIND" in p for p in ports), str(ports))
check("  وافتراضه مغلق",
      any("${WEB_BIND:-127.0.0.1}" in p for p in ports), str(ports))
check("  ولا 0.0.0.0 مكتوباً",
      not any(p.startswith("0.0.0.0:") for p in ports), str(ports))
check("  والقاعدة بلا منفذ على المضيف", not SVC["db"].get("ports"))
check("  والسبب مكتوب في الملفّ",
      "لا تسجيل دخول" in (ROOT / "docker-compose.yml").read_text(
          encoding="utf-8"))
doc = (ROOT / "docs" / "DOCKER.md").read_text(encoding="utf-8")
check("  والوثيقة تبدأ بالتحذير", "لا تسجيل دخول" in doc[:900])
check("  وتعطي مخرجاً عملياً", "ssh -L" in doc)


# ═══ ٣) لا أسرار ولا بيانات ثقيلة في الصورة ═══
for pat in (".env", "data/", "reports/", ".git/", "*.sqlite3"):
    check(f"٣ ‏.dockerignore يمنع {pat}", pat in DI)
check("  والسبب مكتوب", "docker history" in DI)
check("  ولا COPY لـ .env", "COPY .env" not in DF)

# ═══ لا ‎env_file‎ يشير إلى ملفٍّ محجوب ═══
#
# كان ``env_file: [.env]`` — يعمل على الجهاز ويُسقط كل نشرٍ من
# مستودع Git: الملفّ محجوبٌ بـ ‎.gitignore‎ فلا يصل الخادم، وبورتينر
# يستنسخ المستودع ثمّ يشغّل compose فيفشل بـ ``env file not found``
# قبل أن يبني شيئاً.
#
# والبديل ``${VAR}``: بورتينر يملؤه من واجهته، و‏compose محلّياً
# يملؤه من ‎.env‎ تلقائياً — فملفٌّ واحد يخدم الاثنين.
for _name, _svc in SVC.items():
    check(f"  ولا env_file في {_name}", "env_file" not in _svc,
          str(_svc.get("env_file")))

# وكل متغيّرٍ يستهلكه compose مذكورٌ في القالب — والعكس.
# فمتغيّرٌ مطلوبٌ وغير موثَّق يُنسى، وموثَّقٌ وغير مستعمَل يُضلّل.
import re as _re

_code = "\n".join(l for l in _raw_compose.splitlines()
                   if not l.strip().startswith("#"))
_used = set(_re.findall(r"\$\{([A-Z_][A-Z0-9_]*)", _code))
_tpl = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
_tcode = "\n".join(l for l in _tpl.splitlines()
                    if not l.strip().startswith("#"))
_declared = set(_re.findall(r"^([A-Z_][A-Z0-9_]*)=", _tcode, _re.M))
check("  وكل متغيّر موثَّق", not (_used - _declared),
      str(sorted(_used - _declared)))
check("  ولا موثَّقٌ مهمَل", not (_declared - _used),
      str(sorted(_declared - _used)))

# والمطلوب يوقف النشر برسالةٍ بدل أن يُقلع ناقصاً
check("  والمفتاح السرّي مطلوب", "${DJANGO_SECRET_KEY:?" in _raw_compose)
check("  وكلمة مرور القاعدة مطلوبة",
      "${POSTGRES_PASSWORD:?" in _raw_compose)

# ولا سرٌّ مكتوبٌ في الملفّ نفسه
_lit = [l.strip() for l in _code.splitlines()
        if _re.search(r"(SECRET|TOKEN|PASSWORD|API_KEY):\s*[\"']?[A-Za-z0-9_\-]{8,}", l)
        and "${" not in l]
check("  ولا سرٌّ مكتوب فيه", not _lit, str(_lit[:2]))


# ═══ ٤) الصورة تحمل ما يحتاجه التشغيل ═══
#
# ‏libgomp1 غيابه يجعل ``import lightgbm`` يفشل، فيرتدّ التدريب
# إلى sklearn **صامتاً** ويقول العرض «نشط».
check("٤ libgomp1 مثبّت", "libgomp1" in df_code)
check("  و lightgbm مثبّت", "requirements-ai.txt" in df_code)
check("  و tzdata", "tzdata" in df_code)
check("  و psycopg", "psycopg" in df_code)
check("  و gunicorn", "gunicorn" in df_code)
# الملفّات الساكنة: Django يتوقّف عن تقديمها حين ينطفئ DEBUG
check("  و whitenoise", "whitenoise" in df_code)
check("  والترميز UTF-8", "PYTHONIOENCODING=utf-8" in df_code)
check("  ولا يعمل بالجذر", "USER app" in df_code)
check("  والمهلة أطول من الافتراضي", '"--timeout", "120"' in df_code)


# ═══ ٥) الإقلاع يرفض ما لا يعمل ═══
check("٥ يرفض بلا مفتاح سرّي",
      "DJANGO_SECRET_KEY" in ep_code and "die" in ep_code)
check("  والسبب موثَّق", "عند كل\n# إقلاع" in EP or "كل إقلاع" in EP)
check("  وينتظر القاعدة", "أنتظر قاعدة" in EP)
check("  ويهاجر من الويب وحده",
      str(SVC["web"]["environment"].get("RUN_MIGRATIONS")) == "1"
      and str(SVC["scheduler"]["environment"].get("RUN_MIGRATIONS")) == "0")
check("  والمجدول ينتظر الهجرات", "migrate --check" in ep_code)
check("  ويجمع الساكنة", "collectstatic" in ep_code)
check("  وpipefail مضبوط", "set -euo pipefail" in ep_code)


# ═══ ٦) فحص الصحّة يقيس ما يدّعيه ═══
check("٦ فحص صحّة معرَّف", "HEALTHCHECK" in DF and "/healthz/" in DF)
hz = (ROOT / "web" / "dashboard" / "health.py").read_text(encoding="utf-8")
check("  ويسأل القاعدة", "SELECT 1" in hz)
check("  ويردّ 503 عند عطبها", "status=503" in hz)
# نصّ خطأ القاعدة يذكر المضيف واسمها — يُسجَّل ولا يُرسَل
check("  ولا يكشف سبب العطب في الرد", 'HttpResponse("db' in hz)
urls = (ROOT / "web" / "config" / "urls.py").read_text(encoding="utf-8")
check("  والمسار مسجَّل", "healthz" in urls)
# قبل بقيّة المسارات: يُنادى كل ثلاثين ثانية
check("  قبل بقيّة المسارات",
      urls.index('path("healthz/') < urls.index('include("dashboard.urls")'))


# ═══ ٧) الساكنة تُقدَّم بعد إطفاء DEBUG ═══
st = (ROOT / "web" / "config" / "settings.py").read_text(encoding="utf-8")
s_code = "\n".join(l for l in st.splitlines() if not l.strip().startswith("#"))
check("٧ whitenoise في الوسائط", "WhiteNoiseMiddleware" in s_code)
# مشروط لا مفروض: من يشغّل بـ runserver لا يحتاجها
check("  بشرط تثبيتها", "except ImportError" in s_code
      and "import whitenoise" in s_code)
check("  وينبّه إن غابت مع DEBUG مطفأ", "if not DEBUG:" in s_code)
# بعد SecurityMiddleware مباشرةً — الملفّ الساكن لا يمرّ بالجلسة
check("  في الموضع الثاني", "MIDDLEWARE.insert(1," in s_code)


# ═══ ٨) القالب يُرفع والسرّ لا يُرفع ═══
gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
check("٨ ‏.env محجوب", "\n.env\n" in gi and "\n.env.*\n" in gi)
# ‏.env.docker.example يطابق ‎.env.*‎ فيُحجب بلا استثناء صريح —
# فيُنشر مستودعٌ بلا القالب الذي تشرحه الوثيقة
check("  والقالب مستثنى", "!.env.docker.example" in gi)
check("  والقالب موجود", (ROOT / ".env.docker.example").exists())
tpl = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
# قالبٌ بقيمة يُنسخ كما هو ويصير المفتاح معروفاً
check("  وبلا قيم", "DJANGO_SECRET_KEY=\n" in tpl
      and "POSTGRES_PASSWORD=\n" in tpl)
check("  ولا مفاتيح فيه",
      not any(k in tpl for k in ("PK", "sk-ant-", "bot"))
      or "ALPACA_API_KEY=\n" in tpl)


# ═══ ٩) دليل بورتينر يذكر ما ينكسر ═══
pdoc = (ROOT / "docs" / "PORTAINER.md").read_text(encoding="utf-8")
check("٩ الدليل موجود", len(pdoc) > 1500)
# التحذير أوّلاً: النظام بلا استيثاق، والخادم يكشفه
check("  ويبدأ بالتحذير", "لا تسجيل دخول" in pdoc[:600])
check("  ويعطي مخرجاً عملياً", "ssh -L" in pdoc)
check("  ويشرح Repository stack", "Repository" in pdoc
      and "Environment variables" in pdoc)
# ‏.env لا يُرفع — والتحقّق يُطلب صراحةً قبل الدفع
check("  ويأمر بالتحقّق قبل الدفع", "git ls-files" in pdoc)
check("  ويوصي بمستودعٍ خاصّ", "خاصّاً" in pdoc)
# صلاحية الرمز أقلّ ما يكفي
check("  وصلاحية الرمز محدودة", "repo" in pdoc and "Personal access token" in pdoc)
# الإشباع يُذكر: بلا ضبط الفترات يبقى السعودي بلا مسح
check("  ويأمر بضبط الفترات", "مُشبَع" in pdoc and "/jobs/" in pdoc)
check("  ويذكر التراجع", "Pull and redeploy" in pdoc)
check("  ولا يحذف القديم", "لا تحذف قاعدتك القديمة" in pdoc)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
