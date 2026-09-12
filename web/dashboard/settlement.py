# -*- coding: utf-8 -*-
"""حسم الصفقات في الخلفية — مستقلّاً عن المسح.

المشكلة التي يحلّها:

كان الحسم يجري **داخل أمر المسح فقط**، بشموع ذلك المسح. ويترتّب عليه
عطبان صامتان:

  • صفقة على فريم لا يمسحه المسح التلقائي (‏1h مثلاً بينما المسح على
    4h) لا تُحسم أبداً. تبقى «مفتوحة» إلى الأبد مهما بلغ السعر هدفها.
  • إن توقّف المسح التلقائي أو فشل، تجمّد سجلّ الصفقات كله.

وهذا يفسد الغرض من المشروع: صفقة لا تُحسم لا تدخل الإحصاءات، فتظهر
النتائج أفضل أو أسوأ مما هي — لأن الغائب ليس عشوائياً.

الحلّ: دورة مستقلة تجمع الصفقات الحيّة حسب (السوق، الفريم)، تجلب
الناقص من شموع رموزها فقط، وتحسمها بمحرّك ``tracking`` نفسه.

الكلفة ضئيلة: الصفقات الحيّة عشرات لا مئات، والجلب تراكمي — بضع شموع
لكل رمز.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 180          # ثانية
MIN_INTERVAL = 30

_state = {
    "running": False,
    "thread_started": False,
    "last_run": None,
    "last_error": None,
    "checked": 0,
    "settled": 0,
    "settled_total": 0,
    "groups": 0,
    "fetched": 0,
}
_lock = threading.Lock()


def status() -> dict:
    return dict(_state)


# ───────────────────────────────────────────── جلب الشموع

def _fresh_candles(market: str, symbol: str, timeframe: str):
    """شموع محدَّثة للرمز — من المخزَّن مع جلب الناقص وحده.

    الجلب التراكمي هنا ليس تحسيناً بل شرط جدوى: رمز محدَّث يحتاج شمعة
    أو اثنتين، وطلب التاريخ كاملاً لعشرات الرموز كل ثلاث دقائق يستهلك
    حصّة الطلبات بلا فائدة.
    """
    from scanner import storage
    from scanner.adapters import get_adapter
    from scanner.config import load_market

    from django.conf import settings as dj

    cached = storage.load(market, symbol, timeframe)
    try:
        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        adapter = get_adapter(cfg.adapter)
        need = storage.bars_needed(cached, timeframe, cfg.candles)
        # لا شيء جديد يُنتظر: نكتفي بالمخزَّن بدل طلب لا يضيف شمعة
        if cached is not None and need <= 2:
            return cached, False
        fresh = adapter.fetch(symbol, timeframe, need)
        merged = storage.merge(cached, fresh)
        if storage.last_time(merged) != storage.last_time(cached):
            storage.save(market, symbol, timeframe, merged)
        return merged, True
    except Exception as exc:  # noqa: BLE001
        log.debug("تعذّر تحديث شموع %s %s: %s", symbol, timeframe, str(exc)[:100])
        return cached, False


# ───────────────────────────────────────────── دورة واحدة

def settle_once(max_symbols: int = 200) -> dict:
    """يحسم كل صفقة حيّة يمكن حسمها. يعيد ملخّصاً."""
    from django.db.utils import DatabaseError, OperationalError, ProgrammingError

    from . import dbretry

    from . import trades as trade_svc
    from .models import Trade

    summary = {"checked": 0, "settled": 0, "groups": 0, "fetched": 0,
               "expired": 0, "stale": 0, "skipped_locked": 0, "error": None}

    try:
        summary["expired"] = trade_svc.expire_stale()
        # قبل الجلب لا بعده: صفقة على رمز مشطوب تطلب شموعاً لن تصل،
        # فإلغاؤها أولاً يوفّر الطلب ويمنعها من العودة كل دورة
        summary["stale"] = trade_svc.cancel_stale_candles()
        live = list(Trade.objects.filter(status__in=["pending", "open"])
                    .order_by("timeframe", "symbol"))
    except (OperationalError, ProgrammingError):
        summary["error"] = "جدول الصفقات غير موجود — شغّل migrate"
        return summary
    except DatabaseError as exc:
        summary["error"] = str(exc)[:150]
        return summary

    if not live:
        return summary

    # التجميع حسب (سوق، فريم): كل مجموعة تشترك في ملفات الشموع نفسها
    groups: dict[tuple[str, str], list] = {}
    for trade in live:
        groups.setdefault((trade.market, trade.timeframe), []).append(trade)
    summary["groups"] = len(groups)

    seen = 0
    for (market, timeframe), items in groups.items():
        symbols = sorted({t.symbol for t in items})
        candles: dict[str, list] = {}
        for symbol in symbols:
            if seen >= max_symbols:
                break
            seen += 1
            df, fetched = _fresh_candles(market, symbol, timeframe)
            if fetched:
                summary["fetched"] += 1
            if df is None or getattr(df, "empty", True):
                continue
            candles[symbol] = trade_svc.candles_from_frame(df)

        for trade in items:
            rows = candles.get(trade.symbol)
            if not rows:
                continue
            summary["checked"] += 1
            try:
                # القفل ازدحام عابر لا عطب: يُعاد المحاولة، وإن أصرّ
                # تُتخطّى هذه الصفقة وحدها. إسقاط الدورة كلّها كان
                # يترك ما بعدها بلا حسم — وهو فقدُ قياسٍ لا فقدُ سطر سجلّ.
                settled = dbretry.try_on_lock(
                    lambda t=trade, r=rows: trade_svc.resolve_with_candles(t, r),
                    default=None, what=f"حسم {trade.symbol}",
                )
                if settled is None:
                    summary["skipped_locked"] = summary.get("skipped_locked", 0) + 1
                elif settled:
                    summary["settled"] += 1
            except DatabaseError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("تعذّر حسم %s: %s", trade.symbol, str(exc)[:120])

    return summary


# ───────────────────────────────────────────── إصلاح الأوقات القديمة

def repair_times(limit: int = 2000) -> dict:
    """يعيد اشتقاق أوقات الدخول والخروج من الشموع للصفقات المحسومة.

    لماذا لا يكفي الإصلاح في المحرّك: الحسم لا يكتب فوق وقت موجود
    (``if trade.closed_at is None``)، وهو سلوك صحيح — لكنه يعني أن كل
    صفقة حُسمت قبل الإصلاح تبقى بوقت معالجة إلى الأبد. وبعضها بوقت
    خروج **قبل** وقت الدخول لأن المصدرين اختلطا، فتظهر مدتها «—».

    الشموع محفوظة على القرص، فالاشتقاق منها لا يكلّف طلب شبكة.
    """
    from django.db.utils import DatabaseError, OperationalError, ProgrammingError

    from scanner import storage
    from scanner.tracking import LOST, Plan, WON, resolve

    from . import trades as trade_svc
    from .models import Trade

    out = {"checked": 0, "fixed": 0, "inverted": 0, "skipped": 0, "error": None}
    try:
        rows = list(Trade.objects.filter(status__in=[WON, LOST])
                    .order_by("-signal_at")[:limit])
    except (OperationalError, ProgrammingError):
        out["error"] = "جدول الصفقات غير موجود — شغّل migrate"
        return out
    except DatabaseError as exc:
        out["error"] = str(exc)[:150]
        return out

    cache: dict[tuple, list] = {}
    for trade in rows:
        out["checked"] += 1
        was_inverted = bool(trade.opened_at and trade.closed_at
                            and trade.opened_at > trade.closed_at)
        if was_inverted:
            out["inverted"] += 1

        key = (trade.market, trade.symbol, trade.timeframe)
        if key not in cache:
            try:
                df = storage.load(*key)
                cache[key] = trade_svc.candles_from_frame(df)
            except Exception:  # noqa: BLE001
                cache[key] = []
        bars = trade_svc._bars_after(cache[key], trade.candle_time)
        if not bars:
            out["skipped"] += 1
            continue

        plan = Plan(side=trade.side, entry=trade.entry, stop=trade.stop,
                    target=trade.target1)
        if not plan.valid():
            out["skipped"] += 1
            continue
        res = resolve(bars, plan, max_bars=trade_svc.ENTRY_DEADLINE_BARS.get(
            trade.timeframe, 30))

        opened = trade_svc._bar_time(bars, res.entry_bar)
        closed = trade_svc._bar_time(bars, res.exit_bar)
        # صفقة «الآن» تدخل بإغلاق شمعة الإشارة، فالمحرّك لا يعطيها
        # entry_bar لأنها كانت مفتوحة قبل أول شمعة يفحصها
        if opened is None and trade.action in ("now", "breakout"):
            opened = trade.candle_time

        fields = []
        if opened and trade.opened_at != opened:
            trade.opened_at = opened
            fields.append("opened_at")
        if closed and trade.closed_at != closed:
            trade.closed_at = closed
            fields.append("closed_at")
        # لو بقي الانقلاب بعد الاشتقاق فالبيانات لا تسمح بأكثر:
        # نساوي الدخول بالخروج بدل ترك مدة سالبة تظهر «—»
        if (trade.opened_at and trade.closed_at
                and trade.opened_at > trade.closed_at):
            trade.opened_at = trade.closed_at
            if "opened_at" not in fields:
                fields.append("opened_at")

        if fields:
            trade.save(update_fields=fields)
            out["fixed"] += 1

    return out


# ───────────────────────────────────────────── الحلقة

def _interval(fallback: int) -> int:
    try:
        from . import appsettings

        return int(appsettings.get("settlement_seconds", fallback) or fallback)
    except Exception:  # noqa: BLE001
        return fallback


def _loop(interval: int) -> None:
    time.sleep(25)          # مهلة حتى يستقر الخادم وتُطبَّق الهجرات
    while True:
        if not _lock.acquire(blocking=False):
            time.sleep(interval)
            continue
        try:
            _state["running"] = True
            from .concurrency import track

            with track("حلقة الحسم", kind="settlement"):
                result = settle_once()
            _state.update(
                last_run=time.time(),
                checked=result["checked"],
                settled=result["settled"],
                groups=result["groups"],
                fetched=result["fetched"],
                settled_total=_state["settled_total"] + result["settled"],
                last_error=result.get("error"),
            )
            if result["settled"]:
                log.info("حُسمت %s صفقة", result["settled"])
        except Exception as exc:  # noqa: BLE001
            log.exception("خطأ في حلقة الحسم")
            _state["last_error"] = str(exc)[:200]
        finally:
            _state["running"] = False
            _lock.release()
        # تُقرأ كل دورة: تعديل الإعداد يسري بلا إعادة تشغيل الخادم
        time.sleep(max(MIN_INTERVAL, _interval(interval)))


def start(interval: int = DEFAULT_INTERVAL) -> bool:
    if _state["thread_started"]:
        return False
    _state["thread_started"] = True
    threading.Thread(target=_loop, args=(interval,),
                     name="trade-settlement", daemon=True).start()
    log.info("حسم الصفقات يعمل كل %s ثانية", interval)
    return True
