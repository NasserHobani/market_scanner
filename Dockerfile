# ═══════════════════════════════════════════════════════════════
#  ماسح الأسواق — صورة الإنتاج
# ═══════════════════════════════════════════════════════════════
#
# البناء:   docker build -t market-scanner .
# التشغيل:  انظر docker-compose.yml و docs/DOCKER.md
#
# ═══ الصورة الواحدة تخدم دورين ═══
#
# الويب (gunicorn) والمجدول (run_jobs) يشتركان في الكود نفسه
# ويختلفان في الأمر وحده. وصورتان تعنيان نسختين تتباعدان.

# ── مرحلة البناء ──
#
# ‏pip يجرّ أدوات ترجمة وذاكرة تحميل لا لزوم لها في التشغيل. وعزلها
# هنا يُنقص الصورة النهائية نحو ٤٠٠ ميغابايت.
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements-web.txt requirements-ai.txt pyproject.toml ./

# ═══ لماذا تُذكر الحزم صراحةً ═══
#
# ‏requirements-web.txt يذكر Django وحده، ويترك psycopg تعليقاً
# «لمن أراد PostgreSQL». وهذا صالحٌ على الجهاز، أمّا الصورة فقاعدتها
# PostgreSQL دائماً — فلا يُترك المحرّك اختياراً.
#
# و‏gunicorn و whitenoise ليسا من متطلّبات المشروع بل من متطلّبات
# **نشره**: خادم WSGI حقيقي بدل ``runserver``، وخدمةُ الملفّات
# الساكنة التي يتوقّف Django عن تقديمها حين ينطفئ DEBUG.
RUN pip install --no-cache-dir \
        -r requirements-web.txt \
        -r requirements-ai.txt \
        "pandas>=2.0" "numpy>=1.24" "pyyaml>=6.0" "pyarrow>=14.0" \
        "psycopg[binary]>=3.1" \
        "gunicorn>=21.2" \
        "whitenoise>=6.6" \
        "requests>=2.31"


# ── مرحلة التشغيل ──
FROM python:3.11-slim AS runtime

# ‏libgomp1: يحتاجه LightGBM وقت التشغيل. وبلا تثبيته يفشل
#   ``import lightgbm`` فيرتدّ التدريب إلى sklearn صامتاً — وهو
#   العطب نفسه الذي ظهر على جهازك بـ «LightGBM UNAVAILABLE».
# ‏tzdata: بلا حزمة المناطق يسقط ``ZoneInfo("Asia/Riyadh")`` إلى
#   UTC، فتُعرض كل الأوقات بفارق ثلاث ساعات.
# ‏curl: لفحص الصحّة أدناه.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 tzdata curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # ‏Django يُستورَد من ‎/app/web‎ وحزمة scanner من ‎/app‎
    PYTHONPATH=/app:/app/web \
    DJANGO_SETTINGS_MODULE=config.settings \
    # ═══ الترميز ═══
    # سجلّات هذا النظام عربية. وأنبوب لوج بترميزٍ غير UTF-8 ينهار
    # بـ UnicodeEncodeError عند أوّل حرف — لا يسقط الطلب بل يُفقد
    # السطر، فيبدو كأنّ شيئاً لم يحدث.
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    TZ=Asia/Riyadh

COPY --from=builder /opt/venv /opt/venv

# ═══ مستخدم غير الجذر ═══
#
# ثغرةٌ في التطبيق تصير جذراً داخل الحاوية إن عمل بالجذر — وهو
# أوّل درجة في سلّم الخروج منها.
RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY --chown=app:app . /app

# مجلّدات يكتب فيها التطبيق. وتُنشأ الآن بمالكها الصحيح: وحدة
# التخزين التي تُركَّب على ‎/app/data‎ ترث ملكيّة نقطة التركيب،
# فإن كانت للجذر عجز التطبيق عن الكتابة و«لا يعمل بلا سبب».
RUN mkdir -p /app/data /app/reports /app/web/staticfiles \
    && chown -R app:app /app/data /app/reports /app/web/staticfiles \
    && chmod +x /app/docker-entrypoint.sh

USER app

EXPOSE 8000

# ═══ فحص الصحّة ═══
#
# «الحاوية تعمل» لا يعني «التطبيق يستجيب»: عمليةٌ علقت على قفل
# قاعدة تبقى حيّة بلا أن تردّ. وهذا يسأل الصفحة فعلاً.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz/ || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# ═══ عدد العمّال وحدّ المهلة ═══
#
# ‏--timeout 120: المسح والتدريب أطول من الافتراضي (٣٠ث)، وقتلُ
#   العامل في منتصفهما يترك صفقةً نصف مكتوبة.
# ‏--workers 3: عمليات لا خيوط — فـ pandas يحرّر GIL جزئياً فقط.
#   والجدولة **لا** تعمل هنا (SCHEDULER_ENGINE=off في compose):
#   ثلاثة عمّال يعني ثلاثة مجدولين على قاعدةٍ واحدة، فتُشغَّل كل
#   مهمّة ثلاث مرّات. المجدول حاوية مستقلّة واحدة.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
