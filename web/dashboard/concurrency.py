# -*- coding: utf-8 -*-
"""رصد التزامن — ما الذي يعمل الآن، وما الذي يحجب غيره.

═══ المسألة ═══

«النظام يعلّق» شكوى صحيحة لكنها لا تُصلَح كما هي: أهو المسح؟ أم نداء
النموذج؟ أم قفل قاعدة البيانات؟ أم طلبٌ ينتظر الشبكة؟ لكلٍّ علاج
مختلف، والتخمين بينها يُنتج تعديلات لا تُقاس.

═══ لماذا خادم التطوير يعلّق أصلاً ═══

‏``runserver`` يخدم كل طلب في خيط، فيبدو متزامناً. لكنّ ثلاثة قيود
تجعله متسلسلاً عملياً:

  ١. **قفل المفسّر (‏GIL) — وهذا قِيس ووُجد أقلّ أثراً مما يُظنّ.**

     كنت أظنّ المسح يحجب غيره لأنه يحسب. والقياس نفى ذلك: أثناء مسح
     حقيقي لمئة وعشرين رمزاً في 12.5 ثانية، نُفِّذ طلب خفيف **979
     مرّة** (78 في الثانية) ووسيط زمنه **تحسّن** من 0.084ms إلى
     0.064ms.

     والسبب أن pandas وnumpy تُطلقان القفل أثناء عملهما في طبقة C.
     فالحساب الثقيل ليس هو الحاجب — ما يحجب هو **الانتظار داخل
     Python**: شبكة، أو قفل، أو قراءة آلاف الملفات.

     يبقى القفل قيداً حقيقياً على شيفرة Python الخالصة الثقيلة، لكن
     اتّهامه هنا كان تخميناً صحّحه القياس.

  ٢. **كتابة SQLite تتسلسل.** القرّاء لا يتزاحمون بعد تفعيل ‏WAL،
     لكنّ الكاتب واحد. ومعاملة تكتب مئات الصفوف تحجب كل كاتب آخر
     طوال مدّتها.

  ٣. **العمل المتزامن داخل الطلب.** طلبٌ ينتظر الشبكة يشغل خيطاً
     ولا يُنتج شيئاً. والمتصفّح يحدّ اتصالاته بستّة، فستّة طلبات
     بطيئة تُجمّد الواجهة كلّها.

والرصد هنا لا يحلّ أياً منها — بل يقول **أيّها** يقع، وهذا شرط
إصلاحٍ موجَّه بدل تخمين.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

__all__ = ["InFlightMiddleware", "snapshot", "track", "SLOW_MS"]

# ما فوقه يُعدّ بطيئاً ويُحفَظ للتشخيص. اختير 1500ms لأن ما دونه لا
# يُشعِر المستخدم بالتعليق، وما فوقه يبدأ في حجب الاتصالات.
SLOW_MS = 1500.0

_MAX_SLOW = 40

_lock = threading.Lock()
_inflight: dict[int, dict[str, Any]] = {}
_slow: deque = deque(maxlen=_MAX_SLOW)
_seq = 0
_stats = {"requests": 0, "slow": 0, "peak_concurrent": 0,
          "blocked_ms": 0.0}


def _now_ms() -> float:
    return time.monotonic() * 1000.0


class _Tracker:
    """سياق يسجّل عملية جارية ومدّتها."""

    def __init__(self, label: str, kind: str = "task") -> None:
        self.label = label
        self.kind = kind
        self.key = 0
        self._t0 = 0.0

    def __enter__(self) -> "_Tracker":
        global _seq
        self._t0 = _now_ms()
        with _lock:
            _seq += 1
            self.key = _seq
            _inflight[self.key] = {
                "id": self.key, "label": self.label, "kind": self.kind,
                "started": self._t0, "thread": threading.current_thread().name,
            }
            _stats["requests"] += 1
            # الذروة تُسجَّل لحظة الدخول: هي عدد ما كان يعمل **معاً**،
            # وهو الرقم الذي يفرّق بين نظام متزامن وآخر متسلسل
            if len(_inflight) > _stats["peak_concurrent"]:
                _stats["peak_concurrent"] = len(_inflight)
        return self

    def __exit__(self, *exc: Any) -> None:
        ms = _now_ms() - self._t0
        with _lock:
            entry = _inflight.pop(self.key, None)
            concurrent = len(_inflight) + 1
            if ms >= SLOW_MS:
                _stats["slow"] += 1
                # ما حجبه هذا الطلب تقريباً: مدّته مضروبة فيمن كان
                # ينتظر معه. تقدير خشن لكنه يرتّب المتّهمين ترتيباً
                # صحيحاً، وهو الغرض.
                _stats["blocked_ms"] += ms * max(0, concurrent - 1)
                _slow.appendleft({
                    "label": self.label, "kind": self.kind,
                    "ms": round(ms, 1), "concurrent": concurrent,
                    "at": time.time(),
                    "thread": (entry or {}).get("thread", ""),
                })


def track(label: str, kind: str = "task") -> _Tracker:
    """يرصد كتلة عمل::

        with track("مسح crypto 4h", kind="scan"):
            ...
    """
    return _Tracker(label, kind)


def snapshot() -> dict[str, Any]:
    """ما يعمل الآن، وأبطأ ما مضى."""
    now = _now_ms()
    with _lock:
        running = [
            {**v, "ms": round(now - v["started"], 1)}
            for v in _inflight.values()
        ]
        slow = list(_slow)
        stats = dict(_stats)
    running.sort(key=lambda r: -r["ms"])
    for r in running:
        r.pop("started", None)
    return {
        "running": running,
        "concurrent": len(running),
        "slowest_now": running[0] if running else None,
        "recent_slow": slow,
        "stats": stats,
        "threads": [t.name for t in threading.enumerate()],
    }


def reset() -> None:
    """للاختبارات."""
    with _lock:
        _inflight.clear()
        _slow.clear()
        for k in _stats:
            _stats[k] = 0 if isinstance(_stats[k], int) else 0.0


class InFlightMiddleware:
    """يرصد كل طلب — بلا استثناء.

    استثناء نقاط الاستعلام الدوري كان مغرياً (فهي كثيرة ورخيصة)، لكنه
    يُخفي بالضبط ما نبحث عنه: نقطةٌ رخيصة تصير بطيئة حين يحجبها غيرها،
    وهذا هو العرَض الذي يشتكي منه المستخدم.
    """

    def __init__(self, get_response) -> None:  # noqa: ANN001
        self.get_response = get_response

    def __call__(self, request):  # noqa: ANN001
        label = f"{request.method} {request.path}"
        with track(label, kind="http"):
            return self.get_response(request)


# ─────────────────────────────────────── نقطة العرض

def api_concurrency(request):  # noqa: ANN001
    """ما يعمل الآن وأبطأ ما مضى — للتشخيص.

    رخيصة عمداً: قراءة قاموس تحت قفل، بلا قاعدة بيانات ولا شبكة.
    نقطةُ تشخيصٍ تحتاج عملاً لتجيب تصير جزءاً من المشكلة التي تصفها.
    """
    from .jsonsafe import JsonResponse

    data = snapshot()
    st = data["stats"]
    hints: list[str] = []
    if data["concurrent"] >= 5:
        hints.append(
            f"{data['concurrent']} عملية تعمل معاً — المتصفّح يحدّ "
            "اتصالاته بستّة، فما زاد ينتظر.")
    slowest = data.get("slowest_now")
    if slowest and slowest["ms"] > 5000:
        hints.append(
            f"«{slowest['label']}» جارية منذ {slowest['ms'] / 1000:.0f} ثانية "
            "— هي المرشَّح الأول للحجب.")
    if st.get("slow"):
        hints.append(
            f"{st['slow']} عملية بطيئة من {st['requests']}؛ "
            f"الذروة {st['peak_concurrent']} معاً.")
    return JsonResponse({"ok": True, **data, "hints": hints,
                         "slow_threshold_ms": SLOW_MS})
