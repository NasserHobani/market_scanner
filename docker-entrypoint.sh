#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  ما يجري قبل أن يبدأ التطبيق
# ═══════════════════════════════════════════════════════════════
set -euo pipefail
# ‏pipefail لازم: ‏migrate | tee بلا هذا الخيار يعيد نجاح ``tee``
# ويبتلع فشل الهجرة، فتُقلع الحاوية على قاعدةٍ ناقصة.

cd /app

log() { printf '⚙ %s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

# ═══ ١) لا تُقلع بمفتاحٍ متولّد ═══
#
# ‏settings.py يولّد مفتاحاً سرّياً ويكتبه في ‎.env‎ إن لم يجده.
# وفي الحاوية لا ‎.env‎ يُحفظ — فيتولّد مفتاحٌ **جديد عند كل
# إقلاع**، وتنتهي كل الجلسات ورموز CSRF بلا سبب ظاهر. وثلاثة
# عمّال يعني ثلاثة مفاتيح مختلفة في اللحظة نفسها.
[ -n "${DJANGO_SECRET_KEY:-}" ] || die \
  "‏DJANGO_SECRET_KEY غير مضبوط. ولّده مرّة واحدة واحفظه في ‎.env‎:
   python -c \"import secrets;print(secrets.token_urlsafe(50))\""

[ -n "${POSTGRES_DB:-}" ] || die \
  "‏POSTGRES_DB غير مضبوط — الصورة مبنيّة على PostgreSQL."

# ═══ ٢) انتظار القاعدة ═══
#
# ‏depends_on في compose ينتظر **إقلاع الحاوية** لا جهوز الخادم.
# وPostgres يقبل الاتّصال بعد ثوانٍ من إقلاعه، فبلا هذا يسقط
# ``migrate`` عند أوّل تشغيل ثمّ ينجح عند الثاني — عطبٌ يختفي
# عند تتبّعه.
log "أنتظر قاعدة البيانات على ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432} …"
for i in $(seq 1 60); do
  if python - <<'PY' 2>/dev/null
import os, socket, sys
s = socket.create_connection(
    (os.getenv("POSTGRES_HOST", "db"), int(os.getenv("POSTGRES_PORT", "5432"))),
    timeout=2)
s.close()
PY
  then
    log "القاعدة جاهزة (بعد ${i} ثانية)"
    break
  fi
  [ "$i" -eq 60 ] && die "لم تستجب القاعدة خلال ٦٠ ثانية"
  sleep 1
done

# ═══ ٣) الهجرات — من الويب وحده ═══
#
# حاويتان تهاجران معاً على قاعدةٍ واحدة تتسابقان على جدول
# ``django_migrations``. فالمجدول ينتظر ولا يهاجر.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  log "أطبّق الهجرات …"
  python web/manage.py migrate --noinput
else
  # وينتظر أن تنتهي: بدءُ المهامّ على جداول ناقصة يملأ السجلّ
  # أخطاءً تبدو عطباً في المهامّ لا في التوقيت.
  log "أنتظر انتهاء الهجرات …"
  for i in $(seq 1 120); do
    if python web/manage.py migrate --check >/dev/null 2>&1; then
      log "الهجرات مكتملة"
      break
    fi
    [ "$i" -eq 120 ] && die "لم تكتمل الهجرات خلال دقيقتين"
    sleep 1
  done
fi

# ═══ ٤) الملفّات الساكنة ═══
#
# ‏Django يتوقّف عن تقديمها حين ينطفئ DEBUG. وwhitenoise يقدّمها
# من ``STATIC_ROOT`` — الذي يبقى فارغاً حتى يُنادى collectstatic.
# وبلا هذا تُفتح اللوحة بلا نمطٍ ولا رسوم، وتبدو معطوبة.
if [ "${COLLECT_STATIC:-1}" = "1" ]; then
  log "أجمع الملفّات الساكنة …"
  python web/manage.py collectstatic --noinput --clear >/dev/null
fi

# ═══ ٥) بذر المهامّ المجدولة ═══
#
# قاعدةٌ جديدة بلا مهامّ تعني مجدولاً يعمل ولا يفعل شيئاً أبداً،
# ولا يقول لماذا. و``--stagger`` يوزّعها على دقائق متتالية: كلّها
# على اللحظة نفسها تتزاحم على قفل المسح الواحد فلا تعمل إلّا
# واحدة (وقع هذا فعلاً).
if [ "${SEED_JOBS:-0}" = "1" ]; then
  log "أبذر المهامّ الافتراضية …"
  python web/manage.py run_jobs --seed
  python web/manage.py run_jobs --stagger >/dev/null || true
fi

log "أبدأ: $*"
exec "$@"
