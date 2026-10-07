# -*- coding: utf-8 -*-
"""لماذا تأخّرت الجدولة؟ — بالقياس لا بالتخمين.

    docker exec <web> python tools_doctor_cron.py

═══ ما يجيب عنه ═══

كل مهمّة «تنجح» في الشاشة وكلّها متأخّرة. والسبب لا يظهر في حالة
المهامّ لأنّه ليس فيها: هو في **مجموع** مُدَدها.

فهذه الأداة تطبع لكل مهمّة: فترتها، وكم تأخّرت، وكم تستغرق، وكم
تأكل من دورتها. والمهمّة التي زمنها أطول من فترتها مستحيلة
بالبناء — لا تلحق أبداً مهما تُرك الخادم يعمل.

═══ ولماذا مساران ═══

    الخفيف   حسم · مراقبة · محفظة      ثوانٍ
    الثقيل   مسح · مزامنة · انضغاط     دقائق

وخلطُهما في طابورٍ واحد يجعل مهمّةَ الثلاث دقائق تنتظر خلف مسحٍ
مدّته اثنتا عشرة. والأداة تُظهر الحِمل على كل مسار على حدة.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def bar(frac: float, width: int = 18) -> str:
    n = max(0, min(width, int(round(frac * width))))
    return "█" * n + "·" * (width - n)


def main() -> int:
    import django

    django.setup()

    from django.utils import timezone

    from dashboard import cron
    from dashboard.models import ScheduledJob

    now = timezone.now()
    jobs = list(ScheduledJob.objects.all().order_by("priority", "id"))
    if not jobs:
        print("✗ لا مهامّ مسجّلة — شغّل: python web/manage.py run_jobs --seed")
        return 1

    print(__doc__.strip().splitlines()[0])
    print()

    load = {"light": 0.0, "heavy": 0.0}
    impossible: list[str] = []
    late: list[tuple[float, str]] = []
    stuck: list[tuple[float, str]] = []

    hdr = (f"{'المهمّة':<22}{'المسار':<8}{'الفترة':>9}"
           f"{'المدّة':>9}{'التأخّر':>10}  الحِمل")
    print(hdr)
    print("─" * (len(hdr) + 10))

    for j in jobs:
        lane = cron.lane_of(j.handler)
        period = float(j.interval_seconds or 0)
        dur = float(j.last_duration_ms or 0) / 1000.0

        if not j.active:
            print(f"{j.code:<22}{'—':<8}{'موقوفة':>9}")
            continue

        # ═══ المعلّقة تُكشَف أوّلاً ═══
        #
        # صفٌّ يقول «يعمل» منذ ساعات لم يَعُد يعمل: العملية ماتت
        # بين كتابة «بدأ» وكتابة النتيجة. وظهرت ``scan:us`` كذلك
        # وآخر تشغيلٍ لها قبل ثلاث عشرة ساعة.
        if j.last_status == "running" and j.last_run_at:
            stuck_for = (now - j.last_run_at).total_seconds()
            if stuck_for > max(3600, 4 * (j.interval_seconds or 0)):
                stuck.append((stuck_for, j.code))

        # ═══ التأخّر يُقاس بالموعد لا بآخر تشغيل ═══
        #
        # «آخر تشغيل قبل ساعة» لا يعني تأخّراً إن كانت فترتها
        # ساعتين. والمقياس الصحيح: كم مضى على استحقاقها.
        behind = (now - j.next_run).total_seconds() if j.next_run else 0.0
        behind = max(0.0, behind)

        share = (dur / period) if period > 0 else 0.0
        if lane in load:
            load[lane] += share

        flag = ""
        # ═══ المستحيلة بالبناء ═══
        #
        # مهمّةٌ مدّتها أطول من فترتها لا تلحق أبداً: تبدأ التالية
        # وهي متأخّرة أصلاً، ويتراكم الفارق بلا حدّ.
        if period > 0 and dur > period:
            flag = "  ✗ مدّتها أطول من فترتها"
            impossible.append(j.code)
        elif behind > period * 2 and period > 0:
            flag = "  ⚠ متأخّرة أكثر من ضعف فترتها"

        if behind > 0:
            late.append((behind / max(1.0, period), j.code))

        print(f"{j.code:<22}{lane:<8}"
              f"{_m(period):>9}{_m(dur):>9}{_m(behind):>10}  "
              f"{bar(min(1.0, share))}{flag}")

    print()
    print("═══ الحِمل على كل مسار ═══")
    print("  (مجموع «المدّة ÷ الفترة». وفوق ١٫٠ يعني طلباً أكثر من الطاقة)")
    for lane in ("light", "heavy"):
        v = load[lane]
        mark = "✗ مُشبَع" if v > 1.0 else "⚠ قريب" if v > 0.7 else "✓"
        print(f"  {lane:<8} {v:5.2f}×  {bar(min(1.0, v))}  {mark}")

    print()
    if stuck:
        print("✗ مهامّ معلّقة — تقول «تعمل» ولم تُسجَّل نهايتها:")
        for age, code in sorted(stuck, reverse=True):
            print(f"    {code}: منذ {age / 3600:.1f} ساعة")
        print("  والغالب أنّ العملية أُنهيت في أثنائها — إعادة نشر،")
        print("  أو قتلٌ لنفاد الذاكرة، أو قراءةٌ شبكية بلا مهلة.")
        print("  وتُستعاد تلقائياً في دورة الجدولة القادمة. ولتعجيلها:")
        print("    docker exec <scheduler> python web/manage.py "
              "run_jobs --lane light")
        print()

    if impossible:
        print("✗ مهامّ مستحيلة بالبناء — أطِل فترتها أو خفّف عملها:")
        for code in impossible:
            print(f"    {code}")
        print()

    if load["heavy"] > 1.0:
        print("⇒ المسار الثقيل يطلب أكثر من طاقته. الخيارات، بالترتيب:")
        print("   ١. أطِل فترة المسح (١٥د ← ٣٠د) — شمعة 4h أربع ساعات،")
        print("      فالمسح كل ربع ساعة يعيد التحليل ستّ عشرة مرّةً على")
        print("      الشمعة نفسها.")
        print("   ٢. قلّل «فريمات المسح لكل سوق»: كل فريمٍ يضاعف الدورة.")
        print("   ٣. قلّل «فريمات المزامنة لكل سوق».")
        print("   ٤. قلّل ‎max_symbols_per_market‎ في الإعدادات.")
    elif late and max(late)[0] > 2:
        worst = sorted(late, reverse=True)[:3]
        print("⇒ الحِمل مقبول لكنّ هناك تأخّراً — الغالب أنّ المجدول")
        print("   توقّف أو أنّ الدورة الماضية طالت. الأكثر تأخّراً:")
        for ratio, code in worst:
            print(f"    {code}: {ratio:.1f}× فترتها")
    else:
        print("✓ لا تأخّر يُذكر.")

    print()
    print("ملاحظة: «المدّة» هي آخر تشغيل وحده — لا متوسّطاً. ودورةٌ")
    print("واحدة بطيئة لسببٍ عابر تبدو هنا أسوأ ممّا هي.")
    return 0


def _m(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    if seconds < 90:
        return f"{seconds:.0f}ث"
    if seconds < 5400:
        return f"{seconds / 60:.1f}د"
    return f"{seconds / 3600:.1f}س"


if __name__ == "__main__":
    raise SystemExit(main())
