# -*- coding: utf-8 -*-
"""صفحة البتكوين — تحليل النظام والتوقّع، مع حكم صريح على صلاحيته.

طبقة عرض رقيقة عمداً: كل الحساب في ``scanner.btc``، وهذا الملف يترجم
إلى قاموس القالب. والقاعدة التي تعلّمناها بالخطأ مرّتين محفوظة هنا:
**لا نداء شبكة داخل رسم الصفحة**. رأي Ollama يُقرأ من آخر ما سُجِّل،
ويُطلب الجديد بزرّ صريح عبر نقطة طرفية منفصلة.
"""
from __future__ import annotations

import logging
import time

from .jsonsafe import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

log = logging.getLogger(__name__)

SYMBOL = "BTCUSDT"
MARKET = "crypto"

# التقرير مكلف (تدريب متدحرج على آلاف الشموع) والصفحة تُفتح كثيراً
_CACHE: dict = {}
_TTL = 600.0


def _load(tf: str):
    from scanner import storage

    return storage.load(MARKET, SYMBOL, tf)


def _report(force: bool = False) -> dict:
    hit = _CACHE.get("report")
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return hit[1]
    from scanner.btc import report as btc_report

    try:
        rep = btc_report.build_all(_load)
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر بناء تقرير البتكوين: %s", str(exc)[:160])
        rep = {"states": {}, "models": {}, "consensus": {}, "error": str(exc)[:200]}
    _CACHE["report"] = (time.time(), rep)
    return rep


# ═══════════════════════════════════════════════════════════════
#  السياق: التموضع · الأحداث · الأخبار
# ═══════════════════════════════════════════════════════════════
#
# ═══ ولماذا نقطةٌ منفصلة ═══
#
# ثلاثةُ مصادرَ شبكية: مشتقّات Binance، وارتفاع الكتلة، وتغذيات
# RSS. ووضعُها في رسم الصفحة يعني صفحةً تنتظر ثلاث شبكاتٍ قبل أن
# تُظهر شمعةً واحدة — والقاعدة المكتوبة أعلى هذا الملفّ تمنعه.
#
# فتصل الصفحة أوّلاً، ويصل السياق بعدها.

_CTX_TTL = 300.0


def _context_payload() -> dict:
    from scanner.analysis import events as ev
    from scanner.analysis import positioning as pos

    out: dict = {}

    # كلٌّ في ``try`` منفصل: فشلُ التغذيات لا يُخفي التموضع.
    # ومصدرٌ واحد معطوب كان سيبتلع الثلاثة.
    try:
        out["positioning"] = pos.read(SYMBOL)
    except Exception as exc:  # noqa: BLE001
        out["positioning"] = {"ok": False, "state": "unknown",
                              "why": str(exc)[:120]}
    try:
        out["events"] = ev.upcoming(45)
        out["calendar"] = ev.calendar_health()
    except Exception as exc:  # noqa: BLE001
        out["events"] = []
        out["calendar"] = {"ok": False, "why": str(exc)[:120]}
    try:
        from scanner.analysis.context import fetch_headlines

        items, err = fetch_headlines(MARKET, limit=8)
        out["headlines"] = items
        out["news_error"] = err
    except Exception as exc:  # noqa: BLE001
        out["headlines"] = []
        out["news_error"] = str(exc)[:120]

    # ═══ والعناوين لا تُحلَّل ═══
    #
    # لا وسمَ «إيجابي/سلبي» هنا. وسمُ العناوين برأي نموذج لغة يبدو
    # تحليلاً وهو تخمين، ولم يُقَس أثره على أيّ صفقة في هذه
    # المنصّة. فتبقى قراءةً للإنسان.
    out["news_note"] = "العناوين للقراءة — لا تدخل أيّ حساب ولا تُوسَم"
    return out


def api_btc_context(request):
    """التموضع والأحداث والعناوين — نداءٌ واحد، مخبّأ."""
    hit = _CACHE.get("context")
    if hit and (time.time() - hit[0]) < _CTX_TTL:
        return JsonResponse({"ok": True, "cached": True, **hit[1]})
    data = _context_payload()
    _CACHE["context"] = (time.time(), data)
    return JsonResponse({"ok": True, "cached": False, **data})


def _last_opinion() -> dict:
    """آخر رأي مسجَّل للنموذج المحلي عن البتكوين — من القرص، بلا شبكة."""
    import json
    from pathlib import Path

    from django.conf import settings as dj

    root = getattr(dj, "BASE_DIR", Path("."))
    for name in ("data/local_ai_history.jsonl", "data/advisor_history.jsonl"):
        path = Path(root) / name
        if not path.exists():
            continue
        try:
            rows = [json.loads(x) for x in
                    path.read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception:  # noqa: BLE001
            continue
        for r in reversed(rows):
            if str(r.get("symbol", "")).upper().startswith("BTC"):
                return r
    return {}


CHART_TIMEFRAMES = ("15m", "1h", "4h", "1d")
DEFAULT_TF = "4h"


def btc_page(request):
    rep = _report(force=request.GET.get("refresh") == "1")
    tf = request.GET.get("tf")
    if tf not in CHART_TIMEFRAMES:
        tf = DEFAULT_TF
    # حكم النموذج يُرسل إلى الواجهة مع الشارت: القراءة الفنّية وحدها
    # تُغري بقرار، ووجود «هذا الفريم لم يتجاوز خطّ الأساس» بجانبها هو
    # ما يمنع ذلك
    verdicts = {
        k: {"usable": bool(v.get("usable")),
            "accuracy": v.get("accuracy"),
            "baseline": v.get("best_baseline_value"),
            "prob_up": (v.get("now") or {}).get("prob_up")}
        for k, v in (rep.get("models") or {}).items() if v.get("valid")
    }
    return render(request, "dashboard/btc.html", {
        "nav_page": "btc",
        "show_market_chips": False,
        "market": MARKET,
        "symbol": SYMBOL,
        "chart_timeframes": CHART_TIMEFRAMES,
        "chart_tf": tf,
        "chart_config": {"market": MARKET, "symbol": SYMBOL,
                         "timeframe": tf, "verdicts": verdicts},
        "states": rep.get("states", {}),
        "models": rep.get("models", {}),
        "consensus": rep.get("consensus", {}),
        "error": rep.get("error", ""),
        "opinion": _last_opinion(),
        "payload": {"countdown": None},
    })


# ── مهمة الرأي: تبدأ وتُستعلَم، ولا تُنتظَر ──
#
# العطب الذي عولج: كانت النقطة تُشغّل النموذج **داخل الطلب**. وقياس
# 54 مراجعة أعطى وسيطاً **116 ثانية** وأقصى 177، ومع ``ai_retry_count``
# = 2 و``ai_timeout`` = 300 يبلغ أسوأ انتظار **تسعمئة ثانية**. المتصفّح
# والخادم الوسيط يستسلمان قبلها بكثير، فيظهر «بطيء أو معلّق وغالباً
# بلا نتيجة» — وهي ليست مشكلة النموذج بل شكل الاستدعاء.
#
# نمط ابدأ/استعلم هو ما يستعمله المسح في هذا المشروع أصلاً.
_JOB: dict = {"state": "idle", "started": 0.0, "result": None,
              "error": "", "elapsed": 0.0}
_JOB_LOCK = None


def _job_lock():
    global _JOB_LOCK
    if _JOB_LOCK is None:
        import threading

        _JOB_LOCK = threading.Lock()
    return _JOB_LOCK


@require_POST
def api_btc_opinion(request):
    """يبدأ مراجعة في الخلفية ويعود فوراً. النتيجة عبر ``/status/``."""
    import threading

    with _job_lock():
        if _JOB["state"] == "running":
            return JsonResponse({"ok": True, "state": "running",
                                 "elapsed": round(time.time()
                                                  - _JOB["started"]),
                                 "reason": "مراجعة جارية بالفعل"})
        _JOB.update(state="running", started=time.time(), result=None,
                    error="", elapsed=0.0)

    threading.Thread(target=_run_opinion, name="btc-opinion",
                     daemon=True).start()
    return JsonResponse({"ok": True, "state": "running",
                         "reason": "بدأت المراجعة — قد تستغرق دقيقتين"})


def api_btc_opinion_status(request):
    """حالة المراجعة الجارية أو نتيجة آخر واحدة."""
    out = dict(_JOB)
    if out["state"] == "running":
        out["elapsed"] = round(time.time() - out["started"])
    out.pop("started", None)
    return JsonResponse({"ok": True, **out})


def _run_opinion() -> None:
    started = time.time()
    try:
        result = _request_opinion()
        with _job_lock():
            _JOB.update(state="done", result=result, error="",
                        elapsed=round(time.time() - started))
    except Exception as exc:  # noqa: BLE001
        with _job_lock():
            _JOB.update(state="failed", result=None,
                        error=str(exc)[:200],
                        elapsed=round(time.time() - started))


def _request_opinion() -> dict:
    try:
        from scanner.ai_advisor.runtime import review_recommendation
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("وحدة المستشار غير متاحة") from exc
    rep = _report()
    state = rep.get("states", {}).get("4h", {})
    model = rep.get("models", {}).get("4h", {})
    if True:
        # يُمرَّر حكم القياس مع الحالة: النموذج يجب أن يعرف أن توقّع
        # الاتجاه صالح أو غير صالح، وإلّا بنى رأيه على رقم مرفوض
        out = review_recommendation(
            symbol=SYMBOL, market=MARKET, timeframe="4h",
            recommendation={
                "action": "analysis",
                "headline": "تحليل نظام البتكوين",
                "trend": state.get("trend"),
                "model_valid": bool(model.get("usable")),
                "model_accuracy": model.get("accuracy"),
                "model_baseline": model.get("best_baseline_value"),
            },
            row={k: v for k, v in (state.get("features") or {}).items()
                 if v is not None},
        )
        return out or {}
    return {}


@require_POST
def api_btc_refresh(request):
    _CACHE.pop("report", None)
    rep = _report(force=True)
    return JsonResponse({"ok": True, "models": rep.get("models", {}),
                         "consensus": rep.get("consensus", {})})
