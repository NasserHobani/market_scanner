# -*- coding: utf-8 -*-
"""تشغيل المهامّ المستحقّة مرّة واحدة ثمّ الخروج.

    python web/manage.py run_jobs
    python web/manage.py run_jobs --force scan:crypto
    python web/manage.py run_jobs --list

═══ لماذا أمرٌ خارجيّ ═══

محرّك الجدولة يعمل داخل الخادم. فإغلاق نافذة الطرفية يوقف كل شيء،
ولا شيء ينبّه — لأنّ الشاشة التي تنبّه لا تُفتح حينها.

وهذا الأمر يجعل الجدولة مستقلّة عن الخادم: يُربط بـ Task Scheduler
في ويندوز (أو cron في لينكس) فيعمل كل خمس دقائق، يسأل القاعدة عن
المستحقّ ويشغّله ويخرج.

═══ ولماذا لا يتزاحم مع المحرّك ═══

كلاهما يقرأ ``next_run`` من القاعدة نفسها. فمهمّةٌ شغّلها أحدهما
يتقدّم موعدها، فلا يراها الآخر مستحقّة. والقفل داخل العملية يمنع
التداخل داخلها.

لكن **بين عمليتين** لا قفل: خادمٌ يعمل وأمرٌ خارجيّ في اللحظة
نفسها قد يشغّلان المهمّة مرّتين. فإن ربطت الأمر بالمجدول الخارجي،
أوقف محرّك الخادم::

    SCHEDULER_ENGINE=off
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "يشغّل المهامّ المجدولة المستحقّة مرّة واحدة"

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true",
                            help="اعرض المهامّ وحالتها بلا تشغيل")
        parser.add_argument("--force", metavar="CODE",
                            help="شغّل مهمّة بمفتاحها ولو لم تستحقّ")
        parser.add_argument("--seed", action="store_true",
                            help="أنشئ المهامّ الافتراضية الناقصة")
        parser.add_argument("--stagger", action="store_true",
                            help="وزّع مهامّ المسح على دقائق متتالية")

    def handle(self, *args, **opts):
        from django.utils import timezone

        from dashboard import cron
        from dashboard.models import ScheduledJob

        if opts.get("stagger"):
            # للمهامّ المبذورة قبل هذا الإصلاح: كلّها على اللحظة
            # نفسها، فتتزاحم على قفل المسح الواحد ولا تعمل إلّا
            # واحدة. والتوزيع يُصلحها بلا حذفٍ ولا إعادة بذر.
            from datetime import timedelta

            now = timezone.now()
            n = 0
            for i, j in enumerate(ScheduledJob.objects.filter(handler="scan")
                                  .order_by("code")):
                j.next_run = now + timedelta(minutes=i)
                j.save(update_fields=["next_run", "updated_at"])
                n += 1
                self.stdout.write(f"{j.code} ← بعد {i}د")
            self.stdout.write(f"وُزّعت {n} مهمّة مسح")
            return

        if opts.get("seed"):
            made = cron.ensure_defaults()
            self.stdout.write(f"أُنشئت {made} مهمّة")
            return

        # البذر عند أوّل تشغيل: قاعدةٌ فارغة تعني أنّ الأمر لا يفعل
        # شيئاً أبداً، ولا يقول لماذا.
        if not ScheduledJob.objects.exists():
            cron.ensure_defaults()

        if opts.get("list"):
            now = timezone.now()
            for j in ScheduledJob.objects.all():
                due = "مستحقّة" if j.is_due else (
                    f"بعد {int((j.next_run - now).total_seconds() // 60)}د"
                    if j.next_run else "—")
                state = "نشِطة" if j.active else "موقوفة"
                self.stdout.write(
                    f"{j.code:<20} {state:<8} كل {j.interval_number} "
                    f"{j.interval_type:<8} {due:<12} "
                    f"آخر: {j.last_status} {j.last_message[:40]}")
            return

        code = opts.get("force")
        if code:
            job = ScheduledJob.objects.filter(code=code).first()
            if job is None:
                self.stderr.write(f"لا مهمّة بالمفتاح: {code}")
                return
            out = cron.run_job(job, manual=True)
            self.stdout.write(f"{code}: {out.get('status')} · "
                              f"{out.get('message', '')}")
            return

        # ``block=True`` ضروري: العملية تموت بعد ``handle``، وخيطٌ
        # طليق يُقتل قبل أن يعمل. فتُنتظر النتيجة ثمّ يُخرَج.
        #
        # ═══ وقفلُ القاعدة يُقال بلغةٍ لا بأثرِ استدعاء ═══
        #
        # ‏SQLite يسمح بكاتبٍ واحد. فخادمٌ يعمل ومحرّكه يمسح يحجب
        # هذا الأمر طوال المسح — وأثرُ ثلاثين سطراً لا يقول ذلك.
        from django.db import OperationalError

        try:
            done = cron.run_due(block=True)
        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            raise CommandError(
                "قاعدة البيانات مقفلة — عمليةٌ أخرى تكتب فيها الآن.\n"
                "\n"
                "و‏SQLite يسمح بكاتبٍ واحد، ومسحٌ يستغرق دقائق يحجب\n"
                "كل كاتبٍ سواه طوال مدّته.\n"
                "\n"
                "والسبب الغالب: الخادم يعمل ومحرّكه يمسح. فإمّا أن\n"
                "تُوقف الخادم، أو تُطفئ محرّكه وتعتمد هذا الأمر:\n"
                "\n"
                "    ضع في ‎.env‎:  SCHEDULER_ENGINE=off\n"
                "\n"
                "ولا يصحّ أن يعملا معاً: كلاهما يشغّل المهامّ نفسها،\n"
                "فتُمسح السوق مرّتين وتُفتح الصفقة الورقية مرّتين."
            ) from exc
        if not done:
            self.stdout.write("لا مهمّة مستحقّة")
            return
        for r in done:
            self.stdout.write(f"{r['code']}: {r.get('status')} · "
                              f"{str(r.get('message', ''))[:80]}")
