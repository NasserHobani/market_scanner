# -*- coding: utf-8 -*-
"""دراسة رمزٍ واحد — تشتغل في خيطٍ خلفيّ لأنّها تمشي على التاريخ.

═══ لماذا خلفيّة ═══

الوسم بالحاجزين يمشي على كل شمعةٍ ثمّ على أفقها: ألفا شمعةٍ بأفق
٢٤ تعني نحو ٤٨ ألف مقارنة. وهي ثوانٍ لا دقائق — لكنّها ثوانٍ
تُجمَّد فيها عمليةُ gunicorn كاملة.

وفي هذا المشروع ثلاثة عمّالٍ لا أكثر. فدراستان متزامنتان تُبقيان
واحداً للموقع كلّه.
"""
from __future__ import annotations

import logging
import threading
import time

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.study")

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_MAX = 8
_TTL = 900.0


def study_page(request):
    from scanner.live import TIMEFRAME_LABELS, UI_TIMEFRAMES

    from .views import MARKETS, market_options

    return render(request, "dashboard/study.html", {
        "nav_page": "study",
        "markets": MARKETS,
        "market_options": market_options(),
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]}
                       for t in UI_TIMEFRAMES],
        "tf_in_page": True,
    })


def _key(market: str, symbol: str, tf: str) -> str:
    return f"{market}|{symbol}|{tf}"


def _run(key: str, market: str, symbol: str, tf: str, params: dict) -> None:
    from scanner import study as study_mod

    started = time.time()
    try:
        out = study_mod.study(market, symbol, tf, **params)
        with _LOCK:
            _JOBS[key] = {"state": "done", "result": out,
                          "elapsed": round(time.time() - started, 1),
                          "at": time.time()}
    except Exception as exc:  # noqa: BLE001
        log.exception("تعذّرت دراسة %s", symbol)
        with _LOCK:
            _JOBS[key] = {"state": "failed", "error": str(exc)[:240],
                          "elapsed": round(time.time() - started, 1),
                          "at": time.time()}


@require_POST
def api_study_start(request):
    symbol = (request.POST.get("symbol") or "").strip().upper()
    market = (request.POST.get("market") or "crypto").strip()
    tf = (request.POST.get("tf") or "4h").strip()

    from scanner.live import UI_TIMEFRAMES

    from .views import MARKETS

    if not symbol.isalnum() or len(symbol) > 24:
        return JsonResponse({"ok": False, "reason": "رمز غير صالح"},
                            status=400)
    if market not in MARKETS or tf not in UI_TIMEFRAMES:
        return JsonResponse({"ok": False, "reason": "سوق أو فريم غير صالح"},
                            status=400)

    def _f(name: str, default: float, lo: float, hi: float) -> float:
        try:
            v = float(request.POST.get(name) or default)
        except (TypeError, ValueError):
            return default
        # ═══ الحدود تُفرَض لا تُرجى ═══
        #
        # هدفٌ بـ‎0×ATR‎ يجعل كل شمعةٍ رابحة، وأفقٌ بألفٍ يمشي على
        # التاريخ كلّه لكل شمعة. وكلاهما يُدخَل بالخطأ.
        return max(lo, min(hi, v))

    params = {
        "target_atr": _f("target", 2.0, 0.5, 10.0),
        "stop_atr": _f("stop", 1.0, 0.25, 10.0),
        "horizon": int(_f("horizon", 24, 4, 200)),
    }

    key = _key(market, symbol, tf)
    with _LOCK:
        job = _JOBS.get(key)
        if job and job["state"] == "running":
            return JsonResponse({"ok": True, "state": "running",
                                 "reason": "دراسةٌ جارية لهذا الرمز"})
        # تنظيف ما شاخ — وإلّا نمت الذاكرة بلا حدّ
        now = time.time()
        for k in [k for k, v in _JOBS.items()
                  if v.get("state") != "running"
                  and now - v.get("at", now) > _TTL]:
            _JOBS.pop(k, None)
        if sum(1 for v in _JOBS.values() if v["state"] == "running") >= 2:
            return JsonResponse(
                {"ok": False,
                 "reason": "دراستان تعملان الآن — انتظر إحداهما. "
                           "الخادم ثلاثة عمّال، وثالثةٌ تُجمّد الموقع."},
                status=429)
        if len(_JOBS) >= _MAX:
            _JOBS.pop(next(iter(_JOBS)), None)
        _JOBS[key] = {"state": "running", "at": time.time()}

    threading.Thread(target=_run, args=(key, market, symbol, tf, params),
                     name=f"study-{symbol}", daemon=True).start()
    return JsonResponse({"ok": True, "state": "running", "key": key})


@require_GET
def api_study_status(request):
    symbol = (request.GET.get("symbol") or "").strip().upper()
    market = (request.GET.get("market") or "crypto").strip()
    tf = (request.GET.get("tf") or "4h").strip()
    job = _JOBS.get(_key(market, symbol, tf))
    if not job:
        return JsonResponse({"ok": True, "state": "idle"})
    out = {"ok": True, "state": job["state"],
           "elapsed": job.get("elapsed", round(time.time() - job["at"], 1))}
    if job["state"] == "done":
        out["result"] = job["result"]
    elif job["state"] == "failed":
        out["error"] = job.get("error", "")
    return JsonResponse(out)
