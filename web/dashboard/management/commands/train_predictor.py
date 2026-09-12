# -*- coding: utf-8 -*-
"""يدرّب نموذج التنبؤ على المحاكاة، ويحكم عليه بالصفقات الحقيقية.

    python web/manage.py train_predictor            # قياس بلا ترقية
    python web/manage.py train_predictor --promote  # يرقّي إن اجتاز
    python web/manage.py train_predictor --report   # الأرقام فقط

═══ لماذا مجموعتان ═══

قِيس على القاعدة::

    صفقات محسومة مربوطة بلقطة     13   (المطلوب 100)
    وتيرة الربط                 0.7/يوم → نحو 120 يوماً

فالتدريب على الصفقات وحدها انتظارُ أربعة أشهر. وصفوف المسح ذات
اللقطة والمستويات ٥٠٩، تُسمّى بمحاكاة الخروج على شموع مغلقة فتعطي
١٩٠ صفّاً **الآن**، وبثلاثة أسواق بدل سوقٍ واحد.

═══ والحَكَم يبقى الحقيقة ═══

نسبة الفوز في المحاكاة ‎68.4٪‎ وفي الصفقات الحقيقية ‎46.4٪‎. الفارق
ليس خطأً في المحاكاة بل حدُّها: تفترض أنّ الأمر نُفِّذ عند السعر
المطلوب — بلا انزلاق ولا رفض ولا تأخّر.

فالنموذج يتدرّب على المحاكاة ولا يُرقّى إلّا إن تفوّق على خطّ
الأساس في **صفقاتٍ حقيقية لم يرها قطّ**. المحاكاة تُدرّب،
والحقيقة تحكم.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "يدرّب نموذج التنبؤ ويقيسه على الصفقات الحقيقية"

    def add_arguments(self, parser):
        parser.add_argument("--promote", action="store_true",
                            help="رقِّ النموذج إن اجتاز البوّابة")
        parser.add_argument("--report", action="store_true",
                            help="اعرض الأرقام بلا تدريب")
        parser.add_argument("--min-rows", type=int, default=100,
                            help="أقلّ عدد صفوف للتدريب")

    def handle(self, *args, **opts):
        from dashboard.predictor import (
            build_datasets, engine_name, evaluate, train_and_gate,
        )

        w = self.stdout.write
        data = build_datasets()
        sim, real = data["simulated"], data["real"]

        w("═══ البيانات ═══")
        w(f"  محاكاة:  {sim['eligible_count']:>4} صفّاً"
          f"  (نسبة فوز {sim.get('win_rate')}٪)")
        w(f"  حقيقية:  {real['eligible_count']:>4} صفّاً"
          f"  (نسبة فوز {real.get('win_rate')}٪)")
        if sim.get("skipped"):
            w(f"  استُبعد من المحاكاة: {sim['skipped']}")

        eng = engine_name()
        w(f"\n═══ المحرّك ═══\n  {eng['name']} — {eng['note']}")
        # ═══ لا يُدَّعى LightGBM وهو غيره ═══
        #
        # سلسلة الارتداد: lightgbm ← sklearn ← مصنّفٌ بسيط مكتوب
        # بيدٍ. والثالث يعمل ويُنتج «نموذجاً» — فيظهر في الشاشة
        # «نشط» ويظنّه القارئ LightGBM. فيُقال الاسم صراحةً.
        if eng["name"] != "lightgbm":
            w("  ⚠ LightGBM غير مثبَّت. للتثبيت:")
            w("      pip install lightgbm")

        if opts["report"]:
            return

        if sim["eligible_count"] < opts["min_rows"]:
            w(f"\n✗ صفوف المحاكاة {sim['eligible_count']} دون الحدّ "
              f"{opts['min_rows']} — لا تدريب")
            return

        w("\n═══ التدريب ═══")
        out = train_and_gate(sim, real, promote=opts["promote"])
        for line in out["log"]:
            w("  " + line)

        w("\n═══ البوّابة ═══")
        g = out["gate"]
        w(f"  خطّ الأساس على الحقيقي: {g['baseline']}")
        w(f"  النموذج على الحقيقي:    {g['model']}")
        w(f"  الفارق:                 {g['delta']:+.3f}")
        w(f"  العيّنة الحقيقية:        {g['real_n']} صفّاً")
        if g["passed"]:
            w("  ✓ اجتاز" + ("  · رُقّي" if out.get("promoted")
                             else "  · لم يُرقَّ (بلا ‎--promote‎)"))
        else:
            w(f"  ✗ لم يجتز — {g['reason']}")
            w("  ولا يُرقّى: نموذجٌ لم يثبت على صفقاتك الحقيقية "
              "لا يُبنى عليه قرار مال.")
