# -*- coding: utf-8 -*-
"""تجهيز سوق كامل بأمر واحد: شركات ← معلومات ← تاريخ ← مسح.

═══ لماذا أمرٌ واحد ═══

بناء السوق السعودي احتاج أربع خطوات في ثلاثة أمكنة: زرّ في اللوحة،
ثمّ زرّ ثانٍ، ثمّ أمرٌ في الطرفية، وبينها إعادة تشغيل الخادم. وكل
خطوةٍ تحتاج معرفةً بما قبلها وما بعدها.

وأي خطوة تُنسى تُنتج حالةً تبدو سليمة وهي ناقصة: ٣٢٦ شركة محفوظة،
٢٥ منها لها شموع، والقطاع غائب عن ٢٩١ — واللوحة تعرض جدولاً لا
يقول أيّها المشكلة.

فهذا الأمر يمشي المسار كلّه بالترتيب، ويطبع بعد كل مرحلة **ما تغيّر
فعلاً** — لا «تمّ» بل «كان كذا وصار كذا».

    python web/manage.py bootstrap_market --market saudi
    python web/manage.py bootstrap_market --market saudi --check
    python web/manage.py bootstrap_market --market saudi --limit 30

═══ ولماذا كلّ مرحلة تُستأنف ═══

المراحل الثقيلة تُقاس بالدقائق، وأي انقطاع فيها كان يُلزم بالبدء من
الصفر. فكلٌّ منها تسأل القرص وقاعدة البيانات أوّلاً: ما نقص وحده
يُجلَب.
"""
from __future__ import annotations

import sys
import time

from django.core.management.base import BaseCommand

OK, BAD, DOT, WARN = "✓", "✗", "·", "!"


class Command(BaseCommand):
    help = "يجهّز سوقاً كاملاً: شركات ← معلومات ← تاريخ ← مسح"

    def add_arguments(self, parser):
        parser.add_argument("--market", default="saudi")
        parser.add_argument("--limit", type=int, default=0,
                            help="اقتصر على أوّل N شركة (تجربة سريعة)")
        parser.add_argument("--check", action="store_true",
                            help="تشخيص بلا أي جلب أو كتابة")
        parser.add_argument("--skip-info", action="store_true")
        parser.add_argument("--skip-history", action="store_true")
        parser.add_argument("--skip-scan", action="store_true")
        parser.add_argument("--no-quotes", action="store_true",
                            help="بلا أسعار وأساسيات (أسرع بكثير)")

    # ──────────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        for stream in (self.stdout, self.stderr):
            try:
                stream._out.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass

        market = opts["market"].strip().lower()
        t0 = time.time()

        self.stdout.write("=" * 60)
        self.stdout.write(f"تجهيز سوق {market}")
        self.stdout.write("=" * 60)

        before = self._state(market)
        self._report("الحالة الآن", before)

        if opts["check"]:
            self._advise(before, market)
            return

        if not opts["skip_info"]:
            self._phase_info(market, with_quotes=not opts["no_quotes"])
            mid = self._state(market)
            self._delta("بعد المعلومات", before, mid)
            before = mid

        if not opts["skip_history"]:
            self._phase_history(market, limit=opts["limit"])
            mid = self._state(market)
            self._delta("بعد التاريخ", before, mid)
            before = mid

        if not opts["skip_scan"]:
            self._phase_scan(market, limit=opts["limit"])
            mid = self._state(market)
            self._delta("بعد المسح", before, mid)
            before = mid

        self.stdout.write("\n" + "=" * 60)
        self._report("الحالة النهائية", before)
        self._advise(before, market)
        self.stdout.write(f"\nالزمن الكلّي: {time.time() - t0:.0f}ث")

    # ── قياس الحالة ───────────────────────────────────────────

    def _state(self, market: str) -> dict:
        """الحقيقة من القاعدة والقرص معاً — لا من ادّعاء مرحلة."""
        from dashboard.models import Company, ScanResult, ScanRun

        qs = Company.objects.filter(market=market)
        total = qs.count()
        run = (ScanRun.objects.filter(market=market, kind="scan")
               .order_by("-id").first())
        return {
            "companies": total,
            "with_sector": qs.exclude(sector="").count(),
            "with_price": qs.filter(price__isnull=False).count(),
            "with_history": qs.filter(candles__gt=0).count(),
            "sectors": qs.exclude(sector="").values("sector").distinct().count(),
            "scanned": run.symbols_scanned if run else 0,
            "run_id": run.id if run else None,
            "results": ScanResult.objects.filter(market=market).count(),
        }

    def _bar(self, n: int, total: int, w: int = 24) -> str:
        if total <= 0:
            return "░" * w
        f = max(0, min(w, round(w * n / total)))
        return "█" * f + "░" * (w - f)

    def _report(self, title: str, s: dict) -> None:
        t = s["companies"] or 1
        self.stdout.write(f"\n[{title}]")
        self.stdout.write(f"  شركات محفوظة   {s['companies']:5}")
        for key, label in (("with_sector", "لها قطاع"),
                           ("with_price", "لها سعر"),
                           ("with_history", "لها شموع")):
            n = s[key]
            self.stdout.write(f"  {label:14} {n:5}  {self._bar(n, t)}"
                              f"  {100.0 * n / t:5.1f}٪")
        self.stdout.write(f"  قطاعات متمايزة {s['sectors']:5}")
        self.stdout.write(f"  آخر دورة مسح   "
                          f"{('#' + str(s['run_id'])) if s['run_id'] else '—':>5}"
                          f"  ({s['scanned']} رمزاً)")

    def _delta(self, title: str, a: dict, b: dict) -> None:
        """ما تغيّر فعلاً — لا «تمّ».

        «تمّت المرحلة» جملةٌ تصدق حتى حين لا يتغيّر شيء. والفرق
        وحده يقول هل نفعت.
        """
        self.stdout.write(f"\n[{title}] ما تغيّر:")
        moved = False
        for key, label in (("companies", "شركات"), ("with_sector", "لها قطاع"),
                           ("with_price", "لها سعر"),
                           ("with_history", "لها شموع"),
                           ("results", "صفوف نتائج")):
            d = b[key] - a[key]
            if d:
                moved = True
                self.stdout.write(f"  {OK} {label}: {a[key]} → {b[key]}"
                                  f"  ({d:+})")
        if not moved:
            self.stdout.write(f"  {WARN} لم يتغيّر شيء — راجع الرسائل أعلاه")

    def _advise(self, s: dict, market: str) -> None:
        t = s["companies"]
        self.stdout.write("\n[الخطوة التالية]")
        if not t:
            self.stdout.write(f"  {BAD} لا شركات — تعذّر الاكتشاف. شغّل:")
            self.stdout.write(f"      python tools_check_universe.py {market}")
            return
        if s["with_history"] < t * 0.5:
            self.stdout.write(
                f"  {WARN} {t - s['with_history']} شركة بلا شموع — أعد الأمر؛"
                " كل جولة تُكمل الناقص.")
        if s["with_sector"] < t * 0.6:
            self.stdout.write(
                f"  {WARN} تغطية القطاع {100.0 * s['with_sector'] / t:.0f}٪ —"
                " تحليل القطاعات لا يُقرأ تحت ٦٠٪.")
        if s["with_history"] >= t * 0.5 and s["with_sector"] >= t * 0.6:
            self.stdout.write(f"  {OK} السوق جاهز للتحليل.")
        self.stdout.write(f"  اللوحة: /scanner/?market={market}")

    # ── المراحل ───────────────────────────────────────────────

    def _phase_info(self, market: str, *, with_quotes: bool) -> None:
        from dashboard import companies_views as cv
        from dashboard import jobs

        self.stdout.write("\n[١] الشركات ومعلوماتها")
        jobs.reset("info")
        jobs.begin("info", scope=market)
        # يُنادى مباشرةً لا في خيط: في الطرفية الانتظار هو المطلوب،
        # والخيط هنا يعني أمراً ينتهي قبل عمله.
        cv._fetch_info(market, with_quotes, with_quotes, True)
        s = jobs.snapshot("info")
        mark = OK if s["state"] == "done" else BAD
        self.stdout.write(f"  {mark} {s.get('note') or ''}"
                          + (f" — {s['error']}" if s.get("error") else ""))

    def _phase_history(self, market: str, *, limit: int) -> None:
        from dashboard import companies_views as cv
        from dashboard import jobs
        from dashboard.models import Company

        pending = Company.objects.filter(market=market, candles=0).count()
        self.stdout.write(f"\n[٢] التاريخ — {pending} شركة بلا شموع")
        if not pending:
            self.stdout.write(f"  {DOT} لا شيء ينتظر")
            return
        if limit:
            self.stdout.write(f"  {DOT} مقصور على {limit} بأمر --limit")
        jobs.reset("history")
        jobs.begin("history", scope=market)
        cv._fetch_history(market, True, limit=limit)
        s = jobs.snapshot("history")
        mark = OK if s["state"] == "done" else BAD
        self.stdout.write(f"  {mark} {s.get('note') or ''}"
                          + (f" — {s['error']}" if s.get("error") else ""))

    def _phase_scan(self, market: str, *, limit: int) -> None:
        from django.core.management import call_command

        self.stdout.write("\n[٣] المسح")
        kw = {"market": market}
        if limit:
            kw["top"] = limit
        try:
            call_command("scan", **kw)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"  {BAD} تعذّر المسح: {str(exc)[:200]}")
