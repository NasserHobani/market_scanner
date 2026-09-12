# -*- coding: utf-8 -*-
"""التزامن — ما الذي يحجب ماذا.

═══ ما تحرسه ═══

«النظام يعلّق» شكوى لا تُصلَح كما هي. فالمطلوب أن يقول النظام **أيّ**
عملية حجبت غيرها، ومتى، وكم دامت. وبلا ذلك تبقى كل تعديلات الأداء
تخميناً.

والحواجز هنا:

  ١. **الرصد لا يحجب.** أداةُ تشخيصٍ تُبطئ ما تراقبه تصير جزءاً من
     المشكلة. فالقفل يُمسك للحظات لا طوال العملية.
  ٢. **العمل الطويل خارج مسار الطلب.** طلبٌ ينتظر الشبكة يشغل خيطاً،
     والمتصفّح يحدّ اتصالاته بستّة.
  ٣. **المنع لا يُبتلع.** نقلُ بوّابة الحداثة إلى الخيط ألغى ردّ 409،
     فيجب أن يصل السبب بطريق آخر.
"""
from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from dashboard.concurrency import (  # noqa: E402
    SLOW_MS, InFlightMiddleware, reset, snapshot, track,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def code_of(path: str) -> str:
    src = (ROOT / path).read_text(encoding="utf-8")
    return "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))


# ── ١) الرصد يرى ما يعمل ──
reset()
check("١ لا شيء يعمل ابتداءً", snapshot()["concurrent"] == 0)

with track("عملية أ"):
    snap = snapshot()
    check("  العملية الجارية تُرى", snap["concurrent"] == 1, str(snap))
    check("  باسمها", snap["running"][0]["label"] == "عملية أ")
    check("  وبمدّتها", snap["running"][0]["ms"] >= 0)
check("  وتختفي بعد انتهائها", snapshot()["concurrent"] == 0)


# ── ٢) التزامن الحقيقي يُرصد ──
#
# ثلاثة خيوط تعمل معاً: الذروة يجب أن تكون 3 لا 1. وهذا الرقم بالذات
# هو ما يفرّق بين نظام متزامن وآخر متسلسل.
reset()
gate = threading.Event()
peak_seen = []


def worker(name: str) -> None:
    with track(name):
        peak_seen.append(snapshot()["concurrent"])
        gate.wait(2.0)


threads = [threading.Thread(target=worker, args=(f"عامل {i}",))
           for i in range(3)]
for t in threads:
    t.start()
time.sleep(0.15)
mid = snapshot()
gate.set()
for t in threads:
    t.join(3.0)

check("٢ الثلاثة تعمل معاً", mid["concurrent"] == 3, str(mid["concurrent"]))
check("  والذروة تُسجَّل", snapshot()["stats"]["peak_concurrent"] == 3)
check("  وتُفرَغ بعد الانتهاء", snapshot()["concurrent"] == 0)


# ── ٣) البطيء يُحفَظ ومعه من كان ينتظر ──
reset()
with track("بطيئة"):
    time.sleep(SLOW_MS / 1000.0 + 0.05)
slow = snapshot()["recent_slow"]
check("٣ البطيئة تُحفَظ", len(slow) == 1, str(slow))
check("  بمدّتها", slow and slow[0]["ms"] >= SLOW_MS)
check("  والسريعة لا تُحفَظ", (lambda: (
    [track("سريعة").__enter__().__exit__(), None][1],
    len(snapshot()["recent_slow"]) == 1)[1])())


# ── ٤) الرصد نفسه لا يحجب ──
#
# القفل يُمسك عند الدخول والخروج فقط. لو أُمسك طوال العملية لصار
# الرصد يفرض تسلسلاً على ما يقيسه — أي يخلق الظاهرة التي يدرسها.
reset()
started = threading.Event()
release = threading.Event()
overlapped = []


def holder() -> None:
    with track("ممسكة طويلاً"):
        started.set()
        release.wait(2.0)


th = threading.Thread(target=holder)
th.start()
started.wait(1.0)
t0 = time.monotonic()
with track("سريعة أثناء الطويلة"):
    overlapped.append(True)
elapsed = (time.monotonic() - t0) * 1000
release.set()
th.join(3.0)

check("٤ الرصد لا يحجب", elapsed < 50, f"{elapsed:.0f}ms")
check("  والعمليتان تداخلتا فعلاً", overlapped == [True])


# ── ٥) الوسيط يرصد الطلب ──
seen = {}


def fake_view(request):  # noqa: ANN001
    seen["concurrent"] = snapshot()["concurrent"]
    return "ردّ"


class _Req:
    method = "GET"
    path = "/api/test/"


reset()
mw = InFlightMiddleware(fake_view)
check("٥ الوسيط يعيد الردّ", mw(_Req()) == "ردّ")
check("  ويرصد الطلب أثناءه", seen.get("concurrent") == 1)
check("  ويُفرغه بعده", snapshot()["concurrent"] == 0)
check("  والوسيط مفعَّل في الإعدادات",
      "dashboard.concurrency.InFlightMiddleware"
      in code_of("web/config/settings.py"))


# ── ٦) العمل الطويل خارج مسار الطلب ──
views = code_of("web/dashboard/views.py")
check("٦ بوّابة الحداثة ليست في الطلب",
      "scan_freshness_gate" not in views.split("def api_scan_now")[1]
      .split("def api_scan_status")[0],
      "ما زالت داخل api_scan_now")
check("  بل في الخيط الخلفي",
      "scan_freshness_gate" in views.split("def _gated_scan")[1][:900])
check("  والمسح يبدأ بخيط", "threading.Thread(" in views)
check("  والخيط مرصود", 'kind="scan"' in views)

# نداء النموذج مرصود — هو أطول ما في النظام (116 ثانية وسيطاً)
pm = code_of("web/dashboard/postmortem_views.py")
check("  ونداء النموذج مرصود", 'kind="llm"' in pm)

# الحلقات الخلفية مرصودة: تعمل كل بضع دقائق وتكتب في القاعدة
for f, kind in (("web/dashboard/settlement.py", "settlement"),
                ("web/dashboard/monitor.py", "monitor")):
    check(f"  وحلقة {kind} مرصودة", f'kind="{kind}"' in code_of(f))


# ── ٧) المنع لا يُبتلع ──
#
# نقلُ البوّابة إلى الخيط ألغى ردّ 409 للمتصفّح. فلو لم يصل السبب
# بطريق آخر لضغط المستخدم «امسح الآن» ولم يحدث شيء ولم يعرف لماذا —
# وهو أسوأ من رسالة الخطأ التي حلّت محلّها.
sched = code_of("web/dashboard/scheduler.py")
check("٧ سبب المنع يُسجَّل", "def note_blocked" in sched)
check("  ويصل عبر الحالة", "last_blocked" in sched)
check("  والخيط يستدعيه", "note_blocked(" in views)

# تعذّر الفحص لا يمنع المسح: العطب قد يكون في الفاحص لا في البيانات
check("  وفشل الفاحص لا يمنع المسح",
      "scheduler.run_scan(market, timeframe" in views)


# ── ٨) نقطة التشخيص رخيصة ──
#
# نقطةٌ تحتاج قاعدة بيانات أو شبكة لتقول «ما الذي يحجب» تصير جزءاً من
# الحجب. ولا تُستثنى من الرصد أيضاً: استثناؤها يُخفي كونها بطيئة.
conc = code_of("web/dashboard/concurrency.py")
for forbidden in ("objects.", "requests.", "urlopen", "storage.load",
                  "time.sleep"):
    check(f"٨ نقطة التشخيص بلا «{forbidden}»", forbidden not in conc)
check("  ولا تُستثنى نقاط من الرصد",
      "exclude" not in conc.lower() and "skip" not in conc.lower())

urls = code_of("web/dashboard/urls.py")
check("  والمسار مربوط", "api/concurrency/" in urls)

# ── ٩) الحدود ──
reset()
try:
    with track("تنفجر"):
        raise ValueError("خطأ متعمَّد")
except ValueError:
    pass
check("٩ الاستثناء لا يترك عملية معلَّقة", snapshot()["concurrent"] == 0)

reset()
many = [threading.Thread(target=lambda i=i: worker(f"ك{i}")) for i in range(12)]
gate.clear()
for t in many:
    t.start()
time.sleep(0.2)
c = snapshot()["concurrent"]
gate.set()
for t in many:
    t.join(3.0)
check("  ويتحمّل خيوطاً كثيرة", c == 12, str(c))
check("  ويُفرَغ بعدها", snapshot()["concurrent"] == 0)

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
