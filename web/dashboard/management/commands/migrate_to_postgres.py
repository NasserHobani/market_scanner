# -*- coding: utf-8 -*-
"""ينقل كل بيانات SQLite إلى PostgreSQL — ويثبت أنّه لم يضع شيء.

    python web/manage.py migrate_to_postgres --check     # قياس بلا كتابة
    python web/manage.py migrate_to_postgres             # النقل
    python web/manage.py migrate_to_postgres --verify    # مقارنة بعد النقل

═══ لماذا نسخٌ مباشر لا dumpdata/loaddata ═══

الطريق المعتاد ``dumpdata > file`` ثمّ ``loaddata`` فيه ثلاثة
مزالق في هذا المشروع تحديداً:

**الترميز.** ``dumpdata > file`` على ويندوز يمرّ عبر أنبوب، وPython
يختار ترميز المخرَج من **نوعه** لا محتواه — فيصير cp1252 وينهار
على أوّل حرفٍ عربي بـ ``UnicodeEncodeError``. وبياناتنا عربية
كلّها. (وقع هذا الشكل من العطب في ``run_checks.py`` من قبل.)

**‏contenttypes.** ``migrate`` ينشئها تلقائياً، ثمّ يصطدم
``loaddata`` بمفاتيح مكرّرة.

**التسلسلات.** ‏PostgreSQL لا يحرّك عدّاد الجدول عند إدراجٍ بمفتاحٍ
صريح — فأوّل صفٍّ جديد بعد النقل يصطدم بمفتاحٍ موجود.

والنسخ المباشر يتجنّبها كلّها: قراءةٌ من اتّصالٍ وكتابةٌ في آخر في
عمليةٍ واحدة، ثمّ إعادة ضبط التسلسلات صراحةً.

═══ وما لا يُنقل ═══

الشموع ليست في القاعدة — هي ملفّات في ``data/candles``. وكذلك
لقطات الميزات وسجلّات الذكاء وقياسات الانضغاط: ملفّات على القرص
لا صفوف. فالنقل يمسّ القاعدة وحدها، وما سواها يبقى كما هو.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

# ═══ الترتيب يتبع الاعتماد ═══
#
# الجدول المُشار إليه يُنقل قبل المشير إليه، وإلّا رُفض المفتاح
# الأجنبي. و``ScanResult`` تشير إلى ``ScanRun``، و``SignalAlert``
# إلى ``ScanResult``، و``JobRun`` إلى ``ScheduledJob``،
# و``PaperTrade`` إلى ``PaperAccount``.
ORDER = [
    "ScanRun", "ScanResult", "SignalAlert", "Watch", "Trade",
    "Setting", "Company", "BlockedSymbol",
    "ScheduledJob", "JobRun",
    "PaperAccount", "PaperTrade",
    # سجلّ رصد PES — بلا مفاتيح أجنبية، فموضعه حرّ
    "PesDetection",
]

BATCH = 500


class Command(BaseCommand):
    help = "ينقل بيانات SQLite إلى PostgreSQL ويتحقّق من الأعداد"

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true",
                            help="اعرض الأعداد على الجانبين بلا كتابة")
        parser.add_argument("--verify", action="store_true",
                            help="قارن الجانبين بعد النقل")
        parser.add_argument("--force", action="store_true",
                            help="انقل ولو كانت الجداول الهدف غير فارغة")

    # ── أدوات ──

    def _models(self):
        from django.apps import apps

        by_name = {m.__name__: m for m in apps.get_app_config("dashboard").get_models()}
        missing = [n for n in ORDER if n not in by_name]
        if missing:
            raise CommandError(
                f"نماذج في الترتيب وليست في التطبيق: {missing}")
        extra = [n for n in by_name if n not in ORDER]
        if extra:
            # ═══ نموذجٌ جديد بلا ترتيب ═══
            #
            # لو مرّ صامتاً لبقيت بياناته في SQLite بلا أن ينتبه
            # أحد — وهو أسوأ من فشلٍ صريح.
            raise CommandError(
                f"نماذج بلا موضع في الترتيب: {extra} — أضفها إلى ORDER")
        return [(n, by_name[n]) for n in ORDER]

    def _counts(self, alias: str) -> dict:
        out = {}
        for name, model in self._models():
            try:
                out[name] = model.objects.using(alias).count()
            except Exception as exc:  # noqa: BLE001
                out[name] = f"✗ {str(exc)[:40]}"
        return out

    def _guard(self):
        from django.conf import settings

        if "legacy" not in settings.DATABASES:
            raise CommandError(
                "لا اتّصال بالقاعدة القديمة. تأكّد أنّ "
                "data/dashboard.sqlite3 موجود وأنّ POSTGRES_DB مضبوط.")
        if "postgresql" not in settings.DATABASES["default"]["ENGINE"]:
            raise CommandError(
                "القاعدة الأساسية ليست PostgreSQL. اضبط POSTGRES_DB "
                "في ‎.env‎ ثمّ أعد التشغيل.")

    def _checkpoint(self) -> str:
        """يدمج سجلّ WAL في ملفّ القاعدة قبل القراءة.

        ═══ لماذا هذا ليس تزيّداً ═══

        القاعدة تعمل بـ ``journal_mode=WAL``: الكتابات تذهب إلى
        ملفٍّ جانبيّ ‎-wal‎ وتُدمَج في الأصل لاحقاً. وقد بلغ ذلك
        السجلّ **٤ ميغابايت غير مدموجة** — أي آلاف الصفوف تعيش
        خارج ملفّ القاعدة.

        والقراءة عبر ``sqlite3`` تراها (يقرأ الاثنين معاً)، فالنقل
        سليمٌ بلا هذا. لكنّ الخطر في الخطوة التالية: من ينسخ
        ‎dashboard.sqlite3‎ وحده — نسخةً احتياطية أو نقلاً إلى
        خادم — يفقد كل ما في ‎-wal‎ **بلا أن يظهر شيء**: الملفّ
        يُفتح، والجداول موجودة، والصفوف الأخيرة ناقصة.

        فالدمج هنا يجعل الملفّ الواحد كاملاً وقابلاً للنسخ.
        """
        from django.db import connections

        conn = connections["legacy"]
        try:
            with conn.cursor() as cur:
                cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                row = cur.fetchone()
            # ‏(busy, صفحات السجلّ, صفحات مدموجة) — و‎busy=1‎ يعني
            # أنّ كاتباً آخر يمنع الدمج، وهو إنذارٌ لا تفصيل.
            if row and row[0]:
                return ("⚠ تعذّر دمج سجلّ WAL — كاتبٌ آخر يعمل. "
                        "أوقف الخادم قبل النقل.")
            return "✓ دُمج سجلّ WAL في ملفّ القاعدة"
        except Exception as exc:  # noqa: BLE001
            return f"⚠ تعذّر دمج WAL: {str(exc)[:80]}"

    # ── التنفيذ ──

    def handle(self, *args, **opts):
        self._guard()
        w = self.stdout.write

        if opts["check"] or opts["verify"]:
            old = self._counts("legacy")
            new = self._counts("default")
            w(f"{'النموذج':<18}{'SQLite':>10}{'Postgres':>12}   الحال")
            w("─" * 56)
            bad = 0
            for name, _ in self._models():
                o, n = old.get(name), new.get(name)
                same = isinstance(o, int) and isinstance(n, int) and o == n
                mark = "✓" if same else ("—" if opts["check"] else "✗")
                if opts["verify"] and not same:
                    bad += 1
                w(f"{name:<18}{str(o):>10}{str(n):>12}   {mark}")
            w("─" * 56)
            to = sum(v for v in old.values() if isinstance(v, int))
            tn = sum(v for v in new.values() if isinstance(v, int))
            w(f"{'المجموع':<18}{to:>10}{tn:>12}")
            if opts["verify"]:
                w("\n✓ الأعداد متطابقة" if not bad
                  else f"\n✗ اختلاف في {bad} جدولاً")
            return

        # ═══ لا يُكتب فوق بياناتٍ قائمة ═══
        #
        # نقلٌ ثانٍ فوق جداول ممتلئة يضاعف الصفوف أو يصطدم
        # بالمفاتيح. والرفض هنا أرخص من التنظيف بعده.
        existing = {k: v for k, v in self._counts("default").items()
                    if isinstance(v, int) and v}
        if existing and not opts["force"]:
            raise CommandError(
                f"الجداول الهدف غير فارغة: {existing}\n"
                "شغّل ‎--force‎ إن كنت تريد الإضافة فوقها، أو أفرغ "
                "القاعدة أوّلاً.")

        # يُدمج قبل القراءة لا بعدها: ما في ‎-wal‎ من صفوف يجب أن
        # يصير في الملفّ قبل أن يُنسخ أو يُقرأ في أيّ مكانٍ آخر.
        w(self._checkpoint())

        total = 0
        for name, model in self._models():
            n = self._copy(model, name)
            total += n
        w(f"\nنُقل {total} صفّاً.")

        self._reset_sequences()
        w("أُعيد ضبط التسلسلات.")
        w("\nللتحقّق: python web/manage.py migrate_to_postgres --verify")

    def _copy(self, model, name: str) -> int:
        """ينسخ جدولاً واحداً على دفعات — بالمفاتيح نفسها."""
        qs = model.objects.using("legacy").all().order_by("pk")
        n = qs.count()
        if not n:
            self.stdout.write(f"  {name:<18} فارغ")
            return 0

        done = 0
        batch: list = []
        for obj in qs.iterator(chunk_size=BATCH):
            # ``_state`` يحمل الاتّصال المصدر؛ وبلا تصفيره يحاول
            # Django تحديث الصفّ في SQLite بدل إدراجه في Postgres.
            obj._state.db = None
            obj._state.adding = True
            batch.append(obj)
            if len(batch) >= BATCH:
                model.objects.using("default").bulk_create(batch)
                done += len(batch)
                batch = []
        if batch:
            model.objects.using("default").bulk_create(batch)
            done += len(batch)
        self.stdout.write(f"  {name:<18} {done:>7} صفّاً")
        return done

    def _reset_sequences(self) -> None:
        """يضبط عدّاد كل جدول بعد الإدراج بمفاتيح صريحة.

        بلا هذا يبدأ العدّاد من ١ فيصطدم أوّل صفٍّ جديد بمفتاحٍ
        موجود — ويظهر العطب بعد الترحيل بساعات، لا عنده.
        """
        from django.core.management.color import no_style
        from django.db import connections

        conn = connections["default"]
        models = [m for _, m in self._models()]
        sql = conn.ops.sequence_reset_sql(no_style(), models)
        if not sql:
            return
        with conn.cursor() as cur:
            for stmt in sql:
                cur.execute(stmt)
