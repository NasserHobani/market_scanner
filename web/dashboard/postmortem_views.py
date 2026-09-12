# -*- coding: utf-8 -*-
"""واجهة تشريح الصفقات المحسومة.

═══ لماذا نقطتان لا واحدة ═══

القياس يستغرق أجزاء من الثانية؛ ونداء النموذج المحلّي بلغ **116 ثانية**
وسيطاً في هذا المشروع. فدمجهما في نداء واحد يعني صفحة معلَّقة دقيقتين،
وهو العطب الذي أصاب صفحة البتكوين قبلُ.

فالفصل:

    ``/api/postmortem/``          قياس فوري — الأرقام تظهر حالاً
    ``/api/postmortem/ai/``       يبدأ التفسير ويعود فوراً
    ``/api/postmortem/ai/status/`` يُستعلَم حتى ينتهي

والأرقام تُعرَض أوّلاً دائماً. التفسير يأتي بعدها ولا يحلّ محلّها: إن
تعارضا فالأرقام هي الحقيقة.
"""
from __future__ import annotations

import threading
import time

from .jsonsafe import JsonResponse, dumps as json_safe_dumps
from django.views.decorators.http import require_POST

# مهمّة واحدة في كل وقت: التفسير يقرأ كل الصفقات المحسومة، وتشغيل
# نسختين معاً يضاعف الحمل بلا فائدة — النتيجة واحدة.
_JOB: dict = {"state": "idle", "started": 0.0, "result": None,
              "error": "", "elapsed": 0.0, "scope": ""}
_JOB_LOCK = threading.Lock()


def _resolve_provider():
    """المزوّد كما يحلّه المحرّك — من السجلّ لا من مصنع خاصّ.

    ═══ لماذا السجلّ ═══

    كتبتُ أوّلاً ``provider_factory.get_provider`` وهي **غير موجودة**:
    الملفّ يُصدّر ``create_claude_provider`` و``create_ollama_provider``
    فقط. فسقط الطلب وقت التشغيل برسالة استيراد.

    والمسار الصحيح هو ``get_registry().get(id)`` — وهو ما يستعمله
    ``AdvisorEngine`` نفسه. والالتزام به ليس تجميلاً: السجلّ يطبّق
    الارتداد المعرَّف مركزياً (‏mock ← المزوّد الفعّال)، فمسارٌ يلتفّ
    عليه يتصرّف تصرّفاً مختلفاً عن بقيّة النظام في الحالات الحدّية.
    """
    from scanner.ai_advisor.provider_registry import get_registry
    from scanner.ai_local.config import load_local_config

    local = load_local_config()
    wanted = ("ollama" if (local.local_enabled and local.ollama_enabled)
              else "claude")
    registry = get_registry()
    try:
        return wanted, registry.get(wanted)
    except KeyError:
        from scanner.ai_advisor.provider_config import (
            effective_provider_id, load_config,
        )

        fallback = effective_provider_id(load_config())
        return fallback, registry.get(fallback)


def _filters(request) -> dict:
    return {
        "market": (request.GET.get("market") or request.POST.get("market") or "").strip(),
        "timeframe": (request.GET.get("tf") or request.POST.get("tf") or "").strip(),
        "source": (request.GET.get("source") or request.POST.get("source") or "").strip(),
        "since": (request.GET.get("since") or request.POST.get("since") or "").strip(),
    }


def _load(f: dict) -> list[dict]:
    """الصفقات المحسومة من قاعدة البيانات عبر ORM."""
    from .models import Trade

    qs = Trade.objects.filter(status__in=["won", "lost"])
    if f.get("market"):
        qs = qs.filter(market=f["market"])
    if f.get("timeframe"):
        qs = qs.filter(timeframe=f["timeframe"])
    if f.get("source"):
        qs = qs.filter(source=f["source"])
    if f.get("since"):
        qs = qs.filter(signal_at__gte=f["since"])
    return list(qs.values(
        "symbol", "market", "timeframe", "side", "source", "status",
        "score", "confidence", "rr", "grade", "entry", "stop", "target1",
        "action", "reasons", "factors", "r_multiple", "best_r", "worst_r",
        "bars_held",
    ))


def api_postmortem(request):
    """القياس وحده — سريع، بلا نموذج."""
    from django.db.utils import OperationalError, ProgrammingError

    from scanner.postmortem import analyze, render_report

    f = _filters(request)
    try:
        trades = _load(f)
    except (OperationalError, ProgrammingError) as exc:
        return JsonResponse({"ok": False,
                             "error": f"جدول الصفقات غير متاح: {str(exc)[:120]}"})

    rep = analyze(trades)
    return JsonResponse({
        "ok": True,
        "filters": f,
        "report": rep.to_dict(),
        "text": render_report(rep),
        # التفسير لا يُعرَض إلّا حين يوجد ما يُفسَّر: عاملٌ ثبت، أو
        # مجموعة تحمل إشارة. وإلّا فالزرّ نفسه إغراء بالسرد.
        "explainable": bool(rep.has_findings or rep.global_signal),
    })


@require_POST
def api_postmortem_ai(request):
    """يبدأ التفسير في الخلفية ويعود فوراً."""
    f = _filters(request)
    scope = "·".join(v for v in f.values() if v) or "الكل"

    with _JOB_LOCK:
        if _JOB["state"] == "running":
            return JsonResponse({
                "ok": True, "state": "running",
                "elapsed": round(time.time() - _JOB["started"]),
                "scope": _JOB.get("scope", ""),
                "reason": "تفسير جارٍ بالفعل",
            })
        _JOB.update(state="running", started=time.time(), result=None,
                    error="", elapsed=0.0, scope=scope)

    threading.Thread(target=_run, args=(f,), name="postmortem-ai",
                     daemon=True).start()
    return JsonResponse({"ok": True, "state": "running", "scope": scope,
                         "reason": "بدأ التفسير — قد يستغرق دقيقتين"})


def api_postmortem_ai_status(request):
    out = dict(_JOB)
    if out["state"] == "running":
        out["elapsed"] = round(time.time() - out["started"])
    out.pop("started", None)
    return JsonResponse({"ok": True, **out})


def _run(f: dict) -> None:
    started = time.time()
    try:
        from .concurrency import track

        with track("تشريح الصفقات (نموذج)", kind="llm"):
            result = _explain(f)
        with _JOB_LOCK:
            _JOB.update(state="done", result=result, error="",
                        elapsed=round(time.time() - started))
    except Exception as exc:  # noqa: BLE001
        with _JOB_LOCK:
            _JOB.update(state="failed", result=None, error=str(exc)[:250],
                        elapsed=round(time.time() - started))


def _explain(f: dict) -> dict:
    """يقيس ثمّ يفسّر — والتفسير مقيَّد بما ثبت."""
    import json

    from scanner.postmortem import analyze, build_prompt

    rep = analyze(_load(f))
    if not (rep.has_findings or rep.global_signal):
        # لا يُنادى النموذج أصلاً. طلبُ تفسير لفرقٍ لم يثبت هو الطريق
        # المباشر إلى سرد مقنع بلا أساس.
        return {"skipped": True, "report": rep.to_dict(),
                "reason": "لا فرق يتجاوز الضجيج — لا شيء يُفسَّر."}

    prompt = build_prompt(rep)

    from scanner.ai_advisor.prompt_builder import AdvisorPrompt

    provider_id, provider = _resolve_provider()

    # المزوّدون يستقبلون ``AdvisorPrompt`` لا نصّين. والالتزام بالعقد
    # الموحّد يعني أن Claude و Qwen يريان المدخل نفسه، فتبقى المقارنة
    # بينهما ذات معنى.
    scope = "·".join(v for v in f.values() if v) or "كل الصفقات"
    advisor_prompt = AdvisorPrompt(
        version="postmortem_v1",
        system_prompt=prompt["system_prompt"],
        user_prompt=prompt["user_prompt"],
        package_id=f"postmortem_{rep.n_total}",
        event_id=f"postmortem::{scope}",
        rules=["تفسير ما ثبت فقط", "لا سبب لعامل لم يجتز الدلالة"],
    )

    # المحادثة الحيّة: يرى المستخدم النموذج يعمل بدل انتظار صامت
    channel = None
    try:
        from scanner.ai_advisor import live_channel

        channel = live_channel
        channel.start(symbol="تشريح الصفقات", market=f.get("market", ""),
                      timeframe=f.get("timeframe", ""),
                      provider=provider_id,
                      model=getattr(provider, "model_name", lambda: "")(),
                      system=prompt["system_prompt"],
                      user=prompt["user_prompt"])
        channel.stage("يقرأ جدول الفروق")
    except Exception:  # noqa: BLE001
        channel = None

    parsed = provider.analyze(advisor_prompt, package=None)
    text = parsed if isinstance(parsed, str) else json_safe_dumps(
        parsed, ensure_ascii=False, indent=2)
    if isinstance(parsed, str):
        try:
            from scanner.ai_advisor.response_parser import ResponseParser

            parsed = ResponseParser().parse(parsed)
        except Exception:  # noqa: BLE001
            parsed = None

    if parsed:
        parsed = _enforce_grounding(parsed, rep)

    if channel:
        try:
            channel.append(text[:4000])
            channel.finish(answer=text[:4000])
        except Exception:  # noqa: BLE001
            pass

    return {
        "skipped": False,
        "provider": provider_id,
        "model": getattr(provider, "model_name", lambda: "")(),
        "report": rep.to_dict(),
        "analysis": parsed,
        "raw": text[:6000],
    }


def _enforce_grounding(parsed: dict, rep) -> dict:
    """يحذف أي سبب أُسند إلى عامل لم يثبت.

    ═══ لماذا خادميّاً لا بالتعليمات وحدها ═══

    الموجّه يقول للنموذج ألّا يُسند سبباً إلى مرشَّح لم يثبت. وهذا
    **تعليم لا إلزام** — والفرق بينهما هو الفرق بين لافتة وباب مقفل،
    كما في بوّابة الاحتمال الإحصائي.

    ومخالفةٌ هنا أخطر من مثيلتها في التحليل اللحظي: سببٌ منسوب إلى عامل
    لم يجتز الدلالة يبدو **مقيساً** لأنه جاء مع أرقام، فيُبنى عليه قرار
    استراتيجي طويل الأثر.
    """
    proven = {t.tag for t in rep.tags if t.significant}
    proven |= {f.field_name for f in rep.factors if f.significant}
    violations: list[str] = []

    for key in ("success_drivers", "failure_drivers"):
        kept = []
        for item in (parsed.get(key) or []):
            factor = str((item or {}).get("factor") or "").strip()
            # المطابقة بالاحتواء: النموذج قد يعيد صياغة اسم العامل
            if factor and any(p in factor or factor in p for p in proven):
                kept.append(item)
            elif factor:
                violations.append(f"{key}: «{factor}» لم يثبت")
        parsed[key] = kept

    if violations:
        parsed["grounding_violations"] = violations
        parsed.setdefault("what_not_to_conclude", []).append(
            "حُذفت أسباب أُسندت إلى عوامل لم تجتز الدلالة: "
            + "، ".join(v.split("«")[1].rstrip("» لم يثبت") for v in violations[:4])
        )
        if not parsed.get("success_drivers") and not parsed.get("failure_drivers"):
            parsed["verdict"] = "لا فروق تتجاوز الضجيج"
    return parsed


# ─────────────────────────────────────── فحص صفقة واحدة

# مهام مستقلّة لكل صفقة: قد تفحص صفقتين متتاليتين، وقفلٌ واحد يجعل
# الثانية تنتظر الأولى بلا سبب.
_TRADE_JOBS: dict[int, dict] = {}
_TRADE_LOCK = threading.Lock()
_MAX_TRADE_JOBS = 20


def _trade_card(trade_id: int):
    """بطاقة الصفقة مقابل إحصاءات مجموعتها."""
    from scanner.postmortem import analyze, build_card

    from .models import Trade

    t = Trade.objects.filter(pk=trade_id).values(
        "id", "symbol", "market", "timeframe", "side", "source", "status",
        "score", "confidence", "rr", "grade", "entry", "stop", "target1",
        "action", "reasons", "factors", "r_multiple", "best_r", "worst_r",
        "bars_held",
    ).first()
    if not t:
        return None, None

    # المقارنة تكون بمجموعة الصفقة نفسها (سوقها وفريمها) حين تكفي،
    # وإلّا بكل المحسومة. مقارنة صفقة كريبتو 15m بأسهم يومية تُضلّل.
    scoped = _load({"market": t["market"], "timeframe": t["timeframe"]})
    rep = analyze(scoped)
    if rep.n_total < 40:
        rep = analyze(_load({}))
    return t, build_card(t, rep)


def api_trade_card(request, trade_id: int):
    """البطاقة والنتيجة — فوري، بلا نموذج."""
    from scanner.postmortem import render_card

    t, card = _trade_card(int(trade_id))
    if not card:
        return JsonResponse({"ok": False, "error": "الصفقة غير موجودة"},
                            status=404)
    return JsonResponse({
        "ok": True,
        "card": card.to_dict(),
        # نصّ ما سيصل النموذج — يُعرَض ليرى المستخدم أن النتيجة محجوبة
        "prompt_preview": render_card(card),
        "settled": str(t.get("status")) in ("won", "lost"),
    })


@require_POST
def api_trade_review(request, trade_id: int):
    """يبدأ تقييم جودة القرار في الخلفية."""
    tid = int(trade_id)
    with _TRADE_LOCK:
        job = _TRADE_JOBS.get(tid)
        if job and job["state"] == "running":
            return JsonResponse({"ok": True, "state": "running",
                                 "elapsed": round(time.time() - job["started"]),
                                 "reason": "تقييم جارٍ لهذه الصفقة"})
        if len(_TRADE_JOBS) >= _MAX_TRADE_JOBS:
            done = [k for k, v in _TRADE_JOBS.items() if v["state"] != "running"]
            for k in done[:len(_TRADE_JOBS) - _MAX_TRADE_JOBS + 1]:
                _TRADE_JOBS.pop(k, None)
        _TRADE_JOBS[tid] = {"state": "running", "started": time.time(),
                            "result": None, "error": "", "elapsed": 0.0}

    threading.Thread(target=_run_trade, args=(tid,),
                     name=f"trade-review-{tid}", daemon=True).start()
    return JsonResponse({"ok": True, "state": "running",
                         "reason": "بدأ التقييم — النتيجة محجوبة عن النموذج"})


def api_trade_review_status(request, trade_id: int):
    job = _TRADE_JOBS.get(int(trade_id))
    if not job:
        return JsonResponse({"ok": True, "state": "idle"})
    out = dict(job)
    if out["state"] == "running":
        out["elapsed"] = round(time.time() - out["started"])
    out.pop("started", None)
    return JsonResponse({"ok": True, **out})


def _run_trade(tid: int) -> None:
    started = time.time()
    try:
        from .concurrency import track

        with track(f"تقييم صفقة {tid} (نموذج)", kind="llm"):
            result = _review_trade(tid)
        state, error = "done", ""
    except Exception as exc:  # noqa: BLE001
        result, state, error = None, "failed", str(exc)[:250]
    with _TRADE_LOCK:
        _TRADE_JOBS[tid] = {"state": state, "started": started,
                            "result": result, "error": error,
                            "elapsed": round(time.time() - started)}


def _review_trade(tid: int) -> dict:
    """يقيّم جودة القرار، ثمّ يقابلها بالنتيجة — بهذا الترتيب.

    الترتيب هو الميزة: لو رأى النموذج النتيجة لبنى إليها سرداً. وبحجبها
    يصير حكمه قابلاً للمقابلة — ومن المقابلة تظهر الحالة التي لا يراها
    أحد: قرار ضعيف نجح.
    """
    import json

    from scanner.postmortem import (
        build_single_prompt, render_card, verdict_vs_outcome,
    )

    t, card = _trade_card(tid)
    if not card:
        raise ValueError("الصفقة غير موجودة")

    prompt = build_single_prompt(card)

    # حاجز قبل الإرسال: لو تسرّبت النتيجة إلى النصّ لفسدت الميزة كلّها
    leaked = _outcome_leak(prompt["user_prompt"], card.outcome)
    if leaked:
        raise ValueError(f"تسرّبت النتيجة إلى الموجّه: {leaked}")

    from scanner.ai_advisor.prompt_builder import AdvisorPrompt

    provider_id, provider = _resolve_provider()

    channel = None
    try:
        from scanner.ai_advisor import live_channel

        channel = live_channel
        channel.start(symbol=card.symbol, market=card.market,
                      timeframe=card.timeframe, provider=provider_id,
                      model=getattr(provider, "model_name", lambda: "")(),
                      system=prompt["system_prompt"],
                      user=prompt["user_prompt"])
        channel.stage("يقيّم جودة القرار — النتيجة محجوبة")
    except Exception:  # noqa: BLE001
        channel = None

    parsed = provider.analyze(AdvisorPrompt(
        version="trade_decision_v1",
        system_prompt=prompt["system_prompt"],
        user_prompt=prompt["user_prompt"],
        package_id=f"trade_{tid}",
        event_id=f"trade_review::{tid}",
        rules=["النتيجة محجوبة", "الحكم على القرار لا على ما آل إليه"],
    ), package=None)

    text = parsed if isinstance(parsed, str) else json_safe_dumps(
        parsed, ensure_ascii=False, indent=2)
    if isinstance(parsed, str):
        try:
            from scanner.ai_advisor.response_parser import ResponseParser

            parsed = ResponseParser().parse(parsed)
        except Exception:  # noqa: BLE001
            parsed = {}

    if channel:
        try:
            channel.append(text[:3000])
            channel.finish(answer=text[:3000])
        except Exception:  # noqa: BLE001
            pass

    quality = str((parsed or {}).get("decision_quality") or "غير كافٍ للحكم")
    status = str(card.outcome.get("status") or "")
    match = verdict_vs_outcome(quality, status) if status in ("won", "lost") else None

    return {
        "provider": provider_id,
        "model": getattr(provider, "model_name", lambda: "")(),
        "card": card.to_dict(),
        "assessment": parsed,
        "outcome": card.outcome,
        "match": match,
        "prompt_preview": render_card(card),
        "raw": text[:4000],
    }


def _outcome_leak(text: str, outcome: dict) -> str:
    """يكشف تسرّب النتيجة إلى نصّ الموجّه.

    فحص خادميّ لا اعتماد على انضباط البنية: حقلٌ يُضاف يوماً إلى
    ``render_card`` سهواً يُفسد الميزة صامتاً — والحاجز هنا يُسقط
    الطلب بدل أن يُنتج تقييماً ملوَّثاً يبدو سليماً.
    """
    low = text.lower()
    for word in ("won", "lost", "رابحة", "خاسرة", "r_multiple",
                 "best_r", "worst_r", "النتيجة:"):
        if word.lower() in low:
            return word
    for key, val in (outcome or {}).items():
        if val is None:
            continue
        token = f"{val:.4g}" if isinstance(val, float) else str(val)
        if len(token) >= 3 and token in text:
            return f"{key}={token}"
    return ""
