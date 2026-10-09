"""أمر المسح: يشغّل محرك scanner ويحفظ النتائج في قاعدة البيانات.

    python web/manage.py scan --market crypto
    python web/manage.py scan --market crypto --live
"""
from __future__ import annotations

import logging
import os
import threading
import time

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone as dt_timezone
from pathlib import Path

log = logging.getLogger("dashboard.scan")

# ضمان رؤية حزمة scanner حتى لو شُغّل الأمر عبر wsgi/gunicorn لا manage.py
_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from django.core.management.base import BaseCommand
from django.db import transaction

from scanner import breakout
from scanner.features import store as feature_store
from scanner import liquidity
from scanner import live as live_mod
from scanner import storage
from scanner.adapters import get_adapter
from scanner.config import load_market
from scanner.report import to_frame, tradingview_link
from scanner.scoring import score_symbol, score_with_recommendation

from dashboard import trades as trade_svc
from dashboard.models import ScanResult, ScanRun, SignalAlert, Watch

MIN_CANDLES = 60


class StaleData(Exception):
    """آخر شمعة أقدم من أن يُبنى عليها قرار — رمز مشطوب غالباً."""


# كم شمعة يُسمح للرمز أن يتأخّر قبل استبعاده. ثلاث شموع تحتمل انقطاعاً
# قصيراً أو تأخّر منصّة، ولا تحتمل رمزاً توقّف تداوله.
STALE_BARS = 3


def _known_symbols(market: str) -> list[str]:
    """رموز دليل الشركات لهذا السوق — أوثق من نداء شبكة.

    يعيد فارغاً إن لم يكن ثمّة دليل، فيمضي المسح إلى الاكتشاف الحيّ.
    ولا يرمي أبداً: جدولٌ غير مهاجَر يجب ألّا يمنع مسحاً.
    """
    try:
        from dashboard.models import Company

        return list(
            Company.objects.filter(market=market)
            .order_by("-quote_value", "symbol")
            .values_list("symbol", flat=True)
        )
    except Exception:  # noqa: BLE001
        return []


def _actionable(reco) -> bool:
    """هل لهذا الرمز توصية تستحقّ سياقاً كاملاً؟"""
    if not reco:
        return False
    d = reco.as_dict() if hasattr(reco, "as_dict") else reco
    if not isinstance(d, dict):
        return False
    action = str(d.get("action") or "").strip()
    return bool(action) and action not in ("none", "لا توصية", "—")


def _analyze_batch(items, timeframe, cfg, scorer, *, mode, jobs, failed):
    """تحليل دفعةٍ من الإطارات — بالخيوط أو بالعمليّات.

    العمليّات تُنشأ بـ ``spawn`` صراحةً: هو ما يقع على ويندوز،
    و``fork`` على لينكس يعطي قياساً متفائلاً لا يُنقَل.

    وفشل عاملٍ واحد لا يُسقط الدفعة — يُعدّ ويُمضى.
    """
    from concurrent.futures import ThreadPoolExecutor

    out = []
    if mode == "threads":
        with ThreadPoolExecutor(max_workers=jobs) as p:
            futs = {p.submit(scorer, df, sym, timeframe, cfg): sym
                    for sym, df in items}
            for f in futs:
                try:
                    out.append(f.result())
                except Exception:  # noqa: BLE001
                    failed += 1
        return out, failed

    # ═══ العمليّات: الدالّة والوسائط يجب أن تكون قابلة للنقل ═══
    #
    # ``scorer`` دالّةٌ من الوحدة العليا فتُنقَل، لكنّ ``cfg`` قد
    # يحمل ما لا يُنقَل. والسقوط إلى الخيوط عند التعذّر أنفع من
    # انهيار المسح كلّه لأجل خيار أداء.
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor

    try:
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=jobs, mp_context=ctx) as p:
            futs = {p.submit(scorer, df, sym, timeframe, cfg): sym
                    for sym, df in items}
            for f in futs:
                try:
                    out.append(f.result())
                except Exception:  # noqa: BLE001
                    failed += 1
        return out, failed
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر التحليل بالعمليّات (%s) — سقوط إلى الخيوط",
                    str(exc)[:80])
        return _analyze_batch(items, timeframe, cfg, scorer,
                              mode="threads", jobs=jobs, failed=failed)


class Command(BaseCommand):
    help = "يمسح السوق ويحفظ النتائج في قاعدة البيانات"

    def add_arguments(self, parser):
        parser.add_argument("--market", default="crypto")
        parser.add_argument("--timeframe", default=None)
        parser.add_argument("--top", type=int, default=None)
        parser.add_argument("--live", action="store_true",
                            help="متابعة مستمرة عند إغلاق كل شمعة")
        parser.add_argument("--cycles", type=int, default=0)
        parser.add_argument("--full", action="store_true",
                            help="إعادة تنزيل التاريخ كاملاً بدل الناقص فقط")
        parser.add_argument("--fast", action="store_true",
                            help="بلا تحليل النماذج والموجات (أسرع، بلا توصيات)")
        parser.add_argument("--cached", action="store_true",
                            help="استخدم البيانات المخزّنة (بعد بوابة الحداثة) بلا مزامنة كاملة")
        parser.add_argument("--skip-freshness-gate", action="store_true",
                            help="تخطّى بوابة حداثة البيانات (للاختبار فقط)")
        # ═══ التوازي يُقاس لا يُفترض ═══
        #
        # الافتراضي ``serial`` لأنّ القياس على آلة التطوير قال إنّه
        # الأسرع: الخيوط ×0.78 والعمليّات ×0.55. و pandas يُمسك قفل
        # المفسّر في أجزاء كثيرة، و``spawn`` على ويندوز يعيد استيراد
        # كل شيء في كل عامل.
        #
        # والجواب يعتمد على عدد أنويتك، فالخيار موجود ومقياسه معه:
        #     python tools_bench_parallel.py
        parser.add_argument("--analyze", default="serial",
                            choices=("serial", "threads", "processes"),
                            help="كيف يُوزَّع التحليل — قِسه أوّلاً")
        parser.add_argument("--jobs", type=int, default=4,
                            help="عدد العمّال مع --analyze")

    def handle(self, *args, **opts):
        from django.conf import settings

        cfg_path = settings.SCANNER_CONFIG_DIR / f"{opts['market']}.yaml"
        if not cfg_path.exists():
            self.stderr.write(f"ملف الإعدادات غير موجود: {cfg_path}")
            return

        cfg = load_market(cfg_path)
        # إعدادات الصفحة تعلو ملف YAML: المستخدم يعدّل الصفحة لا الملف،
        # فتركُ الملف هو المرجع يجعل الصفحة زينة بلا أثر
        _apply_settings(cfg)
        timeframe = opts["timeframe"] or cfg.timeframes[0]

        if not opts["live"]:
            self._one_pass(cfg, timeframe, opts)
            return

        stopper = live_mod.Stopper()
        cycle = 0
        while not stopper.stop:
            cycle += 1
            if opts["cycles"] and cycle > opts["cycles"]:
                break
            try:
                self._one_pass(cfg, timeframe, opts)
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"تعذّرت الدورة: {exc}")
            if opts["cycles"] and cycle >= opts["cycles"]:
                break
            wait = max(30, live_mod.next_close(timeframe) - time.time() + 20)
            self.stdout.write(f"الدورة القادمة بعد {live_mod.format_wait(wait)}")
            if not stopper.sleep(wait):
                break

    # ------------------------------------------------------------------

    def _capture_pits(self, jobs: list[tuple], cfg, timeframe: str,
                      score_by_symbol: dict) -> None:
        """لقطات نقطة-الزمن — بعد تثبيت النتائج، صفّاً صفّاً.

        كانت داخل معاملة الحفظ، فموتُ العملية أثناءها يُسقط المسح
        كلّه. وهنا كل صفٍّ مستقلّ: يُلتقط، ثمّ يُربط بنتيجته وبصفقته
        إن فُتحت بلا رابط. وفشلُ واحد لا يمسّ غيره ولا ما حُفظ قبله.

        وصفوف التوصيات أوّلاً: هي التي يُثرى سياقها ويُبنى عليها
        قرار. فإن ضاق الوقت أو الذاكرة نقص الأقلّ أهمّية.
        """
        if not jobs:
            return
        from dashboard.models import Trade
        from scanner.feature_snapshots import PointInTimeSnapshotService

        jobs = sorted(jobs, key=lambda j: not _actionable(j[2]))
        pit_svc = PointInTimeSnapshotService()     # واحدةٌ لا لكل صفّ
        done = failed = 0
        for sym, row, reco, snapshot_id, candle_time in jobs:
            try:
                snap = pit_svc.capture_from_scan_row(
                    symbol=sym, market=cfg.name, timeframe=timeframe,
                    candle_time=candle_time.astimezone(
                        dt_timezone.utc).isoformat(),
                    row=row,
                    reco=reco.as_dict() if reco and hasattr(reco, "as_dict")
                    else (reco if isinstance(reco, dict) else {}),
                    legacy_snapshot_id=snapshot_id,
                    score_result=score_by_symbol.get(sym),
                    # الإثراء الثقيل لمن له توصية وحده: بحث التشابه
                    # وقاعدة المعرفة ثانيتان للرمز — ودقائقُ على كلّ
                    # رمزٍ لن تُتّخذ عليه خطوة.
                    skip_enrichment=not _actionable(reco),
                )
                pit_id = getattr(snap, "snapshot_id", "") or ""
                reco_id = getattr(snap, "recommendation_id", "") or ""
                if not (pit_id or reco_id):
                    continue
                key = dict(symbol=sym, market=cfg.name, timeframe=timeframe,
                           candle_time=candle_time)
                ScanResult.objects.filter(**key).update(
                    pit_snapshot_id=pit_id, recommendation_id=reco_id)
                # الصفقة فُتحت قبل وجود اللقطة: تُربط الآن، وما رُبط
                # من قبل لا يُستبدل.
                Trade.objects.filter(**key, pit_snapshot_id="").update(
                    pit_snapshot_id=pit_id)
                Trade.objects.filter(**key, recommendation_id="").update(
                    recommendation_id=reco_id)
                done += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.warning("PIT capture failed %s %s: %s",
                            sym, timeframe, str(exc)[:160])
        self.stdout.write(f"  لقطات: {done} · فشل {failed}")

    def _one_pass(self, cfg, timeframe: str, opts) -> None:
        adapter = get_adapter(cfg.adapter)
        started = time.time()

        # مصدر القائمة يُسجَّل على الدورة، لا يُكتب إلى stderr وحده.
        #
        # المسح من اللوحة يعمل في خيط، فما يُكتب إلى stderr لا يصل أحداً.
        # وهكذا ظلّ السوق الأمريكي يُمسَح على عشرة أسهم — قائمة الملف —
        # طوال تاريخه، بينما ``universe: auto`` تَعِد بسبعمئة. النظام
        # يعمل بجزء من طاقته ويبدو سليماً، وهذا أخطر من التوقّف.
        universe_source, universe_note = "", ""
        try:
            # ═══ دليل الشركات أوّلاً ═══
            #
            # إن كان في القاعدة دليلٌ لهذا السوق فهو الكون. وهذا ليس
            # تفضيلاً بل تصحيح ترتيب: الدليل قائمةٌ **جُلبت وحُفظت
            # ورآها المستخدم** — ٣٢٦ شركة سعودية. والاكتشاف الحيّ
            # نداءُ شبكةٍ يتعثّر بحدّ معدّل أو انقطاع، فيسقط إلى عشرة
            # رموز مكتوبة في ملف الإعداد.
            #
            # ووقع فعلاً: مُسح السوق السعودي على عشرة أسهم بينما
            # ثلاثمئةٌ وستّ وعشرون منها في الجدول أمام عينيه.
            #
            # فالترتيب الصحيح: الدليل ← الاكتشاف الحيّ ← الكون
            # المحفوظ ← قائمة الملف. وكل درجةٍ أوثق ممّا تحتها.
            known = _known_symbols(cfg.name)
            if known and cfg.universe != "list":
                symbols = known
                cap = opts["top"] or cfg.top_n
                if cap and len(symbols) > cap:
                    # مرتَّب بقيمة التداول نزولاً، فالقصّ يأخذ الأنشط
                    # لا الأبجدي. و``--top`` بلا أثر على هذا المسار كان
                    # سيجعل «جرّب ثلاثين» يمسح ثلاثمئة.
                    symbols = symbols[:cap]
                universe_source = "directory"
                universe_note = (f"دليل الشركات: {len(symbols)} رمزاً "
                                 f"من {len(known)} (محفوظ في القاعدة)")
            elif cfg.universe == "list":
                symbols = cfg.symbols
                universe_source = "list"
                universe_note = f"قائمة الملف: {len(symbols)} رمزاً (بالإعداد)"
            else:
                # الاكتشاف قد يأتي من محوّل غير محوّل الشموع — انظر
                # ``universe_adapter`` في ``MarketConfig``.
                disc = (get_adapter(cfg.universe_adapter)
                        if cfg.universe_adapter else adapter)
                symbols = disc.usdt_universe(cfg.min_quote_volume,
                                             top_n=opts["top"] or cfg.top_n)
                universe_source = "auto"
                src = (f" عبر {cfg.universe_adapter}"
                       if cfg.universe_adapter else "")
                universe_note = f"اكتشاف تلقائي{src}: {len(symbols)} رمزاً"
                extra = getattr(disc, "last_universe_note", "")
                if extra:
                    universe_note += f" — {extra}"
                # اكتشاف ينجح ويعيد عدداً ضئيلاً ليس نجاحاً: العتبة أو
                # الأحجام تعطّلت، والنتيجة تشبه الارتداد وإن لم يقع
                if len(symbols) <= len(cfg.symbols or []):
                    universe_source = "auto_thin"
                    universe_note = (
                        f"الاكتشاف أعاد {len(symbols)} رمزاً فقط — "
                        "تحقّق من العتبة وأحجام التداول"
                    )
        except NotImplementedError:
            symbols = cfg.symbols
            universe_source = "list"
            universe_note = "المحوّل لا يدعم الاكتشاف — قائمة الملف"
        except Exception as exc:  # noqa: BLE001
            # مفتاح خاطئ أو انقطاع لا يجب أن يعطي **صفر** نتائج بينما
            # في الملف قائمة صالحة. النزول إليها مع إعلان السبب أنفع من
            # مسح فاشل: المستخدم يرى أن الاكتشاف تعطّل ولا يفقد اللوحة.
            self.stderr.write(f"تعذّر اكتشاف الرموز: {str(exc)[:300]}")

            # ═══ درجةٌ وسطى قبل قائمة الملف ═══
            #
            # كان النزول من «اكتشاف فاشل» إلى «عشرة رموز في الملف»
            # مباشرةً. وعلى القرص كونٌ كامل اكتُشف قبل ساعات — ورميه
            # لأجل ``429`` عابر خسارةٌ بلا مقابل.
            from scanner import universe_cache as ucache

            disc_name = getattr(cfg, "universe_adapter", "") or cfg.adapter
            saved = ucache.load(disc_name)              # مهما قدُم
            if saved and len(saved["symbols"]) > len(cfg.symbols or []):
                symbols = list(saved["symbols"])
                universe_source = "cached"
                universe_note = (
                    f"تعثّر الاكتشاف الحيّ — المسح على الكون المحفوظ "
                    f"({ucache.describe(disc_name)}) — {str(exc)[:110]}")
                self.stdout.write(
                    f"  الكون المحفوظ: {len(symbols)} رمزاً")
            else:
                symbols = cfg.symbols
                universe_source = "fallback"
                universe_note = (f"تعثّر الاكتشاف التلقائي، والمسح على "
                                 f"{len(symbols)} رمزاً من الملف — "
                                 f"{str(exc)[:150]}")
            if not symbols:
                raise
            self.stdout.write(
                f"  النزول إلى قائمة الملف: {len(symbols)} رمزاً")

        # ═══ الرموز المحظورة تُقطع من الجذر ═══
        #
        # قبل بوّابة الحداثة وقبل أوّل نداء شبكة: الرمز المحظور لا
        # يُجلب ولا يُحلَّل ولا يستهلك من زمن المسح شيئاً.
        #
        # والعدد يُذكر: حذفٌ صامت يجعل المستخدم يرى «320 رمزاً» بدل
        # 326 ولا يعرف أين ذهبت الستّة.
        try:
            from dashboard import blocklist

            symbols, blocked_out = blocklist.filter_symbols(cfg.name, symbols)
            if blocked_out:
                self.stdout.write(
                    f"  محظورة شرعياً — استُبعدت: {len(blocked_out)} "
                    f"({', '.join(blocked_out[:6])}"
                    f"{'…' if len(blocked_out) > 6 else ''})")
        except Exception as exc:  # noqa: BLE001
            # قائمة الحظر ميزةٌ إضافية: عطبها يجب ألّا يمنع مسحاً
            self.stderr.write(f"قائمة الحظر: {str(exc)[:120]}")

        # ═══════════════════════════════════════════════════════════
        #  المسح يُصلح بياناته بنفسه — والحماية بعد الجلب لا قبله
        # ═══════════════════════════════════════════════════════════
        #
        # ═══ ما كان ═══
        #
        # بوّابةٌ قبل الجلب تقيّم القرص، فإن وجدته قديماً **أوقفت
        # المسح** (``MARKET_DATA_STALE`` → ``return``) أو **حذفت**
        # القديم من القائمة (``usable``). والقديم لا يُحدَّث إلّا
        # بمهمّة ``market_sync`` المنفصلة.
        #
        # فصار المسح رهينة مهمّةٍ أخرى: تتعطّل المزامنة، فيتقادم
        # القرص، فتمنع البوّابة المسح، فلا يُجلب شيء — والجالب
        # المتوازي بخيوطه الاثني عشر (``fetch_only`` أسفل) موجودٌ
        # ومعطَّل بالبوّابة التي أمامه. ورأيتَه: «537 مشطوباً من
        # 538 · رموز مفحوصة 1 · تعذّر جلبها 0».
        #
        # البوّابة كانت تمنع **العلاج** لا الخطر.
        #
        # ═══ والخطر نفسه محروسٌ في موضعه ═══
        #
        # الغاية ألّا تُبنى توصيةٌ على سعرٍ قديم. و``fetch_only`` يفحص
        # هذا **بعد** الجلب: ما بقي قديماً بعد محاولة التحديث يرمي
        # ``StaleData`` ولا يصل التحليل. وهذا هو الموضع الصحيح —
        # القرار على البيانات التي ستُحلَّل، لا على ما كان على القرص
        # قبل دقيقة.
        #
        # ═══ فما صار ═══
        #
        #   طازجٌ على القرص   ← يُقرأ بلا شبكة  (كما كان)
        #   قديمٌ على القرص   ← يُجلب متوازياً  (كان: يُحذف أو يوقف المسح)
        #   قديمٌ بعد الجلب   ← ``StaleData``   (كما كان)
        #
        # والبوّابة تبقى **مقياساً** يُطبع، لا حاجزاً. ولا تُنعش
        # (``auto_refresh=False``): إنعاشها تسلسليّ، والجالب متوازٍ —
        # كانت تكرّر عمله ببطءٍ أشدّ داخل المسح نفسه.
        # و``--full`` يبقى يعني «اجلب كل شيء من جديد».
        use_cached = not opts.get("full")
        # يُقاس هنا ويُطوى في ``timing`` أسفل: البوّابة تسبق إنشاءه.
        t_gate = 0.0
        if not opts.get("skip_freshness_gate") and not opts.get("full"):
            try:
                from scanner.market_sync import get_service
                _tg = time.perf_counter()
                gate = get_service().scan_freshness_gate(
                    cfg.name, timeframe, symbols=list(symbols),
                    auto_refresh=False,
                )
                t_gate = time.perf_counter() - _tg
                cnt = gate.get("counts") or {}
                old = int(cnt.get("critical", 0)) + int(cnt.get("dead", 0))
                self.stdout.write(
                    f"  حداثة القرص: {gate.get('code')} · "
                    f"{len(symbols)} رمزاً للمسح"
                    + (f" · {old} قديمٌ سيُجلب الآن" if old else ""))
                if old and old >= max(5, len(symbols) // 2):
                    # المسح سيتعافى وحده، لكنّ السبب يجب أن يُرى:
                    # قرصٌ قديمٌ كلّه = مهمّة المزامنة لا تعمل.
                    self.stderr.write(
                        f"  ⚠ {old} من {len(symbols)} قديمٌ على القرص — "
                        f"مهمّة market_sync متعطّلة على الأرجح. "
                        f"المسح يجلبها الآن، لكن راجع /jobs/.")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"  تعذّرت بوابة الحداثة: {str(exc)[:120]}")

        # الأحجام من النداء نفسه — بلا طلب شبكة إضافي
        volumes = (adapter.quote_volumes()
                   if hasattr(adapter, "quote_volumes") else {})

        # شموع الرموز التي لها صفقة حيّة تُحفظ لحسمها بعد المسح — الشموع
        # مجلوبة أصلاً، فالحسم لا يكلّف طلب شبكة واحداً إضافياً
        tracked = trade_svc.live_symbols(cfg.name, timeframe)
        candles_for_trades: dict[str, list] = {}
        breakouts: dict[str, dict] = {}
        computed_volumes: dict[str, float] = {}
        # القياس يسبق التحسين: بلا تفصيل زمني يصير ضبط الأداء تخميناً
        # ═══ و‎gate‎ كان الجزء الوحيد غير المقيس ═══
        #
        # البوّابة تُنادي ``incremental_refresh_stale`` — وهو جلبٌ
        # شبكيّ **تسلسليّ** داخل المسح. فزمنها يدخل في
        # ``duration_seconds`` ولا يظهر في أيّ خانة من التفصيل،
        # فتُقرأ «شبكة 4ث» على دورةٍ استغرقت دقيقتين.
        #
        # وهذا بالضبط ما يجعل «المسح متأخّر» سؤالاً بلا جواب:
        # الرقم المعروض صادق والتفصيل ناقص.
        timing = {"read": 0.0, "net": 0.0, "write": 0.0, "calc": 0.0,
                  "gate": t_gate, "db": 0.0,
                  "bars": 0, "unchanged": 0, "cached": 0}

        scorer = score_symbol if opts.get("fast") else score_with_recommendation

        # جلب مجمَّع حين يدعمه المحوّل. ليس تحسيناً اختيارياً: Alpaca
        # يسمح بمئتي طلب في الدقيقة على الخطة الأساسية، وطلبٌ لكل رمز
        # يجعل مسح ألف سهم خمس دقائق انتظاراً صافياً — أي أن الاكتشاف
        # التلقائي يصير غير عملي. مئة رمز في الطلب تجعلها عشرة طلبات.
        batched: dict[str, object] = {}
        if (not use_cached and hasattr(adapter, "fetch_many")
                and len(symbols) > 1):
            try:
                batched = _prefetch(adapter, cfg, symbols, timeframe,
                                    full=bool(opts.get("full")))
                self.stdout.write(f"  جلب مجمَّع: {len(batched)} رمزاً")
            except Exception as exc:  # noqa: BLE001
                # السقوط إلى الطلب المفرد يُبقي المسح يعمل ولو أبطأ
                self.stderr.write(f"  تعذّر الجلب المجمَّع: {str(exc)[:150]}")
                batched = {}

        def fetch_only(sym: str):
            """شبكة وقرص فقط — بلا أي تحليل.

            القياس قال إن تشغيل التحليل داخل الخيوط يجعله **أبطأ**
            (×0.65 على 8 خيوط): pandas مقيّد بـ GIL في أجزاء كثيرة منه،
            فالخيوط تتنازع عليه بدل أن تتقاسم العمل. الجلب وحده انتظار
            شبكة خالص وهو ما تنفع فيه الخيوط فعلاً.
            """
            t0 = time.perf_counter()
            cached = storage.load(cfg.name, sym, timeframe)
            t_read = time.perf_counter() - t0

            # ═══ القرص يُستعمل بلا شبكة إن كان فيه الشمعة الجارية ═══
            #
            # كان الشرط ``not is_stale(max_bars=3)`` — أي يُقبل ملفٌّ
            # متأخّرٌ ثلاث شموع. والقرار يُبنى على ``iloc[-2]``، أي
            # يفترض أنّ ``iloc[-1]`` هي الجارية. فملفٌّ متأخّرٌ شمعتين
            # يجعل «آخر شمعة مغلقة» في نظر المحلّل شمعةً مضى عليها
            # ثلاث فترات — على ‎15m‎ خمسٌ وأربعون دقيقة.
            #
            # وما كان يحرسه هو ``market_sync``: يُبقي القرص طازجاً فلا
            # يتأخّر. وحين تتعطّل المزامنة يتآكل هذا الافتراض صامتاً.
            #
            # فالشرط الآن: الملفّ يحمل الشمعة الجارية (تأخّرٌ أقلّ من
            # شمعة). وإلّا جلبٌ تراكميّ — شمعتان أو ثلاث بطلبٍ واحد.
            if use_cached and cached is not None and len(cached) >= MIN_CANDLES:
                _b = storage.bars_behind(cached, timeframe, market=cfg.name)
                if _b is not None and _b < 1.0:
                    timing["read"] += t_read
                    timing["cached"] += 1
                    timing["unchanged"] += 1
                    return cached

            # ═══ فجوةٌ أوسع من جلبة تُعاد بناءً لا دمجاً ═══
            #
            # ``bars_needed`` محدودٌ بـ``candles``. وملفٌّ متأخّرٌ أكثر
            # منها يُدمج مع الجديد فيبقى بينهما **ثقب** — والمؤشّرات
            # تُحسب عبره بلا أن يقول أحدٌ شيئاً: متوسّطٌ يقفز، و‏ATR
            # يتضخّم، وتقاطعٌ يُرى حيث لا تقاطع. تاريخٌ أقصر ونظيف
            # خيرٌ من أطولَ مثقوب.
            if cached is not None:
                _gap = storage.bars_behind(cached, timeframe, market=cfg.name)
                if _gap is not None and _gap > cfg.candles - 2:
                    cached = None

            # الناقص وحده لا التاريخ كله: رمز محدَّث يحتاج شمعة أو اثنتين،
            # وطلب 1500 شمعة له يعني طلبين وعشرات الكيلوبايتات بلا فائدة
            need = cfg.candles if opts.get("full") else storage.bars_needed(
                cached, timeframe, cfg.candles)

            t0 = time.perf_counter()
            if sym in batched:
                fresh = batched[sym]
            else:
                fresh = adapter.fetch(sym, timeframe, need)
            t_net = time.perf_counter() - t0

            before = len(cached) if cached is not None else 0
            last_before = storage.last_time(cached)
            df = storage.merge(cached, fresh)

            # الكتابة تكلّف ~60 م.ث لملف 1500 صف. إعادتها بلا شمعة
            # جديدة هدر خالص يتضاعف بعدد الرموز في كل دورة.
            t0 = time.perf_counter()
            changed = (len(df) != before
                       or storage.last_time(df) != last_before)
            if changed:
                storage.save(cfg.name, sym, timeframe, df)
            t_write = time.perf_counter() - t0

            if len(df) < MIN_CANDLES:
                raise ValueError(f"{len(df)} شمعة فقط")
            # رمز مشطوب: الملف باقٍ والجلب التراكمي لا يعيد شيئاً، فيصير
            # سعر 2022 هو «الآن» في نظر المحلّل. يُتخطّى قبل التحليل حتى
            # لا يُنتج توصية ولا صفقة معلّقة لن تُحسم أبداً.
            # بزمن السوق لا بساعة الحائط: الحدّ ثلاث **جلسات**.
            if storage.is_stale(df, timeframe, max_bars=STALE_BARS,
                                market=cfg.name):
                behind = storage.bars_behind(df, timeframe,
                                             market=cfg.name) or 0
                raise StaleData(f"آخر شمعة متأخرة {behind:.0f} شمعة")

            timing["read"] += t_read
            timing["net"] += t_net
            timing["write"] += t_write
            timing["bars"] += need
            if not changed:
                timing["unchanged"] += 1
            return df

        # تُقرأ مرة واحدة لا لكل رمز: القراءة داخل الحلقة تعني مئات
        # الاستعلامات في الدورة الواحدة
        brk_on, brk_kwargs = _breakout_config()
        tiers = _liquidity_tiers()

        results, failed, stale = [], 0, 0
        workers = max(1, min(int(getattr(cfg, "workers", 8) or 8), 32))
        done = 0

        # الخيوط تجلب، والخيط الرئيسي يحلّل ما يصل أولاً بأول: الشبكة
        # والمعالجة يتداخلان زمنياً بلا تنازع على GIL، والذاكرة تبقى
        # محدودة لأن الإطار يُحلَّل ويُطلق فور وصوله
        mode = opts.get("analyze", "serial")
        jobs = max(1, int(opts.get("jobs") or 4))
        analyze_pool = mode if mode in ("threads", "processes") else None
        pending_frames: list[tuple] = []
        if analyze_pool:
            self.stdout.write(f"  التحليل: {mode} ×{jobs} "
                              f"(قِسه بـ tools_bench_parallel.py)")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch_only, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym = futures[future]
                done += 1
                if not opts["live"] and done % 50 == 0:
                    self.stdout.write(f"  … {done}/{len(symbols)}", ending="\r")
                try:
                    df = future.result()
                except StaleData:
                    # ليس عطباً بل رمزاً توقّف — يُعدّ منفصلاً حتى لا
                    # يختفي داخل «فشل» فيُظنّ خللاً في الشبكة
                    stale += 1
                    continue
                except Exception:  # noqa: BLE001
                    failed += 1
                    continue

                # ═══ التحليل: متسلسل افتراضاً، وموازٍ إن قِيس نافعاً ═══
                #
                # الجلب مُخيَّط لأنّه انتظار شبكة — وهو ما تنفع فيه
                # الخيوط. والتحليل حسابٌ في pandas، والخيوط تتنازع
                # على قفل المفسّر فيه بدل أن تتقاسم العمل.
                #
                # القياس على آلة التطوير (نواتان): خيوط ×0.78 ·
                # عمليّات ×0.55 — كلاهما **أبطأ** من المتسلسل.
                # وجهازك قد يختلف، فـ ``tools_bench_parallel.py``
                # يقيسه عندك، و``--analyze`` يطبّق ما قِيس.
                if analyze_pool is None:
                    try:
                        t0 = time.perf_counter()
                        result = scorer(df, sym, timeframe, cfg)
                        timing["calc"] += time.perf_counter() - t0
                    except Exception:  # noqa: BLE001
                        failed += 1
                        continue
                    results.append(result)
                else:
                    # يُؤجَّل: الإطارات تُجمَع ثمّ تُحلَّل دفعةً
                    pending_frames.append((sym, df))
                    continue
                if sym in tracked:
                    candles_for_trades[sym] = trade_svc.candles_from_frame(df)
                try:
                    hit = (breakout.detect(df, sym, timeframe, **brk_kwargs)
                           if brk_on else None)
                except Exception:  # noqa: BLE001
                    hit = None
                if hit is not None:
                    breakouts[sym] = hit.as_dict()
                qv = liquidity.from_candles(df, timeframe)
                if qv is not None:
                    computed_volumes[sym] = qv

        # المؤجَّل يُحلَّل دفعةً واحدة بالمجمّع المطلوب
        if analyze_pool and pending_frames:
            t0 = time.perf_counter()
            batch, failed = _analyze_batch(
                pending_frames, timeframe, cfg, scorer,
                mode=analyze_pool, jobs=jobs, failed=failed)
            results.extend(batch)
            timing["calc"] += time.perf_counter() - t0
            self.stdout.write(f"  حُلّل {len(batch)} رمزاً في "
                              f"{time.perf_counter() - t0:.1f}ث")

        if not results:
            self.stderr.write("لا نتائج — تحقّق من الاتصال")
            return

        # ═══ لماذا تُعلَن المرحلة الثانية ═══
        #
        # كان المخرَج يقف عند «… 150/150» ثمّ يصمت دقائق. والصمت لا
        # يفرّق بين «يعمل» و«علّق»، فيقتل المستخدمُ عمليّةً كانت على
        # وشك الانتهاء — وهذا ما وقع.
        #
        # وحلقة الجلب ليست كل العمل: بعدها حفظُ لقطة خصائص ولقطة
        # نقطة-زمن وصفٍّ لكل رمز، داخل معاملة واحدة. وهي لا تطبع
        # حرفاً.
        self.stdout.write("")
        self.stdout.write(f"  ✓ اكتمل الفحص: {len(results)} رمزاً في "
                          f"{time.time() - started:.0f}ث")
        self.stdout.write("  … الحفظ (لقطات + نتائج + مراقبات) — قد يطول")

        t_persist = time.time()
        df = to_frame(results)
        df["chart"] = [tradingview_link(cfg.adapter, s, timeframe) for s in df["symbol"]]
        reco_by_symbol = {r.symbol: r.recommendation for r in results}
        score_by_symbol = {r.symbol: r for r in results}
        elapsed = time.time() - started
        _tdb = time.perf_counter()
        pit_jobs: list[tuple] = []

        with transaction.atomic():
            run = ScanRun.objects.create(
                market=cfg.name, timeframe=timeframe, kind="scan",
                duration_seconds=round(elapsed, 1),
                symbols_scanned=len(results), symbols_failed=failed,
                ready_count=int(df["ready"].sum()),
                universe_source=universe_source, universe_note=universe_note,
            )
            saved, alerts, armed, opened, skipped = 0, 0, 0, 0, 0
            fired: list[dict] = []
            reco_candidates: list[tuple] = []
            brk_candidates: list[tuple] = []
            n_rows = len(df)
            for _i_row, (_, r) in enumerate(df.iterrows(), 1):
                if not opts["live"] and _i_row % 25 == 0:
                    self.stdout.write(
                        f"    حفظ {_i_row}/{n_rows} "
                        f"({time.time() - t_persist:.0f}ث)", ending="\r")
                    self.stdout.flush()
                reco = reco_by_symbol.get(r["symbol"])
                candle_time = _as_utc(r["timestamp"])
                snapshot_id = feature_store.write_snapshot(
                    symbol=r["symbol"],
                    market=cfg.name,
                    timeframe=timeframe,
                    candle_time=candle_time,
                    score=float(r["score"]),
                    confluence=int(r.get("confluence", 0)),
                    htf=int(r.get("htf", 0)),
                    liquidity=liquidity.tier(volumes.get(r["symbol"])
                                             or computed_volumes.get(r["symbol"]),
                                             tiers),
                    quote_volume=_num(volumes.get(r["symbol"])
                                      or computed_volumes.get(r["symbol"])),
                    reco=reco,
                    extra_features={
                        "rsi": _num(r.get("rsi")),
                        "rvol": _num(r.get("rvol")),
                        "atr_pct": _num(r.get("atr_pct")),
                        "decision": r.get("decision"),
                        "ready": bool(r.get("ready", False)),
                        "blocker": str(r.get("blocker", ""))[:64],
                    },
                )
                # ═══ اللقطة الثقيلة بعد الحفظ لا داخله ═══
                #
                # كانت تُلتقط هنا، داخل ``transaction.atomic()``: إثراءٌ
                # يقرأ قاعدة المعرفة والتشابه والتجارب لكلّ رمزٍ له
                # توصية. وحين قتلت النواةُ العمليةَ في منتصفه (``Killed``)
                # تراجعت المعاملة كلّها — فلم يُحفظ **صفٌّ واحد**، وبقيت
                # الشاشة على مسحٍ قديم، وكأنّ المسح لم يجرِ.
                #
                # فالنتائج تُحفظ أوّلاً وتُثبَّت، واللقطة بعدها خارج
                # المعاملة وتُربط بالتحديث. وإن ماتت العملية أثناءها
                # بقيت النتائج على الشاشة ونقصت الروابط وحدها.
                pit_id = ""
                reco_id = ""
                pit_jobs.append((r["symbol"], dict(r), reco, snapshot_id,
                                 candle_time))
                obj, created = ScanResult.objects.update_or_create(
                    symbol=r["symbol"], market=cfg.name, timeframe=timeframe,
                    candle_time=candle_time,
                    defaults=dict(
                        run=run, close=float(r["close"]), score=float(r["score"]),
                        decision=r["decision"], confluence=int(r.get("confluence", 0)),
                        reasons=str(r.get("reasons", ""))[:255], htf=int(r.get("htf", 0)),
                        ready=bool(r.get("ready", False)),
                        blocker=str(r.get("blocker", ""))[:64],
                        rsi=_num(r.get("rsi")), rvol=_num(r.get("rvol")),
                        atr_pct=_num(r.get("atr_pct")), chart_url=r.get("chart", ""),
                        feature_snapshot_id=snapshot_id,
                        pit_snapshot_id=pit_id,
                        recommendation_id=reco_id,
                        **_liquidity_fields(volumes.get(r["symbol"])
                                            or computed_volumes.get(r["symbol"]),
                                            tiers),
                        **_reco_fields(reco),
                        **_compliance_fields(r["symbol"], cfg.name),
                    ),
                )
                saved += 1
                armed += _arm_watch(obj, reco, timeframe)
                # الفتح مؤجَّل إلى ما بعد الحلقة: الحدّ على المتزامنات
                # يتطلّب معرفة كل المرشّحين قبل اختيار من يُفتح
                reco_candidates.append((obj, reco))
                if r["symbol"] in breakouts:
                    hit = breakouts[r["symbol"]]
                    hit["liquidity"] = obj.liquidity
                    hit["volume_text"] = _volume_text(obj.quote_volume)
                    hit["url"] = f"/symbol/{cfg.name}/{obj.symbol}/?tf={timeframe}"
                    brk_candidates.append((obj, hit))
                # التنبيه مرة واحدة لكل شمعة — التكرار يأتي من إعادة المسح لا من إشارة جديدة
                if obj.ready and created:
                    SignalAlert.objects.create(
                        result=obj, symbol=obj.symbol, score=obj.score,
                        reasons=obj.reasons,
                    )
                    alerts += 1

            cap = _max_new_trades()
            picked = _best_first(reco_candidates, cap)
            picked, dropped_corr = _drop_correlated(picked, cfg.name,
                                                    timeframe)
            for obj, reco in picked:
                if _open_trade(obj, reco, timeframe):
                    opened += 1
            for obj, hit in _best_breakouts(brk_candidates, cap):
                if _open_breakout(obj, hit, timeframe):
                    fired.append(hit)
            skipped = (max(0, len(reco_candidates) - cap)
                       + max(0, len(brk_candidates) - cap)) if cap else 0

        # ═══ اللقطات بعد التثبيت — النتائج على الشاشة مهما جرى هنا ═══
        _pit_t = time.perf_counter()
        self._capture_pits(pit_jobs, cfg, timeframe, score_by_symbol)
        timing["pit"] = time.perf_counter() - _pit_t

        # مراجعة المستشار — رأي مسجَّل لا قرار. تجري بعد فتح الصفقات
        # عمداً حتى تحمل كل مراجعة معرّف **الصفقة** التي تحكم عليها.
        #
        # العطب الذي عولج: كان يُمرَّر ``str(obj.id)`` وهو معرّف صفّ
        # ScanResult لا صفقة، تحت اسم ``trade_id``. فتراكمت 149 مراجعة
        # لا تنضمّ إلى أي نتيجة — 134 دقيقة من زمن النموذج أنتجت رأياً
        # لا يمكن الحكم عليه. وميزة لا تُقاس مساهمتها غير موجودة بحكم
        # مبادئ المشروع نفسها.
        # ═══ المسار الجديد: حكمٌ بالأدلّة لا مراجعةٌ بستّة وثلاثين حقلاً ═══
        #
        # المسار القديم أنتج ٧٥ قراراً: wait ×65 · insufficient ×5 ·
        # avoid ×4 · watch ×1 · **buy ×0**. و``buy`` موجودة في
        # مفرداته — فليست قيداً في القاموس.
        #
        # والآن: قرارٌ من ثلاثة محصورة، ورقمٌ من سجلّ الصفقات
        # المحسومة، وشرط إبطال بسعر، ورفضٌ **يُحفظ** بسببه.
        try:
            _run_verdicts(self, cfg.name, timeframe, reco_candidates)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"أحكام المستشار: {str(exc)[:120]}")

        try:
            from scanner.ai_advisor.runtime import review_scan_candidates

            trade_ids = _trade_ids_for(cfg.name, timeframe,
                                       [o for o, _ in reco_candidates])
            advisor_items = [
                {
                    "symbol": obj.symbol,
                    "market": cfg.name,
                    "timeframe": timeframe,
                    "ready": obj.ready,
                    "recommendation": reco,
                    "row": {
                        "decision": obj.decision,
                        "htf": obj.htf,
                        "atr_pct": obj.atr_pct,
                        "blocker": obj.blocker,
                        "score": obj.score,
                    },
                    # المعرّف الحقيقي إن فُتحت صفقة، وإلّا فارغ صراحةً
                    "trade_id": trade_ids.get(obj.id, ""),
                    # المفتاح الطبيعي يرافقها دائماً: الصفقة قد تُفتح
                    # لاحقاً (خطة معلّقة)، فالربط الأثري يحتاج ما يثبت
                    "scan_result_id": str(obj.id),
                    "candle_time": (obj.candle_time.isoformat()
                                    if obj.candle_time else ""),
                }
                for obj, reco in reco_candidates if obj.ready
            ]
            advisor_items = _advisor_shortlist(advisor_items)
            # المسار القديم لا يعمل إلّا بطلبٍ صريح. لم يُحذف كي
            # يبقى سجلّه وأدواته قابلةً للفحص، لكنّه لا يُنادى.
            if advisor_items and os.environ.get("LEGACY_AI_REVIEW") == "1":
                linked = sum(1 for i in advisor_items if i["trade_id"])
                self.stdout.write(
                    f"  مستشار AI: {len(advisor_items)} مرشّح "
                    f"({linked} بصفقة) — تجري في الخلفية")
                _run_advisor_async(review_scan_candidates, advisor_items)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"مستشار AI: {str(exc)[:120]}")

        if fired:
            try:
                sent = _send_breakouts(fired, cfg.name, timeframe)
                self.stdout.write(f"  اختراقات: {len(fired)} · أُرسل {sent}")
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(f"تعذّر إرسال تنبيهات الاختراق: {str(exc)[:120]}")

        # خارج المعاملة عمداً: تتبّع الصفقات مرآة للمسح لا شرط لنجاحه،
        # فسقوطه يجب ألا يتراجع عن نتائج محفوظة بالفعل
        try:
            trade_svc.expire_stale()
            settled = trade_svc.resolve_market(cfg.name, timeframe,
                                               candles_for_trades)
        except Exception as exc:  # noqa: BLE001
            settled = {"checked": 0, "changed": 0}
            self.stderr.write(f"تعذّر حسم الصفقات: {str(exc)[:150]}")

        n = max(1, len(results) + failed)
        timing["db"] = (time.perf_counter() - _tdb
                        - timing.get("pit", 0.0))
        # ═══ والمجموع يُطابَق على الكلّ ═══
        #
        # تفصيلٌ لا يُجمع لا يُكتشَف نقصه. و``أخرى`` هي الفرق بين
        # ما قيس وما استُغرق فعلاً — فإن كبرت فثمّة جزءٌ غير مقيس،
        # وهو أهمّ سطرٍ في هذا الإخراج.
        total = time.time() - started
        known = (timing["gate"] + timing["net"] + timing["calc"]
                 + timing["read"] + timing["write"] + timing["db"]
                 + timing.get("pit", 0.0))
        other = max(0.0, total - known)
        self.stdout.write(
            f"  الزمن ({total:.1f}ث): بوّابة {timing['gate']:.1f} · "
            f"شبكة {timing['net']:.1f} · تحليل {timing['calc']:.1f} · "
            f"قراءة {timing['read']:.1f} · كتابة {timing['write']:.1f} · "
            f"قاعدة {timing['db']:.1f} · لقطات {timing.get('pit', 0.0):.1f} · "
            f"أخرى {other:.1f}")
        self.stdout.write(
            f"  ·  {timing['bars'] / n:.0f} شمعة/رمز · "
            f"{timing['unchanged']} بلا جديد")
        # ═══ والأثقل يُسمّى ═══
        #
        # ستّة أرقام تحتاج قراءةً، وسطرٌ واحد يحتاج نظرة. و«المسح
        # متأخّر» سؤالٌ يُجاب بهذا السطر لا بالتخمين.
        parts = {"البوّابة": timing["gate"], "الشبكة": timing["net"],
                 "التحليل": timing["calc"], "القرص": timing["read"]
                 + timing["write"], "القاعدة": timing["db"],
                 "اللقطات": timing.get("pit", 0.0),
                 "غير مقيس": other}
        worst, wsec = max(parts.items(), key=lambda kv: kv[1])
        if total > 0:
            self.stdout.write(
                f"  ⇒ الأثقل: {worst} — {wsec:.1f}ث "
                f"({wsec / total * 100:.0f}٪)")
        if storage.storage_format() == "csv":
            self.stdout.write(self.style.WARNING(
                "  نصيحة: pip install pyarrow — يخزّن بصيغة parquet "
                "فتنخفض قراءة وكتابة الملفات كثيراً"))

        if volumes or computed_volumes:
            from scanner import liquidity as _liq
            spread: dict[str, int] = {}
            for sym in (r["symbol"] for _, r in df.iterrows()):
                key = _liq.tier(volumes.get(sym) or computed_volumes.get(sym), tiers)
                spread[key] = spread.get(key, 0) + 1
            self.stdout.write("  السيولة: " + " · ".join(
                f"{_liq.label(k)} {spread[k]}"
                for k, _, _ in _liq.TIERS if spread.get(k)))

        if stale:
            self.stdout.write(f"  تُخطّي {stale} رمزاً بشموع قديمة "
                              f"(متوقّف تداولها غالباً)")
        if skipped:
            self.stdout.write(f"  حُجب {skipped} مرشّحاً بحدّ الصفقات "
                              f"المتزامنة — عدّله من صفحة الإعدادات")

        # ═══ دليل الشركات يتبع القرص لا يسبقه ═══
        #
        # المسح يجلب الشموع ويكتبها. وبلا هذا يبقى الدليل يقول «٢٥
        # شركة لها تاريخ» بعد مسحٍ جلب ثلاثمئة — مصدران يصفان القرص
        # نفسه ويختلفان، وهو بالضبط النمط الذي كلّفنا جولات في هذه
        # الجلسة (npz غير مرئيّ، والنضارة بمقياسين).
        try:
            from dashboard.companies_views import _refresh_candle_stats

            self.stdout.write("  … تحديث دليل الشركات")
            _refresh_candle_stats(cfg.name)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(f"  تعذّر تحديث دليل الشركات: {str(exc)[:100]}")

        self.stdout.write("")
        self.stdout.write(
            f"  زمن: فحص {t_persist - started:.0f}ث · "
            f"حفظ {time.time() - t_persist:.0f}ث")
        self.stdout.write(self.style.SUCCESS(
            f"{cfg.name} · {timeframe} · حُفظ {saved} نتيجة · "
            f"{run.ready_count} مكتمل الشروط · {alerts} إشارة · "
            f"{armed} فرصة مراقَبة · {opened} صفقة جديدة · "
            f"{settled['changed']} حُسمت · {elapsed:.1f}ث"
        ))


# صلاحية الفرصة: عدد شموع قبل أن تفقد معناها
WATCH_BARS = {"15m": 96, "1h": 48, "4h": 30, "1d": 10, "1w": 4}


_watch_warned = False


def _arm_watch(result_row, reco: dict | None, timeframe: str) -> int:
    """ينشئ فرصة مراقَبة من توصية معلّقة، ويلغي القديمة إن تغيّرت الخطة.

    ميزة إضافية لا يجوز أن تُسقط الوظيفة الأساسية: جدول مفقود أو هجرة
    غير مطبَّقة يجب أن يُنبّه ويُتخطّى، لا أن يُفشل المسح كله.
    """
    global _watch_warned
    from datetime import timedelta

    # ═══ الحرس الثاني ═══
    #
    # قائمة الرموز تُصفّى قبل المسح، لكنّ هذا المسار يُنادى أيضاً
    # من نتيجةٍ مخزّنة سلفاً — فرمزٌ حُظر بعد مسحه قد يُسلَّح.
    try:
        from dashboard import blocklist

        if blocklist.is_blocked(result_row.market, result_row.symbol):
            return 0
    except Exception:  # noqa: BLE001
        pass

    from django.db.utils import DatabaseError, OperationalError, ProgrammingError
    from django.utils import timezone

    from scanner.live import timeframe_seconds

    try:
        return _arm_watch_inner(result_row, reco, timeframe, timedelta,
                                timezone, timeframe_seconds)
    except (OperationalError, ProgrammingError) as exc:
        if not _watch_warned:
            _watch_warned = True
            print("\n⚠ تعذّر تسليح الفرص المراقَبة:", str(exc)[:120])
            print("  شغّل:  python web/manage.py migrate")
            print("  المسح مستمر بدونها.\n")
        return 0
    except DatabaseError as exc:
        if not _watch_warned:
            _watch_warned = True
            print("⚠ خطأ قاعدة بيانات في المراقبة:", str(exc)[:120])
        return 0


def _arm_watch_inner(result_row, reco, timeframe, timedelta, timezone,
                     timeframe_seconds) -> int:
    if not reco or reco.get("action") != "pending" or not reco.get("entry"):
        # لم تعد هناك خطة معلّقة — نلغي أي مراقبة سابقة لهذا الرمز
        Watch.objects.filter(symbol=result_row.symbol, market=result_row.market,
                             timeframe=timeframe, status="armed").update(
                                 status="cancelled")
        return 0

    targets = reco.get("targets") or []
    bars = WATCH_BARS.get(timeframe, 30)
    expires = timezone.now() + timedelta(seconds=timeframe_seconds(timeframe) * bars)

    existing = Watch.objects.filter(symbol=result_row.symbol,
                                    market=result_row.market,
                                    timeframe=timeframe, status="armed").first()
    if existing:
        # الخطة نفسها: نمدّد الصلاحية فقط. تغيّرت: نلغي وننشئ جديدة
        if abs(existing.entry - reco["entry"]) < existing.entry * 0.001:
            existing.expires_at = expires
            existing.save(update_fields=["expires_at"])
            return 0
        existing.status = "cancelled"
        existing.save(update_fields=["status"])

    # المراقبة تصير صفقةً حين يتحقّق شرطها — فمنعُ البيع يبدأ هنا،
    # لا عند التحوّل. ومراقبةُ بيعٍ محفوظة تعني صفقةَ بيعٍ مؤجّلة.
    from scanner import direction as _dir

    if not _dir.allowed(reco.get("side")):
        return 0

    Watch.objects.create(
        symbol=result_row.symbol, market=result_row.market, timeframe=timeframe,
        side=_dir.LONG, entry=reco["entry"], stop=reco["stop"],
        target1=targets[0] if targets else None, rr=reco.get("rr"),
        grade=reco.get("grade", "—"),
        reasons=" · ".join(reco.get("reasons") or [])[:255],
        trigger_text=(reco.get("trigger") or "")[:200],
        expires_at=expires,
    )
    return 1


# أقصى عدد مراجعات لكل مسح. قِيس أن المراجعة الواحدة تستغرق **51
# ثانية** بالوسيط على qwen3:8b محلياً، فعشرون مرشّحاً = سبع عشرة
# دقيقة. والحدّ هنا ليس بخلاً بالزمن بل حماية للقياس: مراجعة تصل بعد
# أن تُحسم الصفقة رأيٌ بأثر رجعي لا قيمة تنبّؤية له.
MAX_ADVISOR_ITEMS = 8



def _run_verdicts(cmd, market: str, timeframe: str, candidates) -> None:
    """يستشير المستشار الجديد على مرشّحي الجولة — في الخلفية.

    ═══ ولماذا الخلفية ═══

    نداء النموذج المحلّي يكلّف ثوانٍ لكل رمز. وتشغيله داخل المسح
    يجعل مسحاً من ثلاث دقائق يستغرق نصف ساعة — وهو ما يجعل
    المستخدم يوقف المسح، فلا يبقى لا مسحٌ ولا حكم.
    """
    from scanner.ai_advisor import auto_review

    rows = []
    for obj, reco in candidates:
        if not auto_review.is_actionable({"ready": obj.ready,
                                          "action": _reco_action(reco)}):
            continue
        rows.append({
            "symbol": obj.symbol, "market": market, "timeframe": timeframe,
            "ready": obj.ready, "action": _reco_action(reco),
            "grade": getattr(obj, "grade", "") or "",
            "score": obj.score, "close": obj.close,
            "reasons": obj.reasons or "",
            "rr": getattr(obj, "rr", None),
            "entry": getattr(obj, "entry", None),
            "stop": getattr(obj, "stop", None),
            "target1": getattr(obj, "target1", None),
            "source": "auto",
        })
    if not rows:
        return

    rows = rows[:auto_review.MAX_ITEMS]
    population = _settled_population()
    cmd.stdout.write(
        f"  أحكام المستشار: {len(rows)} مرشّح على {len(population)} "
        "صفقة محسومة — تجري في الخلفية")

    def worker():
        try:
            recs = auto_review.review_candidates(rows, population)
            log.info("أحكام %s %s: %s", market, timeframe,
                     auto_review.summarize(recs))
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّرت الأحكام: %s", str(exc)[:160])

    threading.Thread(target=worker, name="ai-verdicts", daemon=True).start()


def _reco_action(reco) -> str:
    if reco is None:
        return ""
    if isinstance(reco, dict):
        return str(reco.get("action") or "")
    return str(getattr(reco, "action", "") or "")


def _settled_population() -> list[dict]:
    """كل الصفقات المحسومة — أساس كل نسبة تُذكَر في الأحكام."""
    from dashboard.models import Trade

    cols = ("id", "symbol", "market", "timeframe", "side", "status",
            "r_multiple", "score", "rr", "grade", "source", "action",
            "confidence", "entry_price", "stop", "target1", "reasons")
    have = {f.name for f in Trade._meta.get_fields() if hasattr(f, "name")}
    use = [c for c in cols if c in have]
    return list(Trade.objects.filter(status__in=("won", "lost")).values(*use))


def _advisor_shortlist(items: list[dict]) -> list[dict]:
    """المرشّحون الأجدر بالمراجعة حين لا يتّسع الوقت للجميع.

    الأولوية لمن فُتحت له صفقة فعلاً: هؤلاء وحدهم سيُنتجون نتيجة
    يُقاس عليها رأي المستشار. مراجعة مرشّح لم يُتداول تُنتج رأياً بلا
    شاهد — وهذا بالضبط سبب أن 74 مراجعة من 149 لم تنضمّ إلى أي صفقة.
    """
    if len(items) <= MAX_ADVISOR_ITEMS:
        return items
    with_trade = [i for i in items if i.get("trade_id")]
    without = [i for i in items if not i.get("trade_id")]
    return (with_trade + without)[:MAX_ADVISOR_ITEMS]


def _run_advisor_async(fn, items: list[dict]) -> None:
    """يشغّل المراجعة في خيط خفي — المسح لا ينتظر النموذج أبداً.

    كانت تجري داخل المسح، ومهلتها المضبوطة 300 ثانية. فمع عشرين
    مرشّحاً صار المسح ينتظر ما يقارب **ربع ساعة** بعد أن أنهى عمله
    كله. والمستشار في وضع الظلّ أصلاً — رأيه يُسجَّل ولا يغيّر قراراً —
    فانتظاره كان كلفة خالصة بلا مقابل.

    الخيط خفيّ (daemon) عمداً: إغلاق البرنامج لا ينتظر رأياً لم يصل.
    """
    import threading

    def worker():
        try:
            fn(items)
        except Exception:  # noqa: BLE001
            log.debug("تعذّرت مراجعة المستشار في الخلفية", exc_info=False)

    threading.Thread(target=worker, name="ai-advisor", daemon=True).start()


def _trade_ids_for(market: str, timeframe: str, rows: list) -> dict:
    """صفّ المسح ← معرّف الصفقة المفتوحة منه، إن وُجدت.

    الرابط هو المفتاح الطبيعي (سوق · رمز · فريم · وقت الشمعة) لا رقم
    الصفّ: الصفقة تُنشأ في مسار آخر ولا تحمل مرجعاً للصفّ، والاعتماد
    على تقارب الأرقام كان أصل الخلط الذي جعل ``trade_id`` يحمل معرّف
    ScanResult سنةً كاملة من المراجعات.

    استعلام واحد لكل المسح لا استعلام لكل رمز.
    """
    from dashboard.models import Trade

    if not rows:
        return {}
    times = {r.candle_time for r in rows if r.candle_time}
    symbols = {r.symbol for r in rows}
    if not times or not symbols:
        return {}
    try:
        found = {
            (t.symbol, t.candle_time): str(t.id)
            for t in Trade.objects.filter(
                market=market, timeframe=timeframe,
                symbol__in=list(symbols), candle_time__in=list(times),
                source="auto",
            ).only("id", "symbol", "candle_time")
        }
    except Exception:  # noqa: BLE001
        return {}
    return {r.id: found.get((r.symbol, r.candle_time), "") for r in rows}


def _prefetch(adapter, cfg, symbols: list[str], timeframe: str,
              full: bool = False) -> dict:
    """شموع كل الرموز في أقلّ عدد طلبات — للمحوّلات التي تدعم التجميع.

    الرموز تُقسم مجموعتين لأن حاجتيهما مختلفتان جذرياً:

      • رمز محدَّث يحتاج شمعة أو اثنتين، فنافذته أيام.
      • رمز جديد بلا تخزين يحتاج التاريخ كاملاً، فنافذته سنوات.

    وخلطهما يعني طلب سنوات لكل رمز حتى المحدَّث منه — وهو ما يجعل
    الجلب المجمَّع أثقل من المفرد بدل أن يخفّفه.

    ``storage.load`` هنا مرتين لكل رمز (هنا وفي ``fetch_only``). القراءة
    من parquet أرخص بكثير من طلب شبكة، والبديل تمرير الإطارات بين
    الطبقتين — وهو تعقيد لا يستحقّ ملّي ثانية.
    """
    fresh_needed: list[str] = []
    cold: list[str] = []
    for sym in symbols:
        cached = None if full else storage.load(cfg.name, sym, timeframe)
        need = cfg.candles if cached is None else storage.bars_needed(
            cached, timeframe, cfg.candles)
        (cold if need >= cfg.candles else fresh_needed).append(sym)

    out: dict = {}
    if fresh_needed:
        # نافذة قصيرة تكفي أكثر الرموز تأخّراً في هذه المجموعة
        out.update(adapter.fetch_many(fresh_needed, timeframe,
                                      limit=max(20, cfg.candles // 20)))
    if cold:
        out.update(adapter.fetch_many(cold, timeframe, limit=cfg.candles))
    return out


# ترتيب التصنيفات للأفضلية عند الازدحام
_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "—": 9}


def _max_new_trades() -> int:
    try:
        from dashboard import appsettings

        return max(0, int(appsettings.get("max_new_trades", 3) or 0))
    except Exception:  # noqa: BLE001
        return 3


def _best_first(candidates: list[tuple], cap: int) -> list[tuple]:
    """أفضل ``cap`` توصية من هذا المسح — والباقي يُترك بلا صفقة.

    لماذا الحدّ ضروري، وهو ليس إدارة مخاطر بل شرط قياس:

    فُتحت سبع صفقات في لحظة واحدة على فريم 15m، فخسرت خمس وربحت اثنتان.
    الرقم يقرأ كأنه سبع عيّنات، وهو في الحقيقة **عيّنة واحدة**: سبعة
    رموز في سوق واحد ولحظة واحدة تتحرّك معاً، فحركة واحدة في البتكوين
    تحسمها جميعاً. إحصاء يعامل المرتبط كأنه مستقل يضيّق فاصل الثقة
    زوراً ويجعل النتائج تبدو حاسمة وهي ضجيج.

    والأثر الثاني عملي: سبع خسائر متزامنة تضرب رأس المال دفعة واحدة،
    لا كسبع مخاطرات موزّعة كما تفترض حسبة R.

    الترتيب بالتصنيف ثم الثقة: إن كان لا بدّ من اختيار، فليكن ما تقول
    الأرقام إنه الأفضل — لا أوّل ما وصل من الشبكة.
    """
    if cap <= 0:
        return candidates
    ranked = sorted(
        candidates,
        key=lambda pair: (
            _GRADE_RANK.get((pair[1] or {}).get("grade") or "—", 9),
            -float((pair[1] or {}).get("confidence") or 0.0),
            pair[0].symbol,
        ),
    )
    return ranked[:cap]


def _drop_correlated(picked: list[tuple], market: str, timeframe: str
                     ) -> tuple[list[tuple], list]:
    """يُسقط المرشّح الذي يكرّر مرشّحاً مقبولاً بدل أن يضيف إليه.

    الحدّ العددي وحده يعامل رمزين ارتباطهما 0.9 كرمزين ارتباطهما 0.05،
    والأول صفقة واحدة بحجم مضاعف لا صفقتين.

    القياس على 352 رمزاً: الارتباط الوسيط بالبتكوين ‎+0.46‎، وعنده يكون
    عشرون مركزاً مفتوحاً مكافئاً لـ **2.05 رهاناً مستقلاً** بمخاطرة
    ‎×3.12‎ من المتوقّع. أي أن من يظنّ أنه يخاطر بـ ‎1R‎ عشرين مرة يخاطر
    بما يقارب ‎6R‎ على حركة واحدة.

    الفشل هنا لا يمنع فتح الصفقات: الترشيح تحسين لا شرط تشغيل.
    """
    if len(picked) < 2:
        return picked, []
    try:
        from scanner import correlation, storage

        series = {}
        for obj, _ in picked:
            df = storage.load(market, obj.symbol, timeframe)
            series[obj.symbol] = correlation.returns(df)
        limit = _max_pair_corr()
        if limit <= 0:                 # صفر = الترشيح مطفأ
            return picked, []
        return correlation.select_uncorrelated(picked, series,
                                               max_pair=limit)
    except Exception as exc:  # noqa: BLE001
        log.debug("تعذّر ترشيح الارتباط: %s", str(exc)[:120])
        return picked, []


def _max_pair_corr() -> float:
    try:
        from dashboard import appsettings
        from scanner.correlation import MAX_PAIR_CORR

        return float(appsettings.get("max_pair_corr", MAX_PAIR_CORR))
    except Exception:  # noqa: BLE001
        return 0.55


def _best_breakouts(candidates: list[tuple], cap: int) -> list[tuple]:
    """أعنف ``cap`` اختراق حجماً — لنفس سبب ``_best_first``.

    ارتفاع حجم عام في السوق يفجّر عشرات الرموز معاً، وتسجيلها كلها
    يضخّم عيّنة واحدة إلى عشرات الصفوف المتطابقة النتيجة.
    """
    if cap <= 0:
        return candidates
    return sorted(candidates,
                  key=lambda pair: (-(pair[1].get("rvol") or 0.0),
                                    pair[0].symbol))[:cap]


def _breakout_config() -> tuple[bool, dict]:
    try:
        from dashboard import appsettings

        return appsettings.breakout_enabled(), appsettings.breakout_kwargs()
    except Exception:  # noqa: BLE001
        return True, {}


def _liquidity_tiers():
    try:
        from dashboard import appsettings

        return appsettings.liquidity_tiers()
    except Exception:  # noqa: BLE001
        return None


def _liquidity_fields(quote_volume, tiers=None) -> dict:
    """حجم التداول وتصنيفه — يرافق كل نتيجة بعد خفض عتبة الحجم."""
    return {"quote_volume": _num(quote_volume),
            "liquidity": liquidity.tier(quote_volume, tiers)}


def _apply_settings(cfg) -> None:
    """يكتب إعدادات المستخدم فوق إعدادات الملف.

    الفشل هنا يعني العودة لقيم الملف — وهي صالحة — فلا يُسقط المسح.
    """
    try:
        from dashboard import appsettings

        v = appsettings.values()
    except Exception as exc:  # noqa: BLE001
        print("⚠ تعذّرت قراءة الإعدادات، تُستعمل قيم الملف:", str(exc)[:100])
        return

    cfg.require_htf = bool(v["require_htf"])
    cfg.ml_vote_enabled = bool(v.get("ml_vote_enabled", False))
    cfg.min_quote_volume = float(v["min_quote_volume"])
    cfg.workers = int(v["workers"])
    cfg.candles = int(v["candles"])
    top = int(v["top_n"])
    cfg.top_n = top if top > 0 else None


def _volume_text(quote_volume) -> str:
    return liquidity.human(quote_volume)


def _open_breakout(result_row, hit: dict, timeframe: str) -> bool:
    from django.db.utils import DatabaseError

    try:
        return trade_svc.open_from_breakout(result_row, hit, timeframe) is not None
    except DatabaseError:
        return False


def _send_breakouts(hits: list[dict], market: str, timeframe: str) -> int:
    """تنبيه واحد مجمّع لا رسالة لكل رمز — عشر رسائل متتابعة تُقرأ كضجيج.

    الصياغة تقول «يتحرك الآن» لا «ادخل»: القياس الأوّلي لهذه الإشارة
    لم يثبت أفضليتها، والوعد بما لم يُقس أسوأ من السكوت.
    """
    from scanner.formatting import price as fmt
    from scanner.outputs import telegram

    try:
        from dashboard import appsettings

        if not appsettings.get("telegram_breakouts", True):
            return 0
    except Exception:  # noqa: BLE001
        pass

    hits = sorted(hits, key=lambda h: -(h.get("rvol") or 0))[:8]
    lines = [f"*حركة حجمية* — {market} · {timeframe}", ""]
    for h in hits:
        thin = " ⚠سيولة ضعيفة" if h.get("liquidity") in ("micro", "unknown") else ""
        lines += [
            f"*{h['symbol']}*  {h['change_pct']:+.1f}%  حجم ×{h['rvol']:.0f}"
            f"  ({h.get('volume_text', '—')}){thin}",
            f"   السعر {fmt(h['close'])} · وقف مقترح {fmt(h['stop'])} · "
            f"هدف {fmt(h['target'])}",
        ]
    lines += [
        "",
        "_رصد حركة لا توصية دخول._ قياسها الأوّلي على بياناتنا لم يثبت "
        "أفضليتها على الأساس، وهي مسجّلة كمصدر مستقل في صفحة الأداء "
        "لتُحكم بأرقامها بعد عيّنة كافية.",
    ]
    return 1 if telegram.send("\n".join(lines)) else 0


_trade_warned = False


def _open_trade(result_row, reco: dict | None, timeframe: str) -> bool:
    """يفتح صفقة متتبَّعة — وفشله لا يُسقط المسح أبداً."""
    global _trade_warned
    from django.db.utils import DatabaseError, OperationalError, ProgrammingError

    try:
        return trade_svc.open_from_reco(result_row, reco, timeframe) is not None
    except (OperationalError, ProgrammingError) as exc:
        if not _trade_warned:
            _trade_warned = True
            print("\n⚠ تعذّر تسجيل الصفقات:", str(exc)[:120])
            print("  شغّل:  python web/manage.py migrate")
            print("  المسح مستمر بدونها.\n")
        return False
    except DatabaseError:
        return False


def _compliance_fields(symbol: str, market: str) -> dict:
    """تصنيف شرعي أوّلي — لا حكم، توجيه لما يحتاج تحققاً."""
    try:
        from django.conf import settings

        from scanner.compliance import get_screener

        verdict = get_screener(settings.COMPLIANCE_RULES).check(symbol, market)
        return {"compliance": verdict.status,
                "compliance_reason": verdict.reason[:300]}
    except Exception:  # noqa: BLE001
        return {"compliance": "unknown", "compliance_reason": ""}


def _reco_fields(reco: dict | None) -> dict:
    """تسطيح التوصية إلى أعمدة قاعدة البيانات."""
    if not reco:
        return {"action": "none", "headline": "—"}
    analysis = reco.get("analysis") or {}
    patterns = analysis.get("chart_patterns") or []
    targets = reco.get("targets") or []
    elliott = analysis.get("elliott") or {}
    return {
        "action": reco.get("action", "none"),
        "headline": (reco.get("headline") or "")[:32],
        "entry": reco.get("entry"),
        "stop": reco.get("stop"),
        "target1": targets[0] if targets else None,
        "rr": reco.get("rr"),
        "trigger": (reco.get("trigger") or "")[:200],
        "candle_patterns": "، ".join(analysis.get("candles") or [])[:160],
        "chart_pattern": (patterns[0]["arabic"] if patterns else "")[:48],
        "elliott": (elliott.get("label") or "")[:48],
        "confidence": reco.get("confidence") or 0.0,
        "grade": reco.get("grade") or "—",
    }


def _as_utc(value):
    """توحيد وقت الشمعة إلى datetime واعٍ بالمنطقة.

    ملاحظة: django.utils.timezone.utc حُذف في Django 5، فنستخدم
    datetime.timezone.utc القياسي. محوّلاتنا تُرجع أوقاتاً واعية أصلاً،
    والفرع الآخر احتياط لمصدر بيانات مستقبلي لا يفعل.
    """
    dt = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def _num(value):
    try:
        v = float(value)
        return None if v != v else v      # NaN → NULL بدل قيمة زائفة
    except (TypeError, ValueError):
        return None
