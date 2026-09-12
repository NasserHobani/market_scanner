#!/usr/bin/env bash
# استعادة حزمة ‎tools_ship.py‎ على الخادم.
#
#     bash docker-restore.sh ~/scanner-ship
#     STACK=my-stack bash docker-restore.sh ~/scanner-ship
#
# ═══ الترتيب ليس تفضيلاً ═══
#
# يوقف ‎web‎ و‎scheduler‎ أوّلاً. والاستعادة على قاعدةٍ يكتب فيها
# المجدولُ تترك جداول نصفَ مستعادة: ‎DROP SCHEMA‎ ينتظر اتّصالاً
# مفتوحاً ثمّ ينهار، فيبقى بعض الجداول قديماً وبعضها جديداً — ولا
# شيء في الواجهة يقول ذلك.
#
# ويأخذ نسخةً ممّا على الخادم **قبل** أن يمسّه. مسارُ التراجع
# الوحيد، ولحظةُ أخذه هي هذه لا بعدها.
#
# ولا يحذف ‎/app/data‎: مفتاح Django السرّي هناك، وحذفه يُبطل
# الجلسات بلا فائدة. الأرشيف يُفَكّ فوقه.
set -euo pipefail

DIR="${1:-.}"
STACK="${STACK:-market-scanner}"

die() { printf '\n\xe2\x9c\x97 %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

command -v docker >/dev/null || die "لا docker في المسار."
[ -d "$DIR" ] || die "لا مجلّد: $DIR"

# ─────────── ١) البرهان قبل أيّ تغيير ───────────
say "═══ ١) التحقّق من الحزمة ═══"
cd "$DIR"
[ -f SHA256SUMS ] || die "لا SHA256SUMS في $DIR — الحزمة ناقصة."
if command -v sha256sum >/dev/null; then
    sha256sum -c SHA256SUMS || die "بصمةٌ لا تطابق — النقل قُطع. أعد scp."
else
    say "⚠ لا sha256sum — تخطّي التحقّق من السلامة."
fi
[ -f scanner.dump ] || die "لا scanner.dump"
[ -f EXPECTED_ROWS ] || die "لا EXPECTED_ROWS"
say "✓ الحزمة سليمة"

# ─────────── ٢) الحاويات والوحدات ───────────
say ""
say "═══ ٢) المكدّس: $STACK ═══"
find_svc() {
    docker ps -aq \
        --filter "label=com.docker.compose.project=$STACK" \
        --filter "label=com.docker.compose.service=$1" | head -n1
}
DB=$(find_svc db)
WEB=$(find_svc web)
SCHED=$(find_svc scheduler)
[ -n "$DB" ] || die "لا حاوية db في مكدّس '$STACK'.
  الأسماء المتاحة:
$(docker ps -a --format '    {{.Names}}  ({{.Label "com.docker.compose.project"}})')
  فإن اختلف اسم المكدّس:  STACK=<الاسم> bash docker-restore.sh $DIR"

# اسم الوحدة يُقرأ من الحاوية لا يُخمَّن: بادئة المشروع تتغيّر
# باسم المجلّد وبإعدادات بورتينر، والتخمين الخاطئ يُنشئ وحدةً
# جديدة فارغة ويبدو ناجحاً.
vol_for() {
    docker inspect -f \
      '{{range .Mounts}}{{if eq .Destination "'"$2"'"}}{{.Name}}{{end}}{{end}}' \
      "$1" 2>/dev/null
}
APPVOL=""; REPVOL=""
if [ -n "$WEB" ]; then
    APPVOL=$(vol_for "$WEB" /app/data)
    REPVOL=$(vol_for "$WEB" /app/reports)
fi
say "  db        ${DB:0:12}"
say "  web       ${WEB:0:12}   وحدة البيانات: ${APPVOL:-—}"
say "  scheduler ${SCHED:0:12}"

PGUSER=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$DB" \
         | sed -n 's/^POSTGRES_USER=//p' | head -n1)
PGDB=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$DB" \
       | sed -n 's/^POSTGRES_DB=//p' | head -n1)
PGUSER="${PGUSER:-scanner}"; PGDB="${PGDB:-scanner}"
say "  قاعدة     $PGDB (مستخدم $PGUSER)"

# ═══ بلا ‎-i‎ ═══
#
# ‎docker exec -i‎ يوصل مدخلَ الطرفية بالحاوية ويبتلعه. ونداءٌ
# كهذا داخل حلقةٍ تقرأ ملفّاً يلتهم بقيّة الملفّ — فتتحقّق الحلقة
# من جدولٍ واحد وتخرج، ويبدو التحقّق ناجحاً وقد فحص سطراً.
# و‎-i‎ لازمٌ لـ‎pg_restore‎ وحده، حيث الأرشيف يدخل فعلاً.
psql_() { docker exec "$DB" psql -U "$PGUSER" -d "$PGDB" -At "$@"; }

docker start "$DB" >/dev/null 2>&1 || true
for _ in $(seq 1 60); do
    docker exec "$DB" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1 && break
    sleep 2
done
docker exec "$DB" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null \
    || die "القاعدة لا تستجيب بعد دقيقتين."

# ─────────── ٣) أوقف الكتّاب ───────────
say ""
say "═══ ٣) إيقاف web و scheduler ═══"
for c in $WEB $SCHED; do docker stop "$c" >/dev/null && say "  أُوقف ${c:0:12}"; done

# ─────────── ٤) نسخة تراجع ───────────
say ""
say "═══ ٤) نسخة ممّا على الخادم الآن ═══"
BACK="pre-restore-$(date -u +%Y%m%d-%H%M%S).dump"
if docker exec "$DB" pg_dump -U "$PGUSER" -d "$PGDB" -Fc --no-owner \
        > "$BACK" 2>/dev/null && [ -s "$BACK" ]; then
    say "✓ $BACK — $(du -h "$BACK" | cut -f1)"
else
    rm -f "$BACK"
    say "⚠ لا نسخة تراجع (قاعدةٌ فارغة على الأرجح — وهو متوقَّع في أوّل نقل)"
fi

# ─────────── ٥) القاعدة ───────────
say ""
say "═══ ٥) استعادة القاعدة ═══"
# قطع الاتّصالات المعلَّقة: حاويةٌ أُوقفت للتوّ قد تترك اتّصالاً
# حيّاً ثوانيَ، و‎DROP SCHEMA‎ ينتظره ثمّ يفشل.
psql_ -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
          WHERE datname='$PGDB' AND pid<>pg_backend_pid()" >/dev/null || true

# ═══ تفريغٌ صريح بدل ‎--clean‎ ═══
#
# ‎pg_restore --clean‎ يُصدر ‎DROP‎ لكل كائنٍ ويعدّ فشل أيّ منها
# خطأً، فيخرج بقيمةٍ غير صفرية على قاعدةٍ فارغة — ويبدو النجاح
# فشلاً. والتفريغ أوّلاً يجعل الاستعادة على أرضٍ معروفة.
psql_ -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;
          GRANT ALL ON SCHEMA public TO \"$PGUSER\";" >/dev/null
docker exec -i "$DB" pg_restore -U "$PGUSER" -d "$PGDB" --no-owner \
    < scanner.dump
say "✓ استُعيدت"

# ─────────── ٦) الملفّات ───────────
say ""
say "═══ ٦) الملفّات ═══"
HELPER=$(docker inspect -f '{{.Config.Image}}' "$DB")   # صورةٌ موجودة، بلا سحب
untar_into() {   # $1 وحدة  $2 أرشيف
    [ -n "$1" ] || { say "  ⚠ لا وحدة — تُخطّى $2"; return 0; }
    [ -f "$2" ] || { say "  ⚠ لا $2 في الحزمة"; return 0; }
    say "  $2 → وحدة $1"
    docker run --rm -v "$1":/dest -v "$PWD":/src:ro "$HELPER" \
        sh -c "cd /dest && tar xzf /src/$2"
}
untar_into "$APPVOL" appdata.tar.gz
untar_into "$REPVOL" reports.tar.gz

# ─────────── ٧) البرهان ───────────
say ""
say "═══ ٧) التحقّق ═══"
bad=0
# الوصف 3 لا المدخل القياسي — حزامٌ ثانٍ فوق إزالة ‎-i‎ أعلاه
while IFS=$'\t' read -r t want <&3; do
    [ -n "$t" ] || continue
    got=$(psql_ -c "SELECT COUNT(*) FROM \"$t\"" 2>/dev/null || echo ERR)
    if [ "$got" = "$want" ]; then
        printf '  ✓ %-32s %8s\n' "$t" "$got"
    else
        printf '  ✗ %-32s متوقَّع %s · موجود %s\n' "$t" "$want" "$got"
        bad=$((bad+1))
    fi
done 3< EXPECTED_ROWS

if [ -n "$APPVOL" ]; then
    n=$(docker run --rm -v "$APPVOL":/d:ro "$HELPER" \
        sh -c 'find /d -type f | wc -l')
    say "  ملفّات /app/data: $n"
fi

# ─────────── ٨) التشغيل ───────────
say ""
say "═══ ٨) إعادة التشغيل ═══"
for c in $WEB $SCHED; do docker start "$c" >/dev/null && say "  شُغّل ${c:0:12}"; done

say ""
if [ "$bad" -eq 0 ]; then
    say "✓ تمّ. كل جدولٍ طابق العدد المتوقَّع."
    say "  افتح اللوحة، وراقب /jobs/ بضع دقائق."
    [ -f "$BACK" ] && say "  ونسخة التراجع محفوظة: $DIR/$BACK"
else
    say "✗ $bad جدولاً لم يطابق. لا تعتمد على هذه البيانات."
    say "  السجلّ:  docker logs --tail 100 ${WEB:0:12}"
    [ -f "$BACK" ] && say "  وللتراجع: pg_restore من $DIR/$BACK"
    exit 1
fi
