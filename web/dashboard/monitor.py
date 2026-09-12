"""مراقبة الفرص المعلّقة وإطلاق التنبيه عند بلوغ سعر الدخول.

حدّ منهجي يجب أن يكون واضحاً:

الإشارة تُولَّد على شمعة مغلقة — هذا لم يتغيّر. ما تفعله هذه الوحدة هو
مراقبة بلوغ سعرٍ **قرّرناه سلفاً** من تلك الإشارة. الفرق كالفرق بين
«اتخاذ قرار الآن من حركة ناقصة» و«تنفيذ قرار اتُّخذ على شمعة مكتملة».

الأول يعيد مشكلة إعادة الرسم، والثاني هو ما يفعله كل متداول بأمر معلّق.

الأسعار تُجلب في طلب واحد لكل سوق مهما بلغ عدد الرموز المراقَبة.
"""
from __future__ import annotations

import logging
import threading
import time

from django.utils import timezone

log = logging.getLogger(__name__)

_state = {
    "running": False,
    "thread_started": False,
    "last_check": None,
    "checked": 0,
    "triggered_total": 0,
    "last_error": None,
}
_lock = threading.Lock()


def status() -> dict:
    return dict(_state)


# ─────────────────────────────────────────────── جلب الأسعار

def _crypto_prices(symbols: set[str]) -> dict[str, float]:
    """كل أسعار بينانس في طلب واحد — الوزن نفسه مهما زاد عدد الرموز."""
    from scanner.adapters import get_adapter

    adapter = get_adapter("binance")
    data = adapter._get("/api/v3/ticker/price", {})
    out = {}
    for row in data or []:
        sym = row.get("symbol")
        if sym in symbols:
            try:
                out[sym] = float(row["price"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


# تغذية السعر لكل سوق، تُملأ أثناء الجلب.
#
# لماذا تُسجَّل أصلاً: على الخطة الأساسية تنزل لقطات Alpaca إلى IEX،
# وهي بورصة واحدة تحمل ~2.5٪ من حجم السوق. فقد تُطبع فيها صفقة عند سعر
# لم يبلغه الشريط الموحَّد، أو لا تُطبع فيها الحركة التي بلغته. وحالة
# المرصد ``triggered`` **لا رجعة فيها**، فطبعة شاذّة واحدة تستهلك الفرصة
# نهائياً.
#
# ولا سبيل إلى معرفة هل هذا يضرّ فعلاً إلّا بتسجيل التغذية مع كل تحقُّق،
# ثم مقارنة نتائج ما تحقّق على iex بما تحقّق على sip. بلا هذا التسجيل
# يبقى السؤال رأياً.
_FEEDS: dict[str, str] = {}


def _stock_prices(market: str, symbols: list[str]) -> dict[str, float]:
    from django.conf import settings

    from scanner.adapters import get_adapter
    from scanner.config import load_market

    cfg = load_market(settings.SCANNER_CONFIG_DIR / f"{market}.yaml")
    adapter = get_adapter(cfg.adapter)
    if not hasattr(adapter, "quotes"):
        return {}
    quotes = adapter.quotes(symbols)
    if hasattr(adapter, "snapshot_feed"):
        try:
            _FEEDS[market] = str(adapter.snapshot_feed() or "")
        except Exception:  # noqa: BLE001
            pass
    return {k: v["price"] for k, v in quotes.items() if v.get("price")}


# التغذيات التي لا تغطّي السوق كاملاً — السعر منها قرينة لا شريطاً.
PARTIAL_FEEDS = {"iex"}


def feed_for(market: str) -> str:
    """تغذية السعر المستعملة آخر مرّة لهذا السوق (قد تكون فارغة)."""
    return _FEEDS.get(market, "")


def feed_is_partial(market: str) -> bool:
    return feed_for(market) in PARTIAL_FEEDS


def current_prices(watches) -> dict[tuple[str, str], float]:
    """(سوق، رمز) → السعر الحالي."""
    prices: dict[tuple[str, str], float] = {}
    by_market: dict[str, list[str]] = {}
    for w in watches:
        by_market.setdefault(w.market, []).append(w.symbol)

    for market, symbols in by_market.items():
        try:
            if market == "crypto":
                found = _crypto_prices(set(symbols))
            else:
                found = _stock_prices(market, symbols)
            for sym, price in found.items():
                prices[(market, sym)] = price
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر جلب أسعار %s: %s", market, exc)
    return prices


# ─────────────────────────────────────────────── التنبيه

def _alert_text(watch, price: float) -> str:
    from scanner.formatting import price as fmt, ratio

    icon = "🎯" if watch.side == "buy" else "🔻"
    lines = [
        f"{icon} *وصل سعر الدخول* — {watch.symbol}",
        "",
        f"السعر الآن: *{fmt(price)}*",
        f"الدخول المخطط: {fmt(watch.entry)}",
        f"الوقف: {fmt(watch.stop)}",
    ]
    if watch.target1:
        lines.append(f"الهدف: {fmt(watch.target1)}")
    if watch.rr:
        lines.append(f"العائد/المخاطرة: {ratio(watch.rr)}")
    lines.append(f"التصنيف: {watch.grade} · الفريم: {watch.timeframe}")
    if watch.reasons:
        lines.append(f"الأسباب: {watch.reasons}")
    if watch.trigger_text:
        lines += ["", f"_{watch.trigger_text}_"]
    # مصدر السعر جزء من الخبر لا حاشية له: «وصل سعر الدخول» تعني في ذهن
    # القارئ أن الشريط طبع هذا السعر. وعلى IEX قد لا يكون كذلك.
    if feed_is_partial(watch.market):
        lines += ["", "⚠️ السعر من IEX (~2.5٪ من حجم السوق) — "
                      "قد لا يطابق الشريط الموحَّد. أكّده على الشارت."]
    lines += ["", "راجع الشارت قبل التنفيذ — هذا بلوغ مستوى لا أمر تنفيذ."]
    return "\n".join(lines)


def _alerts_on() -> bool:
    """هل تنبيه بلوغ الدخول مُفعَّل؟ العطب يعني التفعيل — التنبيه أهم
    من الصمت عند الشك."""
    try:
        from . import appsettings

        return bool(appsettings.get("telegram_watches", True))
    except Exception:  # noqa: BLE001
        return True


def _interval(fallback: int) -> int:
    try:
        from . import appsettings

        return int(appsettings.get("monitor_seconds", fallback) or fallback)
    except Exception:  # noqa: BLE001
        return fallback


def check_once() -> dict:
    """دورة فحص واحدة. يعيد ملخصاً."""
    from django.db.utils import OperationalError, ProgrammingError

    from scanner.outputs import telegram

    from . import dbretry
    from .models import Trade as _Trade
    from .models import Watch

    now = timezone.now()
    try:
        armed = list(Watch.objects.filter(status="armed"))
    except (OperationalError, ProgrammingError) as exc:
        # الهجرة غير مطبَّقة — نُبلّغ ولا نُسقط الخيط
        _state["last_error"] = "جدول المراقبة غير موجود — شغّل migrate"
        log.warning("جدول المراقبة مفقود: %s", str(exc)[:120])
        return {"checked": 0, "triggered": 0, "error": "migrate"}
    if not armed:
        _state.update(last_check=time.time(), checked=0)
        return {"checked": 0, "triggered": 0}

    # انتهاء الصلاحية أولاً — لا معنى لفحص فرصة مضى وقتها
    expired = [w for w in armed if w.expires_at and w.expires_at <= now]
    for w in expired:
        w.status = "expired"
        dbretry.try_on_lock(
            lambda w=w: w.save(update_fields=["status"]),
            default=None, what=f"إنهاء {w.symbol}",
        )
    armed = [w for w in armed if w not in expired]

    prices = current_prices(armed)
    triggered = 0

    for w in armed:
        price = prices.get((w.market, w.symbol))
        if price is None:
            continue
        w.last_price = price
        w.checked_at = now

        if w.reached(price):
            w.status = "triggered"
            w.triggered_at = now
            w.trigger_price = price
            w.trigger_feed = feed_for(w.market)
            w.notified = False

            # الحفظ **قبل** الإرسال.
            #
            # كان الترتيب معكوساً: يُرسل التنبيه ثم يُحفظ الصفّ. فإن
            # فشل الحفظ — والقاعدة تُقفل أحياناً — بقيت الفرصة «مسلّحة»
            # فأعادت الدورة التالية إرسال التنبيه نفسه، ثم التي بعدها.
            # أي تنبيه مكرّر بلا حدّ على هاتفك عن فرصة واحدة.
            #
            # والآن: إن تعذّر الحفظ لم يُرسَل شيء وتُعاد المحاولة الدورة
            # القادمة. تنبيه متأخّر أهون من سيل تنبيهات.
            saved = dbretry.try_on_lock(
                lambda w=w: (w.save(update_fields=[
                    "status", "triggered_at", "trigger_price", "trigger_feed",
                    "notified", "last_price", "checked_at"]), True)[1],
                default=False, what=f"تسجيل تحقّق {w.symbol}",
            )
            if not saved:
                log.warning("تعذّر تسجيل تحقّق %s — يُؤجَّل التنبيه", w.symbol)
                continue

            ok = telegram.send(_alert_text(w, price)) if _alerts_on() else False
            triggered += 1
            log.info("تحققت فرصة %s عند %s (تغذية: %s · تنبيه: %s)",
                     w.symbol, price, w.trigger_feed or "—", ok)
            if ok:
                # فشلُ هذا الحفظ يترك ``notified=False`` وحده، وهو حقل
                # عرض لا يُعاد الإرسال بناءً عليه — فلا ضرر في تخطّيه
                w.notified = True
                dbretry.try_on_lock(
                    lambda w=w: w.save(update_fields=["notified"]),
                    default=None, what=f"تعليم تنبيه {w.symbol}",
                )
        else:
            # صفّ واحد يتعذّر تحديث سعره لا يُسقط الدورة: بقيّة المراصد
            # أولى بالفحص من سطر عرض
            dbretry.try_on_lock(
                lambda w=w: w.save(update_fields=["last_price", "checked_at"]),
                default=None, what=f"تحديث سعر {w.symbol}",
            )

    # تحديث أسعار الصفقات المتتبَّعة في الدورة نفسها — للعرض فقط.
    # الحسم من الشموع أثناء المسح: عيّنة كل خمس دقائق تُفوّت الفتيل الذي
    # يلمس الوقف ثم يرتدّ، فتحوّل خسارة حقيقية إلى ربح في السجل.
    try:
        from . import trades as trade_svc

        trade_svc.expire_stale()
        live = list(_Trade.objects.filter(status__in=["pending", "open"]))
        if live:
            trade_svc.touch_prices(current_prices(live))
    except (OperationalError, ProgrammingError):
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر تحديث أسعار الصفقات: %s", str(exc)[:120])

    _state.update(last_check=time.time(), checked=len(armed),
                  triggered_total=_state["triggered_total"] + triggered)
    return {"checked": len(armed), "triggered": triggered,
            "expired": len(expired)}


# ─────────────────────────────────────────────── الحلقة

def _loop(interval: int) -> None:
    time.sleep(15)          # مهلة حتى يستقر الخادم
    while True:
        if not _lock.acquire(blocking=False):
            time.sleep(interval)
            continue
        try:
            _state["running"] = True
            from .concurrency import track

            with track("حلقة المراقبة", kind="monitor"):
                result = check_once()
            _state["last_error"] = None
            if result.get("triggered"):
                log.info("تنبيهات مرسلة: %s", result["triggered"])
        except Exception as exc:  # noqa: BLE001
            log.exception("خطأ في حلقة المراقبة")
            _state["last_error"] = str(exc)[:200]
        finally:
            _state["running"] = False
            _lock.release()
        # تُقرأ كل دورة: تعديل الإعداد يسري بلا إعادة تشغيل الخادم
        time.sleep(max(30, _interval(interval)))


def start(interval: int = 300) -> bool:
    if _state["thread_started"]:
        return False
    _state["thread_started"] = True
    threading.Thread(target=_loop, args=(interval,),
                     name="watch-monitor", daemon=True).start()
    log.info("مراقبة الفرص تعمل كل %s ثانية", interval)
    return True
