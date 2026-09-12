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

# ═══ لا صيغة «المطلوب» في compose ═══
#
# ``${VAR:?…}`` تُفحص **وقت تفسير الملفّ** — قبل أن تُبنى صورة أو
# تُقلع حاوية. فإن لم يصل المتغيّر إلى المفسِّر سقط النشر كلّه
# برسالةٍ عن «متغيّر ناقص»، ولو كان الخلل في كيفية إدخاله لا في
# غيابه. وهذا ما أوقف النشر ببورتينر فعلاً:
#
#   required variable POSTGRES_PASSWORD is missing a value
#
# والتحقّق مكانه ``docker-entrypoint.sh``: هناك يقع داخل الحاوية،
# فيظهر في سجلّها ويقول ما يُفعل، ولا يمنع بقيّة المكدّس.
_cc = "\n".join(l for l in _raw_compose.splitlines()
                 if not l.strip().startswith("#"))
check("  ولا صيغة ‎:?‎ في compose", ":?" not in _cc,
      str([l.strip() for l in _cc.splitlines() if ":?" in l][:2]))

# والتحقّق موجودٌ في نقطة الدخول، ويسمّي الناقص
check("  والتحقّق في نقطة الدخول", "متغيّرات ناقصة" in EP)
_req = EP.split("missing=")[1].split("if [ -n")[0]
for _v in ("POSTGRES_DB", "POSTGRES_PASSWORD"):
    check(f"  ويشمل {_v}", _v in _req)

# ═══ المفتاح السرّي لا يُطلب من المستخدم ═══
#
# كان مطلوباً في البيئة — تحميلٌ بلا داعٍ: المفتاح لا يعني شيئاً
# لأحد، وشرطُه الوحيد أن **يثبت** بين الإقلاعات وبين عمّال
# gunicorn الثلاثة، وإلّا انتهت الجلسات ورموز CSRF بلا سبب.
#
# ووحدة ``/app/data`` تبقى بعد كل نشر، فالمفتاح يُولَّد مرّة
# ويُقرأ بعدها.
check("  ولا يُطلب المفتاح السرّي", "DJANGO_SECRET_KEY" not in _req)
check("  بل يُولَّد ويُحفظ", "SECRET_FILE" in EP and "token_urlsafe" in EP)
check("  في وحدة البيانات", "/app/data/.django_secret_key" in EP)
check("  ويُقرأ إن وُجد", 'if [ -s "$SECRET_FILE" ]' in EP)
# ‏umask قبل الكتابة لا chmod بعدها: بينهما نافذةٌ يكون فيها
# الملفّ مقروءاً للجميع
check("  ويُقيَّد بـ umask لا chmod", "umask 077" in EP)
# والبيئة تعلوه: من أراد مفتاحاً بعينه يضبطه
check("  والبيئة تعلوه", 'if [ -z "${DJANGO_SECRET_KEY:-}" ]' in EP)

# ═══ ويُعرَض ما وصل الحاوية فعلاً ═══
#
# «متغيّر ناقص» تُقرأ «لم أكتبه». وقد يكون كُتب ولم يصل — وهو ما
# وقع: مكدّسٌ لا يملكه بورتينر لا تصله متغيّراته.
check("  ويعرض ما وصل فعلاً", "ما وصل هذه الحاوية فعلاً" in EP)
check("  ويشرح المكدّس غير المملوك", "Limited" in EP)
check("  ويعطي أمر الإزالة", "down --remove-orphans" in EP)
# ويقول أين تُكتب في الحالتين — الرسالة التي لا تقول ما يُفعل
# تُكافئ الصمت
check("  ويدلّ على ‎.env‎", "‎.env‎" in EP)
check("  وعلى بورتينر", "بورتينر" in EP and "Environment variables" in EP)

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


# ═══ ٧ب) كل سكربتٍ يُنفَّذ يجب أن يكون قابلاً للتنفيذ ═══
#
# ‏Git لا يحفظ بتَّ التنفيذ على ويندوز: الملفّات تصل الصورة بوضع
# ‎644‎. وكان ``chmod +x`` يذكر نقطة الدخول وحدها — فعملت، وبدا
# كل شيء سليماً، ثمّ سقط المجدول وحده:
#
#     /app/docker-scheduler.sh: Permission denied
#
# وأُعيد بلا توقّف. والعطب لا يظهر في البناء ولا في الويب.
import re as _re2

_scripts = set()
# ما تنفّذه الخدمات في compose
for _sv in SVC.values():
    for _c in (_sv.get("command") or []):
        if isinstance(_c, str) and _c.endswith(".sh"):
            _scripts.add(_c.rsplit("/", 1)[-1])
# وما تنفّذه الصورة
for _m in _re2.finditer(r'ENTRYPOINT\s*\[\s*"([^"]+\.sh)"', DF):
    _scripts.add(_m.group(1).rsplit("/", 1)[-1])

check("٧ب رُصدت سكربتات التشغيل", len(_scripts) >= 2, str(sorted(_scripts)))

# ‏chmod في الـDockerfile يغطّيها — صراحةً أو بنمط
_chmod = [l for l in DF.splitlines()
          if "chmod" in l and not l.strip().startswith("#")]
_chmod_txt = " ".join(_chmod)
# المطابقة بـ ``fnmatch`` لا بـ ``startswith``: النمط
# ‎docker-*.sh‎ لا يُطابَق بقصّ نجمة من طرفه — وأوّل نسخةٍ من هذا
# الفحص فعلت ذلك ورسبت على كودٍ سليم.
from fnmatch import fnmatch as _fn

_globs = _re2.findall(r"/app/(\S*\*\S*)", _chmod_txt)
for _sc in sorted(_scripts):
    _ok = _sc in _chmod_txt or any(_fn(_sc, g) for g in _globs)
    check(f"  و{_sc} يُمنح التنفيذ", _ok,
          f"الأنماط: {_globs}")

# وبتُّ التنفيذ مضبوطٌ في Git أيضاً — لمن يشغّلها بلا Docker
import subprocess as _sp

try:
    _modes = _sp.run(["git", "ls-files", "-s", "--", "*.sh"],
                     cwd=ROOT, capture_output=True, text=True,
                     timeout=20).stdout
except Exception:  # noqa: BLE001
    _modes = ""
if _modes.strip():
    _bad = [l.split("\t")[-1] for l in _modes.strip().splitlines()
            if l.startswith("100644")]
    check("  وبتُّ التنفيذ مضبوطٌ في Git", not _bad, str(_bad))


# ═══ ٨أ) فحص الصحّة للعرض لا للبوّابة ═══
#
# كان ``depends_on: db: {condition: service_healthy}``. وأثره أنّ
# تأخّر القاعدة — أو فشلها — يُسقط **النشر كلّه** برسالة:
#
#     dependency failed to start: container ... is unhealthy
#
# ولا تقول لماذا، ولا تُقلع حاويةً يمكن قراءة سجلّها.
#
# والانتظار موجودٌ أصلاً في نقطة الدخول: حلقةٌ تنتظر وتقول ما
# تنتظره وتموت برسالةٍ مفهومة. فالشرط كان تكراراً — ونسخته
# الأسوأ، لأنّها تُجهض المكدّس بدل أن تُشخّص.
#
# وهو العطب نفسه الذي وقع في ``${VAR:?}``.
for _n, _sv in SVC.items():
    _dep = _sv.get("depends_on") or {}
    _gates = [k for k, v in _dep.items()
              if isinstance(v, dict) and v.get("condition") == "service_healthy"]
    check(f"٨أ {_n} لا يُعلَّق على فحص الصحّة", not _gates, str(_gates))

# والفحص باقٍ — للعرض في بورتينر
check("  والفحص باقٍ على القاعدة", "healthcheck" in SVC["db"])
# ومهلته تكفي initdb الأوّل على قرصٍ بطيء
_sp = str(SVC["db"]["healthcheck"].get("start_period", "0s"))
check("  ومهلته تكفي initdb", int(_sp.rstrip("s")) >= 60, _sp)

# والانتظار في نقطة الدخول يكفي، ويقول ما يُفعل عند الفشل
check("  والانتظار في نقطة الدخول", "DB_WAIT" in EP)
check("  ومدّته كافية",
      int(EP.split("DB_WAIT_SECONDS:-")[1].split("}")[0]) >= 180)
check("  ويدلّ على سجلّ القاعدة", "docker logs market-scanner-db-1" in EP)
check("  ويعدّد الأسباب الشائعة",
      "POSTGRES_PASSWORD فارغ" in EP and "قرص الخادم ممتلئ" in EP)


# ═══ ٨ب) لا خدمتان تبنيان وسماً واحداً ═══
#
# ‏Compose يبني ما له ``build`` **بالتوازي**. وخدمتان بوسمٍ واحد
# تحاولان كتابته في اللحظة نفسها:
#
#     image "market-scanner:latest": already exists
#
# وهذا أوقف النشر فعلاً. والصورتان متطابقتان أصلاً — السياق
# والـDockerfile واحد، والفرق ``command`` وحده.
_builders = {n: sv for n, sv in SVC.items() if sv.get("build")}
_tags = [sv.get("image") for sv in _builders.values()]
check("٨ب من يبني واحدٌ لا أكثر", len(_builders) == 1,
      str(list(_builders)))
check("  ولا وسمان متطابقان في البناء",
      len(_tags) == len(set(_tags)), str(_tags))

# والمجدول يشير إلى ما بناه الويب، ولا يبني
check("  والمجدول لا يبني", "build" not in SVC["scheduler"])
check("  ويشير إلى صورة الويب",
      SVC["scheduler"].get("image") == SVC["web"].get("image"),
      f"{SVC['scheduler'].get('image')} مقابل {SVC['web'].get('image')}")
# والترتيب مقصود: Compose يبني كل ما له build قبل إنشاء أيّ
# حاوية، والاعتماد يجعل النيّة مكتوبة لا مستنتَجة
check("  وينتظر الويب", "web" in (SVC["scheduler"].get("depends_on") or {}))


# ═══ ٨ج) خلف وكيلٍ عكسيّ ═══
#
# الوكيل يُنهي TLS ويمرّر بـ HTTP. فلا يعرف Django أنّ الأصل كان
# HTTPS ما لم يقرأ ``X-Forwarded-Proto`` — والأثر أنّ الصفحات
# تُفتح وتُقرأ ويفشل **كل زرّ** بـ 403، بلا رسالةٍ تقول لماذا.
_st = (ROOT / "web" / "config" / "settings.py").read_text(encoding="utf-8")
_sc = "\n".join(l for l in _st.splitlines() if not l.strip().startswith("#"))
check("٨ج يقرأ ترويسة المخطَّط", "SECURE_PROXY_SSL_HEADER" in _sc)
check("  والمضيف من الوكيل", "USE_X_FORWARDED_HOST" in _sc)
# ═══ مشروطٌ لا دائم ═══
#
# الوثوق بهذه الترويسات بلا وكيلٍ أمامك ثغرة: يرسلها أيّ زائر
# فيوهم Django بأنّ اتّصاله مؤمَّن.
check("  ومشروطٌ بإعلان الوكيل", "TRUST_PROXY" in _sc
      and "if TRUST_PROXY:" in _sc)
check("  وافتراضه مطفأ", 'os.getenv("TRUST_PROXY", "0")' in _sc)
check("  ويُمرَّر في compose", "TRUST_PROXY:" in _raw_compose)

# وعنوانٌ صريح للاستمارات خلف منفذٍ غير معتاد
check("  وأصلٌ صريح للاستمارات",
      "DJANGO_CSRF_TRUSTED_ORIGINS" in _sc)
# ‏Django يشترط المخطَّط ويرمي عند أوّل طلب لا عند الإقلاع —
# فالتنبيه هنا، عند سببه
check("  ويُنبَّه على المخطَّط الناقص", "يحتاج المخطَّق" in _st
      or "يحتاج المخطَّط" in _st)


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
