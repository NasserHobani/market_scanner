"""مسح تلقائي في الخلفية.

يستيقظ عند إغلاق كل شمعة ويمسح، فلا تحتاج كتابة أمر يدوياً.
نفس قاعدة المشروع سارية: التقييم على شموع مغلقة فقط.

قفل واحد يمنع تداخل دورتين — الشبكة البطيئة قد تجعل دورة تمتد
حتى موعد التالية، وتشغيلهما معاً يضاعف الطلبات ويخلط النتائج.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

_lock = threading.Lock()
_state = {
    "running": False,
    "market": None,
    "started_at": None,
    "last_finished": None,
    "last_error": None,
    "last_result": None,
    "thread_started": False,
    "last_blocked": None,
}


def status() -> dict:
    return dict(_state)


def is_running() -> bool:
    return _state["running"]


def note_blocked(market: str, reason: str, *, code: str = "") -> None:
    """يسجّل أن المسح مُنع قبل أن يبدأ.

    نُقلت بوّابة الحداثة من الطلب إلى الخيط، فلم يعد ممكناً إعادة 409
    للمتصفّح. والبديل ليس الصمت: السبب يُسجَّل هنا ويصل عبر
    ``/api/scan/status/`` كما يصل بقيّة أخبار المسح.

    وبلا هذا يضغط المستخدم «امسح الآن» فلا يحدث شيء ولا يعرف لماذا —
    وهو أسوأ من رسالة الخطأ التي حلّت محلّها.
    """
    _state["last_error"] = reason
    _state["last_blocked"] = {"market": market, "reason": reason,
                              "code": code, "at": time.time()}


def run_scan(market: str, timeframe: str | None = None, force: bool = False,
             cached: bool = True) -> dict:
    """دورة واحدة. يعيد فوراً إن كانت هناك دورة جارية.

    ``cached=True`` (افتراضي MD-01): المسح يستهلك بيانات المزامنة الخلفية
    ولا يعيد تنزيل التاريخ. ``force`` يبقى للتوافق ولا يغيّر مسار الجلب.
    """
    if not _lock.acquire(blocking=False):
        # ``busy`` يميّز الازدحام عن الفشل. ومُناديه يقرأ
        # المفتاح لا النصّ العربي — نصٌّ يُترجَم يوماً فيصير
        # الازدحام «فشلاً» بلا أن يتغيّر شيء في المنطق.
        return {"ok": False, "busy": True,
                "reason": "دورة أخرى جارية"}

    _state.update(running=True, market=market, started_at=time.time(),
                  last_error=None)
    try:
        from django.core.management import call_command

        args = ["--market", market]
        if timeframe:
            args += ["--timeframe", timeframe]
        if cached and not force:
            args.append("--cached")
        call_command("scan", *args)
        _state["last_result"] = f"{market} · اكتمل"
        return {"ok": True, "market": market}
    except Exception as exc:  # noqa: BLE001
        log.exception("فشل المسح التلقائي")
        _state["last_error"] = str(exc)[:300]
        return {"ok": False, "reason": str(exc)[:300]}
    finally:
        _state.update(running=False, market=None,
                      last_finished=time.time())
        _lock.release()


def _loop(markets: list[str], initial_delay: float = 8.0) -> None:
    from scanner.live import format_wait, next_close

    time.sleep(initial_delay)          # مهلة حتى يستقر الخادم

    from django.conf import settings
    from scanner.config import load_market

    # أول دورة فوراً إن كانت القاعدة فارغة، حتى لا تجد لوحة فارغة
    from .models import ScanRun
    if not ScanRun.objects.exists():
        for m in markets:
            log.info("مسح أولي: %s", m)
            run_scan(m)

    while True:
        try:
            waits = []
            for m in markets:
                cfg = load_market(settings.SCANNER_CONFIG_DIR / f"{m}.yaml")
                tf = cfg.timeframes[0]
                try:
                    waits.append((next_close(tf), m, tf))
                except ValueError:
                    continue
            if not waits:
                time.sleep(300)
                continue

            waits.sort()
            target, market, tf = waits[0]
            sleep_for = max(20.0, target - time.time() + 20)   # هامش استقرار البيانات
            log.info("الدورة القادمة: %s بعد %s", market, format_wait(sleep_for))
            time.sleep(sleep_for)
            run_scan(market, tf)
        except Exception:  # noqa: BLE001
            log.exception("خطأ في حلقة الجدولة")
            time.sleep(120)


def start(markets: list[str]) -> bool:
    """يشغّل الخيط مرة واحدة فقط."""
    if _state["thread_started"]:
        return False
    _state["thread_started"] = True
    thread = threading.Thread(target=_loop, args=(markets,),
                              name="auto-scan", daemon=True)
    thread.start()
    log.info("المسح التلقائي يعمل: %s", ", ".join(markets))
    return True
