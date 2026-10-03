# -*- coding: utf-8 -*-
"""نداء Together — بزرٍّ صريح، وبتكلفةٍ معروضة قبل الضغط وبعده.

═══ لماذا نقطةٌ مستقلّة ═══

بقيّة المزوّدين تُنادى من محرّك المستشار بسياقٍ مبنيّ. وهذا
يُنادى **لحظةَ يطلبه المستخدم** على ما يراه أمامه — فلا يمرّ
بمسار الارتداد الذي قد يختاره تلقائياً.

═══ ولا نداءَ من جدولة ═══

لا يُستورَد هذا الملفّ في ``cron.py`` ولا في أيّ معالج مهمّة،
وفحصٌ بنيويّ يمنع ذلك. «لن أناديه في حلقة» نيّةٌ يكسرها سطرٌ
واحد بعد أشهر.
"""
from __future__ import annotations

import logging
import threading
import time

from django.views.decorators.http import require_GET, require_POST

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.together")

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_TTL = 900.0

#: ما يُسمح بسؤاله — ولا نصَّ حرّ من المتصفّح
PURPOSES = {
    "symbol": "قراءة رمزٍ واحد",
    "trade": "مراجعة صفقة",
    "study": "تفسير دراسة رمز",
}

SYSTEM_AR = """\
أنت محلّل كمّي في منصّة CS Edge. تقرأ أرقاماً محسوبة وتشرحها.
لا تخترع رقماً لم يُعطَ لك، ولا تتنبّأ بسعر، ولا توصي بشراءٍ أو بيع.
وإن كانت البيانات لا تكفي لحكمٍ فقل ذلك صراحةً.
المنصّة استشارية: قرار التنفيذ لصاحبها وحده.
تكتب بالعربية المهنية وتُخرج JSON صالحاً فقط بالحقول المطلوبة."""


@require_GET
def api_together_health(request):
    """حال المفتاح والإنفاق — يُقرأ بلا أيّ نداءٍ مدفوع."""
    from scanner.ai_advisor import spend
    from scanner.ai_advisor.providers import together_provider as tp

    return JsonResponse({
        "ok": True,
        "configured": tp.configured(),
        "model": tp.model_id(),
        "spend": spend.summary(),
        "why": "" if tp.configured() else (
            "مفتاح Together غير مضبوط. أنشئه من api.together.ai ← "
            "Settings ← API Keys، وأضفه في بورتينر ← Environment "
            "variables: TOGETHER_API_KEY."),
    })


def _run(key: str, system: str, user: str, purpose: str,
         max_tokens: int) -> None:
    from scanner.ai_advisor import spend
    from scanner.ai_advisor.providers import together_provider as tp

    started = time.time()
    try:
        out = tp.TogetherProvider().complete(
            system, user, purpose=purpose, max_tokens=max_tokens)
        with _LOCK:
            _JOBS[key] = {"state": "done", "result": out,
                          "elapsed": round(time.time() - started, 1),
                          "at": time.time()}
    except spend.BudgetExceeded as exc:
        with _LOCK:
            _JOBS[key] = {"state": "budget", "error": str(exc),
                          "at": time.time(),
                          "elapsed": round(time.time() - started, 1)}
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر نداء Together: %s", str(exc)[:160])
        with _LOCK:
            _JOBS[key] = {"state": "failed", "error": str(exc)[:240],
                          "at": time.time(),
                          "elapsed": round(time.time() - started, 1)}


@require_POST
def api_together_ask(request):
    """يبدأ نداءً واحداً في الخلفية ويعود فوراً.

    النموذج قد يستغرق عشرات الثواني، وانتظارُه داخل الطلب يُجمّد
    عاملاً من ثلاثة.
    """
    from scanner.ai_advisor import spend
    from scanner.ai_advisor.providers import together_provider as tp

    if not tp.configured():
        return JsonResponse(
            {"ok": False, "reason": "مفتاح Together غير مضبوط"}, status=400)

    purpose = (request.POST.get("purpose") or "").strip()
    if purpose not in PURPOSES:
        return JsonResponse({"ok": False, "reason": "غرض غير معروف"},
                            status=400)

    payload = (request.POST.get("payload") or "").strip()
    # ═══ حدٌّ على المُدخَل ═══
    #
    # الوحدات تُحسَب بالطول، فنصٌّ طويل = فاتورةٌ كبيرة. والسقف
    # الماليّ يمنعها بعد ذلك، وهذا يمنعها قبله برسالةٍ أوضح.
    if not payload:
        return JsonResponse({"ok": False, "reason": "لا بيانات"}, status=400)
    if len(payload) > 24000:
        return JsonResponse(
            {"ok": False,
             "reason": f"المُرسَل {len(payload)} حرفاً — والحدّ ٢٤٬٠٠٠. "
                       "قلّل ما تُرسله."}, status=400)

    try:
        max_tokens = max(200, min(2000, int(request.POST.get("max") or 1200)))
    except (TypeError, ValueError):
        max_tokens = 1200

    key = f"{purpose}|{abs(hash(payload)) % 10**9}"
    with _LOCK:
        job = _JOBS.get(key)
        if job and job["state"] == "running":
            return JsonResponse({"ok": True, "state": "running", "key": key})
        now = time.time()
        for k in [k for k, v in _JOBS.items()
                  if v.get("state") != "running"
                  and now - v.get("at", now) > _TTL]:
            _JOBS.pop(k, None)
        # ═══ نداءٌ واحد في وقتٍ واحد ═══
        #
        # كلّ نداءٍ يُنفَق. والتوازي يضاعف الفاتورة على ضغطتين
        # متتاليتين بلا أن يُقصَد.
        if any(v["state"] == "running" for v in _JOBS.values()):
            return JsonResponse(
                {"ok": False, "reason": "نداءٌ جارٍ — انتظره. "
                                        "كلّ نداءٍ يُنفَق."}, status=429)
        _JOBS[key] = {"state": "running", "at": time.time()}

    user = f"الغرض: {PURPOSES[purpose]}\n\nالبيانات:\n{payload}"
    threading.Thread(target=_run,
                     args=(key, SYSTEM_AR, user, purpose, max_tokens),
                     name=f"together-{purpose}", daemon=True).start()

    # تقديرٌ قبليّ يُعرَض فوراً — كي يُرى الثمن قبل النتيجة
    est_in = tp._rough_tokens(SYSTEM_AR) + tp._rough_tokens(user)
    return JsonResponse({
        "ok": True, "state": "running", "key": key,
        "estimate_usd": spend.estimate_cost(tp.model_id(), est_in, max_tokens),
    })


@require_GET
def api_together_status(request):
    from scanner.ai_advisor import spend

    key = (request.GET.get("key") or "").strip()
    job = _JOBS.get(key)
    if not job:
        return JsonResponse({"ok": True, "state": "idle"})
    out = {"ok": True, "state": job["state"],
           "elapsed": job.get("elapsed",
                              round(time.time() - job["at"], 1)),
           "spend": spend.summary()}
    if job["state"] == "done":
        out["result"] = job["result"]
    elif job["state"] in ("failed", "budget"):
        out["error"] = job.get("error", "")
    return JsonResponse(out)
