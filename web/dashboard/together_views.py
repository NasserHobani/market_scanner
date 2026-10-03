# -*- coding: utf-8 -*-
"""نداء Together — بزرٍّ صريح، وبتكلفةٍ معروضة قبل الضغط وبعده.

═══ العطب الذي عولج ═══

كانت المهامّ في قاموسٍ داخل العملية. و‏gunicorn يعمل بـ**ثلاثة
عمّال**: الطلب الذي يبدأ النداء يصل عاملاً، والاستعلام عن حاله
قد يصل عاملاً آخر لا يعرف المفتاح — فيردّ ``idle`` إلى الأبد.

فبدا الزرّ «لا يفعل شيئاً»: النداء يعمل فعلاً ويُنفَق، والنتيجة
تُحفَظ في ذاكرة عاملٍ لا يسأله أحد.

وهو العطب نفسه الذي عولج في الجدولة من قبل — «حاوية الويب وحاوية
المجدول ذاكرتان منفصلتان» — وأعدتُه هنا بين عمّال العملية الواحدة.

والعلاج: ملفٌّ في ``data/`` يراه الثلاثة. والوحدة مشتركة بينهم
بالبناء.

═══ ومفتاحٌ ثابت ═══

كان ``hash(payload)`` — و‏Python يُعشّي تجزئة النصوص لكل عملية
(‏PYTHONHASHSEED). فالمفتاح نفسه يختلف بين عاملٍ وآخر ولو وُجد
الملفّ. فصار ‎SHA-1‎: ثابتٌ عبر العمليات والإقلاعات.

═══ ولا نداءَ من جدولة ═══

لا يُستورَد هذا الملفّ في ``cron.py`` ولا في أيّ معالج مهمّة،
وفحصٌ بنيويّ يمنع ذلك.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path

from django.views.decorators.http import require_GET, require_POST

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.together")

#: عمر المهمّة على القرص
_TTL = 1800.0
_LOCK = threading.Lock()

#: ما يُسمح بسؤاله — ولا نصَّ حرّ من المتصفّح
PURPOSES = {
    "symbol": "قراءة رمزٍ واحد",
    "trade": "مراجعة صفقة",
    "study": "تفسير دراسة رمز",
}

# ═══ مخطَّطٌ ثابت ═══
#
# كان الطلب «‏JSON صالحاً» بلا حقولٍ محدّدة، فعاد النموذج بحقولٍ
# يخترعها في كل مرّة ونصوصٍ فيها ‎\n‎ و‏«•» داخل السطر الواحد.
# فتعذّر عرضُها إلّا خاماً — وهو ما ظهر على الشاشة.
#
# والمخطَّط هنا يجعل القوائم **مصفوفات**: كل بندٍ عنصر، فتُرسَم
# قائمةً نظيفة بلا أن تُفكَّك نصوصٌ بفواصل مخترَعة.
SYSTEM_AR = """\
أنت محلّل كمّي في منصّة CS Edge. تقرأ أرقاماً محسوبة وتشرحها.

قواعد ملزِمة:
- لا تخترع رقماً لم يُعطَ لك.
- لا تتنبّأ بسعر، ولا توصي بشراءٍ أو بيع، ولا تقترح وقفاً أو هدفاً.
- إن كانت البيانات لا تكفي لحكمٍ فقل ذلك في «ما_لا_نعرفه».
- المنصّة استشارية: قرار التنفيذ لصاحبها وحده.

أعِد JSON صالحاً بهذه الحقول **وحدها**:

{
  "الخلاصة": "فقرة واحدة، ثلاثة أسطر على الأكثر",
  "يدعم": ["بند", "بند"],
  "يضعف": ["بند", "بند"],
  "ما_لا_نعرفه": ["بند"]
}

كل بندٍ جملةٌ قصيرة مستقلّة. ولا تضع ‎\\n‎ ولا نقاطاً ولا شُرَطاً
داخل البنود — القائمة تتكفّل بذلك."""


# ═══════════════════════════════════════════════════════════════
#  حالة المهمّة — على القرص لا في الذاكرة
# ═══════════════════════════════════════════════════════════════

def _dir() -> Path:
    p = Path(__file__).resolve().parents[2] / "data" / "ai_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _key(purpose: str, payload: str) -> str:
    """مفتاحٌ ثابت عبر العمليات — ‎SHA-1‎ لا ``hash``."""
    h = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{purpose}-{h}"


def _file(key: str) -> Path:
    # اسمٌ آمن: المفتاح من ‎hexdigest‎ فلا يحمل فواصل مسار
    safe = "".join(ch for ch in key if ch.isalnum() or ch in "-_")[:48]
    return _dir() / f"{safe}.json"


def _read(key: str) -> dict | None:
    path = _file(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - float(data.get("at") or 0) > _TTL:
        return None
    return data


def _write(key: str, data: dict) -> None:
    """كتابةٌ ذرّية: مؤقّتٌ ثمّ استبدال.

    الكتابة المباشرة تترك ملفّاً نصفه مكتوب إن قُرئ في أثنائها —
    وثلاثة عمّالٍ يقرؤون في كل ثانيتين.
    """
    data = {**data, "at": time.time()}
    path = _file(key)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # noqa: BLE001
        log.warning("تعذّر حفظ حال المهمّة: %s", str(exc)[:90])


def _sweep() -> None:
    now = time.time()
    try:
        for f in _dir().glob("*.json"):
            if now - f.stat().st_mtime > _TTL:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _running_count() -> int:
    n = 0
    try:
        for f in _dir().glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if d.get("state") == "running" and \
                    time.time() - float(d.get("at") or 0) < 300:
                n += 1
    except OSError:
        pass
    return n


# ═══════════════════════════════════════════════════════════════
#  النقاط
# ═══════════════════════════════════════════════════════════════

@require_GET
def api_together_health(request):
    """حال المفتاح والإنفاق — يُقرأ بلا أيّ نداءٍ مدفوع."""
    from scanner.ai_advisor import spend
    from scanner.ai_advisor.providers import together_provider as tp

    # ═══ ولا يرمي ═══
    #
    # هذه أوّل ما تُنادى عند فتح الصفحة. وسقوطها يترك الشارة
    # بشرطاتٍ بلا سبب — وهو ما يبدو عطباً في كل شيء.
    try:
        s = spend.summary()
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر قراءة الإنفاق: %s", str(exc)[:120])
        s = {"today_usd": 0.0, "month_usd": 0.0,
             "limits": spend.limits(), "error": str(exc)[:120]}

    try:
        on = spend.enabled()
    except Exception:  # noqa: BLE001
        on = True

    return JsonResponse({
        "ok": True,
        "configured": tp.configured(),
        "enabled": on,
        "model": tp.model_id(),
        "spend": s,
        "why": "" if tp.configured() else (
            "مفتاح Together غير مضبوط. أنشئه من api.together.ai ← "
            "Settings ← API Keys، وأضفه في بورتينر ← Environment "
            "variables: TOGETHER_API_KEY.")
        if not tp.configured() else (
            "" if on else "النداء مُطفأ من الإعدادات ← «الذكاء المدفوع»"),
    })


def _run(key: str, system: str, user: str, purpose: str,
         max_tokens: int, subject: str = "") -> None:
    from scanner.ai_advisor import archive, spend
    from scanner.ai_advisor.providers import together_provider as tp

    started = time.time()
    try:
        out = tp.TogetherProvider().complete(
            system, user, purpose=purpose, max_tokens=max_tokens)
        # ═══ يُحفَظ قبل أن يُعرَض ═══
        #
        # إجابةٌ تُعرَض ثمّ تُفقَد بإغلاق التبويب تعني أنّك دفعت
        # مرّتين للسؤال نفسه — وهو نقيض «عند الطلب فقط».
        u = out.get("usage") or {}
        try:
            row = archive.save(
                subject=subject or purpose, purpose=purpose,
                model=out.get("model", ""), answer=out.get("text", ""),
                question=user, cost=u.get("cost", 0.0),
                tokens_in=u.get("tokens_in", 0),
                tokens_out=u.get("tokens_out", 0),
                latency_ms=out.get("latency_ms"))
            out = {**out, "archive_id": row["id"], "at": row["at"]}
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّرت أرشفة الإجابة: %s", str(exc)[:120])
        _write(key, {"state": "done", "result": out,
                     "elapsed": round(time.time() - started, 1)})
    except spend.BudgetExceeded as exc:
        _write(key, {"state": "budget", "error": str(exc),
                     "elapsed": round(time.time() - started, 1)})
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّر نداء Together: %s", str(exc)[:200])
        _write(key, {"state": "failed", "error": str(exc)[:300],
                     "elapsed": round(time.time() - started, 1)})


@require_POST
def api_together_ask(request):
    """يبدأ نداءً واحداً في الخلفية ويعود فوراً."""
    from scanner.ai_advisor import spend
    from scanner.ai_advisor.providers import together_provider as tp

    if not tp.configured():
        return JsonResponse(
            {"ok": False, "reason": "مفتاح Together غير مضبوط"}, status=400)
    if not spend.enabled():
        return JsonResponse(
            {"ok": False,
             "reason": "النداء المدفوع مُطفأ من الإعدادات ← "
                       "«الذكاء المدفوع»."}, status=400)

    purpose = (request.POST.get("purpose") or "").strip()
    if purpose not in PURPOSES:
        return JsonResponse({"ok": False, "reason": "غرض غير معروف"},
                            status=400)

    payload = (request.POST.get("payload") or "").strip()
    if not payload:
        return JsonResponse({"ok": False, "reason": "لا بيانات"}, status=400)
    if len(payload) > 24000:
        return JsonResponse(
            {"ok": False,
             "reason": f"المُرسَل {len(payload)} حرفاً — والحدّ ٢٤٬٠٠٠."},
            status=400)

    lim = spend.limits()
    try:
        asked = int(request.POST.get("max") or lim.get("max_tokens") or 1200)
    except (TypeError, ValueError):
        asked = 1200
    max_tokens = max(200, min(int(lim.get("max_tokens") or 1200), asked))

    key = _key(purpose, payload)
    with _LOCK:
        _sweep()
        prev = _read(key)
        if prev and prev.get("state") == "running":
            return JsonResponse({"ok": True, "state": "running", "key": key})
        # ═══ نداءٌ واحد في وقتٍ واحد ═══
        #
        # كلّ نداءٍ يُنفَق. والتوازي يضاعف الفاتورة على ضغطتين
        # متتاليتين بلا أن يُقصَد.
        if _running_count() >= 1:
            return JsonResponse(
                {"ok": False, "reason": "نداءٌ جارٍ — انتظره. "
                                        "كلّ نداءٍ يُنفَق."}, status=429)
        _write(key, {"state": "running"})

    # الموضوع يُمرَّر صريحاً كي يُرشَّح به الأرشيف لاحقاً
    subject = (request.POST.get("subject") or "").strip().upper()[:40]

    user = f"الغرض: {PURPOSES[purpose]}\n\nالبيانات:\n{payload}"
    threading.Thread(target=_run,
                     args=(key, SYSTEM_AR, user, purpose, max_tokens,
                           subject),
                     name=f"together-{purpose}", daemon=True).start()

    est_in = tp._rough_tokens(SYSTEM_AR) + tp._rough_tokens(user)
    return JsonResponse({
        "ok": True, "state": "running", "key": key,
        "estimate_usd": spend.estimate_cost(tp.model_id(), est_in, max_tokens),
    })


@require_GET
def api_together_history(request):
    """الإجابات المحفوظة — لرمزٍ أو الأحدث عامّةً.

    قراءةٌ من ملفٍّ فقط: لا نداءَ مدفوع هنا بحال.
    """
    from scanner.ai_advisor import archive

    subject = (request.GET.get("subject") or "").strip()
    one = (request.GET.get("id") or "").strip()
    if one:
        row = archive.get(one)
        if not row:
            return JsonResponse({"ok": False, "reason": "غير موجودة"},
                                status=404)
        return JsonResponse({"ok": True, "answer": row})
    if subject:
        return JsonResponse({"ok": True, "subject": subject.upper(),
                             "answers": archive.list_for(subject)})
    return JsonResponse({"ok": True, "answers": archive.recent(),
                         "stats": archive.stats()})


@require_GET
def api_together_status(request):
    from scanner.ai_advisor import spend

    key = (request.GET.get("key") or "").strip()
    job = _read(key)
    try:
        s = spend.summary()
    except Exception:  # noqa: BLE001
        s = {}
    if not job:
        # ═══ ``idle`` حالةٌ صريحة ═══
        #
        # كانت الواجهة تمرّ عليها إلى فرع «تمّ»، فترسم نتيجةً
        # فارغة: «كلّف — · 0 داخل · 0 خارج». فبدا النداء وكأنّه
        # نجح ولم يُنتج شيئاً.
        return JsonResponse({"ok": True, "state": "idle", "spend": s})

    out = {"ok": True, "state": job.get("state", "idle"),
           "elapsed": job.get("elapsed",
                              round(time.time() - float(job.get("at") or 0), 1)),
           "spend": s}
    if job.get("state") == "done":
        out["result"] = job.get("result") or {}
    elif job.get("state") in ("failed", "budget"):
        out["error"] = job.get("error", "")
    return JsonResponse(out)
