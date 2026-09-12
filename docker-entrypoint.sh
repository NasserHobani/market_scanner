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
# ═══ التحقّق هنا لا في compose ═══
#
# كان في ``docker-compose.yml`` بصيغة ``${VAR:?…}``. وتلك تُفحص
# **وقت تفسير الملفّ**، أي قبل أن تُبنى صورة أو تُقلع حاوية —
# فيسقط النشر كلّه برسالةٍ عن «متغيّر ناقص»، ولو كان الخلل في
# **كيفية إدخاله** لا في غيابه.
#
# وهنا يقع الفحص داخل الحاوية: يظهر في سجلّها، ويقول ما يُفعل،
# ولا يمنع بقيّة المكدّس من الإقلاع.

# ═══ المفتاح السرّي يُولَّد ويُحفظ — لا يُطلب من المستخدم ═══
#
# كان مطلوباً في البيئة. وكان ذلك تحميلاً للمستخدم بلا داعٍ:
# المفتاح لا يعني شيئاً لأحد، وشرطُه الوحيد أن **يثبت** بين
# الإقلاعات وبين عمّال gunicorn الثلاثة — وإلّا انتهت الجلسات
# ورموز CSRF بلا سبب ظاهر.
#
# ووحدة ``/app/data`` تبقى بعد كل بناء ونشر. فالمفتاح يُولَّد
# مرّة ويُقرأ بعدها. والبيئة تعلوه إن ضُبطت صراحةً.
SECRET_FILE="/app/data/.django_secret_key"
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  if [ -s "$SECRET_FILE" ]; then
    DJANGO_SECRET_KEY="$(cat "$SECRET_FILE")"
    log "قُرئ المفتاح السرّي من وحدة البيانات"
  else
    DJANGO_SECRET_KEY="$(python -c \
      'import secrets;print(secrets.token_urlsafe(50))')"
    # ‏umask قبل الكتابة لا chmod بعدها: بين الإنشاء والتقييد
    # نافذةٌ يكون فيها الملفّ مقروءاً للجميع.
    ( umask 077; printf '%s' "$DJANGO_SECRET_KEY" > "$SECRET_FILE" )
    log "وُلِّد مفتاحٌ سرّي جديد وحُفظ في وحدة البيانات"
  fi
  export DJANGO_SECRET_KEY
fi

# ═══ وما يبقى مطلوباً فعلاً ═══
#
# كلمة مرور القاعدة وحدها: تُنشأ بها القاعدة، فلا يستطيع هذا
# الطرف أن يخترعها — لا بدّ أن تطابق ما بُنيت به.
missing=""
for v in POSTGRES_DB POSTGRES_PASSWORD; do
  eval "val=\${$v:-}"
  [ -n "$val" ] || missing="$missing $v"
done

if [ -n "$missing" ]; then
  printf '\n' >&2
  printf '✗ متغيّرات ناقصة:%s\n' "$missing" >&2
  printf '\n' >&2
  # ═══ ما تراه الحاوية فعلاً ═══
  #
  # «متغيّر ناقص» تُقرأ «لم أكتبه». وقد يكون كُتب ولم يصل — وهو
  # ما وقع: مكدّسٌ لا يملكه بورتينر لا تصله متغيّراته. والفرق
  # يغيّر ما يفعله القارئ تماماً، فيُعرض بدل أن يُخمَّن.
  printf '  ── ما وصل هذه الحاوية فعلاً ──\n' >&2
  for v in POSTGRES_DB POSTGRES_USER POSTGRES_HOST DJANGO_ALLOWED_HOSTS \
           SCANNER_TIMEZONE AUTO_SCAN_MARKETS; do
    eval "val=\${$v:-}"
    printf '     %-22s %s\n' "$v" "${val:-(فارغ)}" >&2
  done
  printf '\n' >&2
  printf '  فإن كانت هذه قيماً افتراضية وما كتبتَه غائب، فالمتغيّرات\n' >&2
  printf '  لم تصل النشر — لا أنّك لم تكتبها:\n' >&2
  printf '\n' >&2
  printf '   · المكدّس «Limited / created outside Portainer» لا تصله\n' >&2
  printf '     متغيّرات بورتينر. أزله من طرفية الخادم وأنشئه من جديد:\n' >&2
  printf '       docker compose -p market-scanner down --remove-orphans\n' >&2
  printf '   · أو أنّها لم تُحفظ: افتح الـStack ← Environment variables\n' >&2
  printf '     ويجب أن تراها **في الجدول** اسماً وقيمة\n' >&2
  printf '\n' >&2
  printf '  والقائمة كاملةً في ‎.env.docker.example‎\n' >&2
  die "لن أُقلع بإعداداتٍ ناقصة."
fi

# ═══ ٢) انتظار القاعدة ═══
#
# ‏depends_on في compose ينتظر **إقلاع الحاوية** لا جهوز الخادم.
# وPostgres يقبل الاتّصال بعد ثوانٍ من إقلاعه، فبلا هذا يسقط
# ``migrate`` عند أوّل تشغيل ثمّ ينجح عند الثاني — عطبٌ يختفي
# عند تتبّعه.
# ═══ المهلة تكفي ‎initdb‎ الأوّل ═══
#
# كانت ستّين ثانية. وأوّل إقلاعٍ على قاعدةٍ جديدة يشغّل ``initdb``
# — إنشاء نظام الملفّات كلّه — وعلى قرص خادمٍ صغير قد يتجاوز ذلك
# دقيقة. فتموت هذه الحاوية وتُعاد، وتبدو القاعدة معطوبة وهي تُنشئ
# نفسها.
DB_WAIT="${DB_WAIT_SECONDS:-240}"
log "أنتظر قاعدة البيانات على ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}"\
" (حتى ${DB_WAIT}ث) …"
for i in $(seq 1 "$DB_WAIT"); do
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
  # كل نصف دقيقة: طمأنةٌ بأنّ الانتظار مقصود لا تعليق
  [ $((i % 30)) -eq 0 ] && log "…ما زلت أنتظر (${i}ث)"
  if [ "$i" -eq "$DB_WAIT" ]; then
    printf '\n' >&2
    printf '✗ لم تستجب القاعدة خلال %sث.\n' "$DB_WAIT" >&2
    printf '\n' >&2
    printf '  اقرأ سجلّها — هي التي تعرف السبب:\n' >&2
    printf '    docker logs market-scanner-db-1\n' >&2
    printf '\n' >&2
    printf '  والأسباب الشائعة:\n' >&2
    printf '   · POSTGRES_PASSWORD فارغ — القاعدة ترفض إنشاء نفسها\n' >&2
    printf '   · وحدة تخزين من محاولةٍ سابقة بكلمة مرورٍ أخرى\n' >&2
    printf '   · قرص الخادم ممتلئ\n' >&2
    die "لا أستطيع المتابعة بلا قاعدة."
  fi
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
