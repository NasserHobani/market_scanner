# -*- coding: utf-8 -*-
"""مهامّ خلفية بتقدّم مرئيّ — بلا Django.

═══ لماذا وحدة مستقلّة ═══

الطلب المتزامن لثلاثمئة رمز ينتهي بمهلة الخادم، فيرى المستخدم خطأً
بينما العمل يجري فعلاً. و«طال» و«فشل» حالتان لا يجوز أن تبدوا
واحدة — فالعمل يذهب إلى خيط، والصفحة تستعلم عن التقدّم.

وفُصلت عن ``companies_views`` لأنّها لا تعرف شيئاً عن الشركات ولا
عن Django: قاموسٌ وقفل وحسبة نسبة. وبقاؤها هناك كان يعني أن
اختبارها يتطلّب إقلاع Django كاملاً — أي أنّها لن تُختبر.

═══ ولماذا مهمّة واحدة لكل نوع ═══

الضغط المزدوج على الزر لا يبدأ عملاً مضاعفاً على المزوّد نفسه.
وهذا ليس تنميقاً: مضاعفة الطلبات على Alpaca هي ما استدعى ``429``
الذي أوقف اكتشاف السوق الأمريكي.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _blank(kind: str) -> dict[str, Any]:
    return {"kind": kind, "state": "idle", "done": 0, "total": 0,
            "note": "", "error": "", "started": 0.0, "scope": ""}


def reset(kind: str | None = None) -> None:
    """للاختبارات ولإعادة التهيئة."""
    with _LOCK:
        if kind is None:
            _JOBS.clear()
        else:
            _JOBS[kind] = _blank(kind)


def begin(kind: str, *, scope: str = "", total: int = 0,
          note: str = "") -> bool:
    """يبدأ مهمّة. يعيد False إن كانت واحدةٌ من نوعها تعمل بالفعل."""
    with _LOCK:
        cur = _JOBS.get(kind) or _blank(kind)
        if cur["state"] == "running":
            return False
        _JOBS[kind] = {**_blank(kind), "state": "running", "total": int(total),
                       "note": note, "started": time.time(), "scope": scope}
    return True


def set_total(kind: str, total: int) -> None:
    """العدد الكلّي قد لا يُعرَف إلّا بعد أوّل نداء شبكة."""
    with _LOCK:
        if kind in _JOBS:
            _JOBS[kind]["total"] = int(total)


def step(kind: str, note: str = "", n: int = 1) -> None:
    with _LOCK:
        job = _JOBS.get(kind)
        if not job:
            return
        job["done"] += n
        if note:
            job["note"] = note


def finish(kind: str, note: str = "", error: str = "") -> None:
    with _LOCK:
        job = _JOBS.get(kind)
        if not job:
            job = _JOBS[kind] = _blank(kind)
        job.update(state="failed" if error else "done",
                   note=note or job.get("note", ""), error=error)


def snapshot(kind: str, *, now: float | None = None) -> dict[str, Any]:
    """حالة المهمّة للعرض — بلا الطابع الخام.

    ``eta_seconds`` من المعدّل **المقاس** لا من ثابت مفترض: مصدرٌ
    بطيء ومصدرٌ سريع لا يستحقّان التقدير نفسه، والرقم المفترض يكذب
    مرّتين — يطمئن ثمّ يخيّب.
    """
    with _LOCK:
        job = dict(_JOBS.get(kind) or _blank(kind))
    started = job.pop("started", 0.0) or 0.0
    t = time.time() if now is None else now
    job["elapsed"] = round(max(0.0, t - started), 1) if started else 0.0

    total, done = int(job.get("total") or 0), int(job.get("done") or 0)
    job["percent"] = round(100.0 * min(done, total) / total, 1) if total else 0.0

    if job["state"] == "running" and done > 0 and total > done:
        job["eta_seconds"] = round((job["elapsed"] / done) * (total - done))
    else:
        job["eta_seconds"] = None
    return job


def any_running(*kinds: str) -> str:
    """اسم أوّل نوع يعمل — أو نصّ فارغ."""
    with _LOCK:
        for k in (kinds or tuple(_JOBS)):
            if (_JOBS.get(k) or {}).get("state") == "running":
                return k
    return ""


def run_in_thread(kind: str, target: Callable[..., None], *args,
                  name: str = "") -> None:
    """يشغّل ``target`` في خيط ويضمن إنهاء المهمّة مهما وقع.

    بلا هذا الغلاف، استثناءٌ غير متوقّع يترك الحالة ``running`` إلى
    الأبد: الزرّ معطّل والصفحة تستعلم بلا نهاية، والمستخدم لا يعلم
    أنّ شيئاً مات.
    """
    def _wrapped() -> None:
        try:
            target(*args)
        except BaseException as exc:  # noqa: BLE001
            finish(kind, "تعذّر", str(exc)[:250])
        finally:
            with _LOCK:
                job = _JOBS.get(kind)
                if job and job["state"] == "running":
                    job.update(state="failed",
                               error=job.get("error") or "انتهى بلا إعلان نتيجة")

    threading.Thread(target=_wrapped, name=name or f"job-{kind}",
                     daemon=True).start()


__all__ = ["begin", "step", "finish", "snapshot", "set_total", "reset",
           "any_running", "run_in_thread"]
