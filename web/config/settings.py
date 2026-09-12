"""إعدادات Django.

قاعدة معمارية محفوظة: طبقة الويب رقيقة. محرك المسح يبقى حزمة `scanner`
المستقلة التي لا تعرف شيئاً عن Django — الويب يستوردها ويعرض نتائجها فقط.
هذا ما يبقي الماسح قابلاً للتشغيل من سطر الأوامر وبالجدولة بلا خادم.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


# ═══ قراءة ‎.env‎ ═══
#
# كانت هنا نسخةٌ خاصّة بـ Django، فكان الملف يُحمَّل عند إقلاع
# الخادم وحده. وأدوات سطر الأوامر لا تُقلع Django، فكان
# ``SAHMK_API_KEY`` يصل من اللوحة ولا يصل من الأداة — وتقول الأداة
# «المفتاح غير مضبوط» والمفتاح في مكانه.
#
# النسخة الوحيدة الآن في ``scanner/env.py`` وتُنادى عند استيراد
# الحزمة. وهذا يستوردها صراحةً كي لا يعتمد على ترتيب استيراد آخر.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scanner.env import load_env as _load_env  # noqa: E402

ENV_FILE = PROJECT_ROOT / ".env"
ENV_LOADED = _load_env(ENV_FILE)

def _secret_key() -> str:
    """مفتاح ثابت للجهاز، يُولَّد مرة ويُحفظ في .env.

    المفتاح الافتراضي المكتوب في الكود يعني أن أي جلسة أو رمز CSRF
    قابل للتزوير من يعرف المصدر — وهو مقبول على localhost وحده. وبما
    أن الواجهة تُفتح الآن على الشبكة، يُولَّد مفتاح حقيقي تلقائياً بدل
    الاعتماد على أن يتذكّر أحد ضبطه.
    """
    key = os.getenv("DJANGO_SECRET_KEY", "").strip()
    if key and key != "dev-only-change-me":
        return key

    import secrets

    key = secrets.token_urlsafe(50)
    env = PROJECT_ROOT / ".env"
    try:
        with env.open("a", encoding="utf-8") as fh:
            fh.write(f"\nDJANGO_SECRET_KEY={key}\n")
        print(f"⚙ وُلِّد مفتاح سرّي جديد وحُفظ في {env.name}")
    except OSError:
        print("⚠ تعذّر حفظ المفتاح السرّي — سيتغيّر مع كل تشغيل "
              "فتنتهي الجلسات")
    os.environ["DJANGO_SECRET_KEY"] = key
    return key


def _local_ips() -> list[str]:
    """عناوين هذا الجهاز على الشبكة.

    تُضاف إلى ALLOWED_HOSTS لأن Django يرفض الطلب إن لم يطابق ترويسة
    Host — والفتح على 0.0.0.0 بلا ذلك يعطي «Bad Request (400)» غامضاً
    لكل من يزور من الشبكة.
    """
    import socket

    out = {"localhost", "127.0.0.1", "[::1]"}
    try:
        out.add(socket.gethostname())
        for info in socket.getaddrinfo(socket.gethostname(), None):
            addr = info[4][0]
            if addr and ":" not in addr:
                out.add(addr)
    except OSError:
        pass
    try:
        # لا يرسل شيئاً فعلياً — حيلة لمعرفة الواجهة الخارجة
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("10.255.255.255", 1))
        out.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(x for x in out if x)


SECRET_KEY = _secret_key()

# الفتح على الشبكة يعني أن الواجهة لم تعد على جهازك وحدك: تركُ DEBUG
# مشتغلاً يعرض أثر الاستثناء كاملاً — بما فيه مسارات وإعدادات — لكل
# من يفتح صفحة خاطئة. لذلك ينطفئ افتراضياً إلا أن تطلبه صراحة.
LAN_MODE = os.getenv("SCANNER_LAN", "0") == "1"
DEBUG = os.getenv("DJANGO_DEBUG", "0" if LAN_MODE else "1") == "1"

_hosts = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")
          if h.strip()]

if LAN_MODE:
    # دمج لا استبدال: ملف .env يحمل DJANGO_ALLOWED_HOSTS=localhost من
    # التنصيب، و_load_env يضعه في البيئة قبل هذا السطر. لو عاملناه
    # حصرياً لبقي عنوان الشبكة مرفوضاً بـ «Bad Request (400)» رغم
    # طلب وضع الشبكة صراحةً — وهذا ما حدث فعلاً.
    ALLOWED_HOSTS = sorted(set(_hosts) | set(_local_ips()))
    if not any(h for h in ALLOWED_HOSTS if h not in
               ("localhost", "127.0.0.1", "[::1]")):
        # تعذّر التعرّف على أي عنوان شبكة (جدار حماية يمنع الاستكشاف
        # مثلاً). الرفض هنا يعني أداة لا تعمل، فنفتحها مع تنبيه صريح.
        ALLOWED_HOSTS = ["*"]
        print("⚠ تعذّر التعرّف على عنوان الشبكة — قُبل أي مضيف. "
              "حدّد DJANGO_ALLOWED_HOSTS في .env لتضييقه.")
elif _hosts:
    ALLOWED_HOSTS = _hosts
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Django يرفض POST من أصل لا يطابق المضيف. بدون هذا يعمل العرض من
# الشبكة بينما تفشل كل الأزرار برسالة 403 مربكة.
CSRF_TRUSTED_ORIGINS = [
    f"{scheme}://{host}{port}"
    for host in ALLOWED_HOSTS if host and "*" not in host
    for scheme in ("http", "https")
    for port in ("", ":8000", ":8080")
]

# ═══════════ خلف وكيلٍ عكسيّ (Nginx Proxy Manager وغيره) ═══════════
#
# ═══ ما يكسر بلا هذا ═══
#
# الوكيل يُنهي TLS ثمّ يمرّر الطلب إلى الحاوية بـ HTTP عاديّ. فلا
# يعرف Django أنّ الأصل كان HTTPS — ما لم تُقرأ ترويسة
# ``X-Forwarded-Proto``.
#
# والأثر يظهر في الاستمارات: طلبُ POST من صفحةٍ عنوانها ‎https://‎
# يحمل ‎Origin: https://…‎، و‏Django يقارنه بما يظنّه أصلَه —
# فيراه ‎http://‎ ويردّ **403**. أي أنّ الصفحة تُفتح وتُقرأ وكل
# زرٍّ فيها يفشل، بلا رسالةٍ تقول لماذا.
#
# ═══ ولماذا هو مشروط ═══
#
# الوثوق بهذه الترويسات بلا وكيلٍ أمامك ثغرة: يستطيع أيّ زائر
# إرسال ``X-Forwarded-Proto: https`` فيوهم Django بأنّ اتّصاله
# مؤمَّن. فلا تُقرأ إلّا إن أُعلن الوكيل صراحةً.
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
if TRUST_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # والمضيف من ``X-Forwarded-Host`` لا من ``Host`` الداخلي:
    # ‏NPM يمرّر النطاق العامّ في الأولى.
    USE_X_FORWARDED_HOST = True
    USE_X_FORWARDED_PORT = True

# ═══ ونطاقٌ صريح للاستمارات ═══
#
# ‏``CSRF_TRUSTED_ORIGINS`` أعلاه مشتقٌّ من ``ALLOWED_HOSTS``
# بمنافذ ثابتة. وخلف وكيلٍ على منفذٍ غير معتاد لا يكفي، فيُقبل
# عنوانٌ صريح — بمخطَّطه، كما يشترط Django 4+:
#
#   DJANGO_CSRF_TRUSTED_ORIGINS=https://scanner.example.com
_extra_csrf = [o.strip() for o in
               os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
               if o.strip()]
if _extra_csrf:
    bad = [o for o in _extra_csrf if "://" not in o]
    if bad:
        # ‏Django يرمي عند أوّل طلب لا عند الإقلاع، فالخطأ يظهر
        # بعيداً عن سببه. والتنبيه هنا عنده.
        print(f"⚠ DJANGO_CSRF_TRUSTED_ORIGINS يحتاج المخطَّط "
              f"(https://…): {bad}")
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(
        CSRF_TRUSTED_ORIGINS + _extra_csrf))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # رصد التزامن: يقيس مدّة كل طلب وكم كان يعمل معه.
    # كلفته مهملة (قفل وقاموس)، وبدونه تبقى شكوى «النظام يعلّق» بلا
    # رقم — والتخمين بين المسح والنموذج والقفل يُنتج تعديلات لا تُقاس.
    "dashboard.concurrency.InFlightMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # عناصر الشريط الجانبي — مصدرٌ واحد لكل صفحة
                "dashboard.context_processors.nav",
            ],
        },
    },
]

# PostgreSQL عبر متغيرات البيئة، مع SQLite افتراضاً.
#
# ═══ لماذا كان SQLite يعطي «database is locked» ═══
#
# النظام فيه ثلاثة كتّاب متزامنين: خيوط الخادم، وحلقة الحسم، وحلقة
# المراقبة. و SQLite في وضعه الافتراضي (journal_mode=delete) يقفل
# الملف **كاملاً** عند كل كتابة، ويمنع القراءة أثناءها. فأي تقاطع
# يُسقط الكاتب فوراً.
#
# والأسوأ أن سقوطه كان يُجهض **دورة كاملة**: حلقة الحسم تموت عند
# الصفقة التي صادفت القفل، فما بعدها لا يُحسم في تلك الدورة. أي أن
# القياس نفسه — وهو غرض المشروع — كان يفقد صفقات لسبب لا علاقة له
# بالسوق.
#
# الإعدادات الثلاثة أدناه تعالج ذلك من أصله:
#
#   journal_mode=WAL   القرّاء لا يحجبون الكاتب ولا يحجبهم. هذا وحده
#                      يزيل أغلب التصادم، لأن أغلب حركتنا قراءة.
#   timeout=30         الكاتب ينتظر ثلاثين ثانية بدل أن يسقط فوراً.
#   transaction_mode   ‏IMMEDIATE يأخذ قفل الكتابة عند BEGIN لا في
#     = IMMEDIATE      منتصف المعاملة. وهذا هو الفرق الحاسم: المعاملة
#                      المؤجَّلة التي تبدأ بقراءة ثم تكتب تسقط بـ
#                      SQLITE_BUSY **دون أن تحترم المهلة** — وهو سبب
#                      «locked رغم أنني رفعت timeout» الذي يحيّر كثيرين.
#
#   synchronous=NORMAL آمن مع WAL (لا يفقد بيانات إلا بانقطاع كهرباء
#                      مفاجئ)، ويقلّل مزامنة القرص كثيراً.
#
# تبقى PostgreSQL الأفضل لتعدّد الكتّاب الحقيقي، لكن هذا الحمل —
# كاتب واحد نشط في أغلب الوقت — يستوعبه SQLite بهذه الإعدادات.
if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }

    # ═══ اتّصالٌ ثانٍ بالقاعدة القديمة — للترحيل وحده ═══
    #
    # يُضاف فقط إن كان ملفّ SQLite موجوداً، وفقط حين تكون
    # PostgreSQL هي الأساسية. فأمر ``migrate_to_postgres`` يقرأ من
    # ``legacy`` ويكتب في ``default`` في عمليةٍ واحدة — بلا ملفّ
    # وسيط ولا تصدير نصّي.
    #
    # ولا يُحذف بعد الترحيل: يبقى للمقارنة والتحقّق متى شئت.
    _legacy = PROJECT_ROOT / "data" / "dashboard.sqlite3"
    if _legacy.exists():
        DATABASES["legacy"] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _legacy,
            "OPTIONS": {"timeout": 30},
            # ‏Django يمنع الاختبارات من لمس قاعدةٍ بلا TEST NAME
            "TEST": {"MIRROR": None},
        }
else:
    _sqlite_dir = PROJECT_ROOT / "data"
    _sqlite_dir.mkdir(parents=True, exist_ok=True)   # وإلا فشل الاتصال بملف في مجلد غير موجود
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _sqlite_dir / "dashboard.sqlite3",
            # ‏timeout وحدها مفهومة لكل النسخ — تُمرَّر إلى sqlite3.connect
            "OPTIONS": {"timeout": 30},
        }
    }

    # ‏init_command و transaction_mode أُضيفتا في Django 5.1. وتمريرهما
    # إلى 5.0 يذهب مباشرةً إلى ``sqlite3.connect`` فيرفع TypeError عند
    # أول اتصال — أي تعطُّل كامل لا تدهور لطيف. فنفحص النسخة.
    import django as _django

    if _django.VERSION >= (5, 1):
        DATABASES["default"]["OPTIONS"].update({
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA foreign_keys=ON;"
            ),
            "transaction_mode": "IMMEDIATE",
        })
    else:
        # على 5.0: نضبط الـ PRAGMA عند إنشاء كل اتصال. يعطي WAL والمهلة،
        # ويبقى IMMEDIATE متعذّراً — فالترقية إلى 5.1 موصى بها.
        from django.db.backends.signals import connection_created
        from django.dispatch import receiver

        @receiver(connection_created)
        def _sqlite_pragmas(sender, connection, **kwargs):  # noqa: ANN001
            if connection.vendor != "sqlite":
                return
            with connection.cursor() as cur:
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA synchronous=NORMAL;")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "ar"

# التخزين بـ UTC دائماً (USE_TZ) والعرض بالتوقيت المحلي.
#
# كان هذا "UTC" فتُعرض كل الأوقات بتوقيت غرينتش: صفقة دخلت الساعة
# الثامنة مساءً بتوقيتك تظهر «17:00». والفرق ليس تجميلياً — تقارن
# التوقيت بشارتك فلا يتطابق، فتظنّ البيانات خاطئة.
#
# UTC يبقى المرجع في القاعدة وفي الشموع؛ التحويل عند العرض فقط.
TIME_ZONE = os.getenv("SCANNER_TIMEZONE", "Asia/Riyadh")
try:                                    # منطقة مكتوبة خطأً لا تُسقط الخادم
    from zoneinfo import ZoneInfo

    ZoneInfo(TIME_ZONE)
except Exception:                       # noqa: BLE001
    print(f"⚠ منطقة زمنية غير معروفة: {TIME_ZONE} — يُستعمل UTC")
    TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ═══ تقديم الملفّات الساكنة حين ينطفئ DEBUG ═══
#
# ‏Django يقدّمها بنفسه في وضع التطوير وحده. وتحت gunicorn بـ
# ‎DEBUG=0‎ تصير كل ملفّات ‎.css‎ و‎.js‎ ‏404 — فتُفتح اللوحة بلا
# نمطٍ ولا رسوم وتبدو معطوبة، والسجلّ لا يذكر خطأً.
#
# و‏whitenoise يقدّمها من العملية نفسها بلا nginx. وهي حزمة نشرٍ
# لا حزمة مشروع: من يشغّل على جهازه بـ ``runserver`` لا يحتاجها،
# فالإدراج مشروط بوجودها لا مفروض.
try:
    import whitenoise  # noqa: F401
except ImportError:
    if not DEBUG:
        print("⚠ whitenoise غير مثبّت و DEBUG مطفأ — الملفّات "
              "الساكنة لن تُقدَّم. ثبّتها أو ضع وكيلاً عكسياً أمامها.")
else:
    # بعد SecurityMiddleware مباشرةً وقبل كل ما سواه: الملفّ
    # الساكن يُردّ بلا المرور على الجلسة والاستيثاق ورصد التزامن.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            # يضغط ويبصم كل ملفّ باسمه. والبصمة تجعل المتصفّح
            # يخزّنه سنةً بأمان: تغييرُ الملفّ يغيّر اسمه، فلا
            # تبقى نسخةٌ قديمة عالقة بعد كل نشر.
            "BACKEND": "whitenoise.storage."
                       "CompressedManifestStaticFilesStorage"},
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# مجلد إعدادات الأسواق (config/*.yaml) — يقرأه أمر المسح
SCANNER_CONFIG_DIR = PROJECT_ROOT / "config"
COMPLIANCE_RULES = PROJECT_ROOT / "config" / "compliance.yaml"
