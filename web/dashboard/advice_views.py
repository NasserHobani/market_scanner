# -*- coding: utf-8 -*-
"""نقطتا الاستشارة — «لماذا خسرت؟» و«هل أدخل؟».

═══ ما استُبدل ═══

كان المستشار يُنتج ستّة وثلاثين حقلاً، منها أربعة **فارغة في
١٠٠٪** من ١٦٤ مراجعة — وهي وحدها التي تتطلّب رقماً أو موقفاً.
ولم يقل «اشترِ» ولا مرّة، ولم يعطِ سعراً واحداً في شرط إبطال.

والآن خمسة حقول، وكل رقمٍ فيها من سجلّ صفقاتك، والمخرَج الذي لا
يُفحَص يُرفَض ويُقال سببه.
"""
from __future__ import annotations

import logging
import threading

from django.views.decorators.http import require_GET, require_POST

from . import jobs
from .jsonsafe import JsonResponse
from .models import Trade

log = logging.getLogger("dashboard.advice")

# ═══ حقول الدخول وحدها ═══
#
# ``r_multiple`` و ``status`` يدخلان لأنّ **السكّان** يحتاجونهما
# لحساب معدّل الفوز. أمّا الصفقة المفحوصة فتُبنى حزمتها من حقول
# الدخول فقط — انظر ``evidence.ENTRY_TRAITS``.
_FIELDS = ("id", "symbol", "market", "timeframe", "side", "status",
           "r_multiple", "score", "rr", "grade", "source", "action",
           "confidence", "entry_price", "stop", "target1")


def _population() -> list[dict]:
    """كل الصفقات المحسومة — أساس كل نسبة تُذكَر.

    تُقرأ كاملةً لا مقصوصة: معدّل الأساس يجب أن يكون على السجلّ
    كلّه، وإلّا صار «الفارق عن الأساس» فارقاً عن عيّنةٍ اعتباطية.
    """
    have = {f.name for f in Trade._meta.get_fields() if hasattr(f, "name")}
    cols = [c for c in _FIELDS if c in have]
    return list(Trade.objects.filter(status__in=("won", "lost"))
                .values(*cols))


def _one(trade_id: int) -> dict | None:
    have = {f.name for f in Trade._meta.get_fields() if hasattr(f, "name")}
    cols = [c for c in _FIELDS if c in have]
    return Trade.objects.filter(pk=trade_id).values(*cols).first()


# ═══════════════════ لماذا فازت / لماذا خسرت ═══════════════════

def _run_settled(trade_id: int, provider_id: str) -> None:
    from scanner.ai_advisor.advise import advise_settled

    trade = _one(trade_id)
    if not trade:
        jobs.finish("advice", "الصفقة غير موجودة", "لا صفقة بهذا الرقم")
        return
    if trade.get("status") not in ("won", "lost"):
        jobs.finish("advice", "الصفقة غير محسومة",
                    "التشريح لا يجري إلّا على صفقة انتهت")
        return

    pop = _population()
    jobs.step("advice", f"يحلّل {trade.get('symbol')} على {len(pop)} صفقة")
    adv = advise_settled(trade, pop, provider_id=provider_id)
    jobs.finish("advice",
                adv.verdict.arabic() if adv.accepted
                else f"رُفض: {adv.verdict.rejected_because}")
    _RESULT["settled"] = adv.as_dict()


def _run_prospective(setup: dict, provider_id: str) -> None:
    from scanner.ai_advisor.advise import advise_prospective

    pop = _population()
    jobs.step("advice", f"يحلّل {setup.get('symbol')} على {len(pop)} صفقة")
    adv = advise_prospective(setup, pop, provider_id=provider_id)
    jobs.finish("advice",
                adv.verdict.arabic() if adv.accepted
                else f"رُفض: {adv.verdict.rejected_because}")
    _RESULT["prospective"] = adv.as_dict()


# آخر نتيجة لكل نوع — تُقرأ مع حالة المهمّة
_RESULT: dict[str, dict] = {}


@require_POST
def api_advice_settled(request):
    """«لماذا انتهت هذه الصفقة كما انتهت؟»"""
    try:
        trade_id = int(request.POST.get("trade_id") or 0)
    except (TypeError, ValueError):
        trade_id = 0
    if not trade_id:
        return JsonResponse({"ok": False, "reason": "رقم صفقة غير صالح"},
                            status=400)
    provider = (request.POST.get("provider") or "ollama").strip()

    if not jobs.begin("advice", scope=f"settled:{trade_id}", total=1,
                      note="يبدأ…"):
        return JsonResponse({"ok": True, "already": True,
                             **jobs.snapshot("advice")})
    _RESULT.pop("settled", None)
    jobs.run_in_thread("advice", _run_settled, trade_id, provider,
                       name="advice-settled")
    return JsonResponse({"ok": True, **jobs.snapshot("advice")})


@require_POST
def api_advice_prospective(request):
    """«هل أدخل هذه الصفقة؟»"""
    def _num(key):
        try:
            return float(request.POST.get(key))
        except (TypeError, ValueError):
            return None

    setup = {
        "symbol": (request.POST.get("symbol") or "").strip(),
        "market": (request.POST.get("market") or "").strip(),
        "timeframe": (request.POST.get("timeframe") or "").strip(),
        "side": (request.POST.get("side") or "buy").strip(),
        "action": (request.POST.get("action") or "").strip(),
        "grade": (request.POST.get("grade") or "").strip(),
        "source": (request.POST.get("source") or "auto").strip(),
        "score": _num("score"), "rr": _num("rr"),
        "confidence": _num("confidence"),
        "entry": _num("entry"), "stop": _num("stop"),
        "target1": _num("target1"), "close": _num("close"),
    }
    if not setup["symbol"]:
        return JsonResponse({"ok": False, "reason": "بلا رمز"}, status=400)
    provider = (request.POST.get("provider") or "ollama").strip()

    if not jobs.begin("advice", scope=f"prospective:{setup['symbol']}",
                      total=1, note="يبدأ…"):
        return JsonResponse({"ok": True, "already": True,
                             **jobs.snapshot("advice")})
    _RESULT.pop("prospective", None)
    jobs.run_in_thread("advice", _run_prospective, setup, provider,
                       name="advice-prospective")
    return JsonResponse({"ok": True, **jobs.snapshot("advice")})


@require_GET
def api_advice_status(request):
    """حالة الاستشارة ونتيجتها إن اكتملت."""
    snap = jobs.snapshot("advice")
    kind = ""
    scope = snap.get("scope") or ""
    if scope.startswith("settled"):
        kind = "settled"
    elif scope.startswith("prospective"):
        kind = "prospective"
    return JsonResponse({"ok": True, "job": snap,
                         "result": _RESULT.get(kind)})


@require_GET
def api_advice_evidence(request):
    """الأدلّة وحدها — بلا نموذج.

    ═══ لماذا نقطةٌ مستقلّة ═══

    الأرقام محسوبة من سجلّك ولا تحتاج نموذجاً لغويّاً. فمن أراد
    «كم فازت إعدادات كهذه؟» يأخذها فوراً وبلا انتظار — والنموذج
    يُستدعى حين يُراد **حكم**، لا حين يُراد رقم.

    وهذا يجعل عطل النموذج لا يحجب البيانات.
    """
    from scanner.ai_advisor import evidence as ev

    kind = (request.GET.get("kind") or "prospective").strip()
    pop = _population()
    if kind == "settled":
        try:
            tid = int(request.GET.get("trade_id") or 0)
        except (TypeError, ValueError):
            tid = 0
        trade = _one(tid)
        if not trade:
            return JsonResponse({"ok": False, "reason": "لا صفقة"},
                                status=404)
        pack = ev.for_settled(trade, pop)
    else:
        def _num(key):
            try:
                return float(request.GET.get(key))
            except (TypeError, ValueError):
                return None
        pack = ev.for_prospective({
            "symbol": request.GET.get("symbol") or "",
            "market": request.GET.get("market") or "",
            "timeframe": request.GET.get("timeframe") or "",
            "grade": request.GET.get("grade") or "",
            "action": request.GET.get("action") or "",
            "source": request.GET.get("source") or "auto",
            "score": _num("score"), "rr": _num("rr"),
            "entry": _num("entry"), "stop": _num("stop"),
            "target1": _num("target1"), "close": _num("close"),
        }, pop)

    r = pack.rate
    return JsonResponse({
        "ok": True, "kind": kind, "symbol": pack.symbol,
        "population": len(pop),
        "evidence": pack.as_prompt_block(),
        "note": pack.note,
        "rate": (None if r is None else
                 {"wins": r.wins, "total": r.total,
                  "pct": round(r.pct, 1), "low": round(100 * r.low),
                  "high": round(100 * r.high),
                  "baseline": round(r.baseline * 100),
                  "readable": r.readable, "significant": r.significant,
                  "arabic": r.arabic()}),
        "causes": [{"trait": c.trait, "arabic": c.arabic(),
                    "edge": round(c.rate.edge, 1)} for c in pack.causes],
        "why": _why_json(pack.why),
    })


def _why_json(w) -> dict | None:
    """«لماذا قد تنجح» — أسباب الإشارة بدرجة إسناد كلٍّ منها."""
    if w is None:
        return None

    def one(r):
        rt = r.rate
        return {
            "text": r.text, "strength": r.strength,
            "arabic": r.arabic(), "proven": r.survives_fdr,
            "wins": None if rt is None else rt.wins,
            "total": None if rt is None else rt.total,
            "pct": None if (rt is None or not rt.readable)
                   else round(rt.pct),
            "edge": None if (rt is None or not rt.readable)
                    else round(rt.edge),
            "low": None if (rt is None or not rt.readable)
                   else round(100 * rt.low),
            "high": None if (rt is None or not rt.readable)
                    else round(100 * rt.high),
        }

    return {
        "headline": w.headline(),
        "tested": w.tested, "survived": w.survived,
        "supporting": [one(r) for r in w.supporting],
        "opposing": [one(r) for r in w.opposing],
        "untested": [one(r) for r in w.untested],
    }


# ═══════════════════ سجلّ الأحكام التلقائية ═══════════════════

@require_GET
def api_verdicts_list(request):
    """أحكام المستشار — والمرفوض منها معروضٌ بسببه.

    ═══ ولماذا يُعرض المرفوض ═══

    المسار القديم كان يُسقط المخرَج المرفوض صامتاً، فيبدو السجلّ
    نظيفاً وهو ناقص. ومعدّل الرفض أصدق مقياسٍ لصلاحية النموذج
    للمهمّة — إخفاؤه يخفي العطب لا يصلحه.
    """
    from scanner.ai_advisor import verdict_store

    try:
        page = max(1, int(request.GET.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        size = min(100, max(1, int(request.GET.get("page_size") or 25)))
    except (TypeError, ValueError):
        size = 25

    q = (request.GET.get("q") or "").strip().lower()
    decision = (request.GET.get("decision") or "").strip()
    market = (request.GET.get("market") or "").strip()

    recs = verdict_store.load_all()
    if q:
        recs = [r for r in recs
                if q in str(r.get("symbol", "")).lower()
                or q in str(r.get("market", "")).lower()]
    if market:
        recs = [r for r in recs if r.get("market") == market]
    if decision == "مرفوض":
        recs = [r for r in recs if not r.get("accepted")]
    elif decision:
        recs = [r for r in recs
                if (r.get("fields") or {}).get("القرار") == decision]

    total = len(recs)
    start = (page - 1) * size
    return JsonResponse({
        "ok": True, "total": total, "page": page, "page_size": size,
        "pages": max(1, (total + size - 1) // size),
        "stats": verdict_store.stats(),
        "items": recs[start:start + size],
    })


@require_GET
def api_verdict_detail(request, verdict_id: str):
    from scanner.ai_advisor import verdict_store

    rec = verdict_store.get(verdict_id)
    if not rec:
        return JsonResponse({"ok": False, "reason": "لا حكم بهذا المعرّف"},
                            status=404)
    return JsonResponse({"ok": True, "verdict": rec})
