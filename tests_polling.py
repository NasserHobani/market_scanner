# -*- coding: utf-8 -*-
"""حراسة الاستعلامات الدورية — ألّا تتراكم الطلبات.

═══ لماذا ═══

‏``setInterval`` يُطلق على الساعة لا على وصول الردّ. فإن طال الردّ عن
الفترة — وهو ما يحدث حين ينتظر نداءَ شبكة إلى مزوّد الأسعار — تتراكم
الطلبات: طلب كل خمس ثوانٍ ولا واحد منها ينتهي.

والمتصفّح يحدّ الاتصالات المتزامنة بستّة للمضيف الواحد. فما زاد ينتظر
في طابور، ثم يُقطع عند التنقّل أو إعادة التحميل — وقطعُه هو ما يظهر في
سجلّ الخادم باسم ``Broken pipe``.

هذه الاختبارات تقرأ المصدر ولا تحتاج متصفّحاً ولا Django.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
STATIC = ROOT / "web" / "dashboard" / "static" / "dashboard"
TEMPLATES = ROOT / "web" / "dashboard" / "templates" / "dashboard"

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def strip_comments(src: str) -> str:
    """يحذف تعليقات // و/* */ حتى لا يُطابق الفحصُ شرحاً للعطب القديم."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("//")
    )


# ── الحارس نفسه ──
base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
base_code = strip_comments(base)

check("الحارس معرَّف عالمياً", "window.everyN" in base_code)
check("وله اسم قصير", "window.EVERY" in base_code)
check("ينتظر الوعدة قبل الجدولة",
      "typeof res.then" in base_code and "schedule(ms)" in base_code)
check("يتوقّف والصفحة مخفيّة", "document.hidden" in base_code)
check("ويستأنف عند العودة", "visibilitychange" in base_code)
# الحارس يجب أن يُعرَّف قبل سكربتات الصفحات وإلّا كان غير موجود عندها
check("يُعرَّف قبل سكربتات الصفحات",
      base.index("window.everyN") < base.index("{% block scripts %}"))

# ── لا مستعلم شبكيّ بقي على setInterval ──
#
# الفترات القصيرة هي الخطرة: كلّما قصرت الفترة قلّ الهامش قبل التراكم.
GUARDED = {
    "app.js": ("poll", "pollQuotes", "pollScanStatus"),
    "dashboard-page.js": ("pollOpenTrades",),
    "trades-page.js": ("pollActive",),
    "research-page.js": ("loadAutomationStatus",),
    "watches-page.js": ("load",),
}
for fname, fns in GUARDED.items():
    src = strip_comments((STATIC / fname).read_text(encoding="utf-8"))
    for fn in fns:
        check(f"{fname}: {fn} محروسة",
              f"EVERY({fn}" in src.replace(" ", "")
              or re.search(rf"EVERY\([^)]*,\s*{re.escape(fn)}\s*\)", src) is not None,
              "ما زالت على setInterval" if f"setInterval({fn}" in src.replace(" ", "")
              else "")
        check(f"{fname}: {fn} لا تبقى على setInterval",
              not re.search(rf"setInterval\(\s*{re.escape(fn)}\s*,", src))

# الدالة المحروسة يجب أن تُعيد وعدتها، وإلّا جدول الحارس فوراً بلا انتظار
RETURNS = [
    ("app.js", "poll"), ("app.js", "pollQuotes"), ("app.js", "pollScanStatus"),
    ("dashboard-page.js", "pollOpenTrades"), ("trades-page.js", "pollActive"),
    ("research-page.js", "loadAutomationStatus"),
]
CALL = re.compile(r"(return\s+)?(fetch|DS\.loadWidget)\s*\(")
for fname, fn in RETURNS:
    src = (STATIC / fname).read_text(encoding="utf-8")
    start = src.find(f"function {fn}()")
    # أول نداء جلب **بعد** رأس الدالة: أدقّ من قصّ الجسم بعدد محارف
    # ثابت، إذ تختلف أطوال الدوال وقد يقصّ الحدُّ النداء نفسه.
    m = CALL.search(src, start) if start >= 0 else None
    check(f"{fname}: {fn} تُعيد وعدتها",
          bool(start >= 0 and m and m.group(1)),
          "بلا return — الحارس سيجدول قبل وصول الردّ")

# ── الذاكرة على الخادم ──
views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
views_code = "\n".join(
    ln for ln in views.splitlines() if not ln.strip().startswith("#")
)

check("قفل لكل سوق موجود", "_QUOTE_LOCKS" in views_code)
check("والذاكرة تُفحص مرّة ثانية داخل القفل",
      views_code.count("QUOTE_TTL") >= 2)
check("والردّ يُعلن التجميع", '"coalesced"' in views_code)

# ‏TTL يجب أن تتجاوز فترة استعلام الواجهة، وإلّا لم تُصِب الذاكرة أبداً:
# تنتهي في اللحظة التي يصل فيها الاستعلام التالي.
ttl = float(re.search(r"QUOTE_TTL\s*=\s*([\d.]+)", views_code).group(1))
app_src = (STATIC / "app.js").read_text(encoding="utf-8")
quote_ms = int(re.search(r"QUOTE_MS\s*=\s*(\d+)", app_src).group(1))
check("‏TTL أطول من فترة الاستعلام", ttl > quote_ms / 1000.0,
      f"TTL={ttl}s ومدة الاستعلام={quote_ms / 1000.0}s")

# ── النقطة الحيّة تبقى بلا حساب ──
#
# قاعدة انتُهكت مرّتين في هذا المشروع: طبقة العرض لا تنتظر شيئاً.
live = (ROOT / "web" / "dashboard" / "ai_live_views.py").read_text(encoding="utf-8")
live_code = "\n".join(
    ln for ln in live.splitlines() if not ln.strip().startswith("#")
)
for forbidden in ("requests.", "urlopen", "adapter.", "fetch_many", "time.sleep"):
    check(f"النقطة الحيّة بلا «{forbidden}»", forbidden not in live_code)

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
