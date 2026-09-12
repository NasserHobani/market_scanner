# -*- coding: utf-8 -*-
"""اختبارات مرشّح حالة الصفقات — بلا Django.

الفخّ الذي تحرسه: ترشيح «رابحة» ثم حساب نسبة النجاح على المرشَّح يعطي
100% دائماً وتوقّعاً موجباً دائماً — رقم صحيح حسابياً وبلا أي معنى.
لذلك المرشّح للجدول والإحصاءات على العيّنة الكاملة.

    python tests_trade_filters.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

VIEWS = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
TPL = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "performance.html").read_text(encoding="utf-8")

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ── استخراج الخرائط الحقيقية من views.py ──
ns: dict = {}
block = VIEWS[VIEWS.index("STATUS_FILTERS = {"):VIEWS.index("def _trade_filters")]
exec(compile(block, "views.py", "exec"), ns)
STATUS_FILTERS = ns["STATUS_FILTERS"]
STATUS_LABELS = ns["STATUS_LABELS"]

# ── سلامة الخرائط ──
check("لكل مرشّح تسمية عربية",
      set(STATUS_FILTERS) == set(STATUS_LABELS),
      set(STATUS_FILTERS) ^ set(STATUS_LABELS))
check("«الكل» بلا قيد", STATUS_FILTERS["all"] == ())
check("«محسومة» = رابحة + خاسرة",
      set(STATUS_FILTERS["closed"]) == {"won", "lost"})
check("«رابحة» و«خاسرة» منفصلتان",
      STATUS_FILTERS["won"] == ("won",) and STATUS_FILTERS["lost"] == ("lost",))
check("«لم تُفعَّل» تشمل الملغاة",
      set(STATUS_FILTERS["expired"]) == {"expired", "cancelled"})

MODEL_STATES = {"pending", "open", "won", "lost", "expired", "cancelled"}
covered = {s for states in STATUS_FILTERS.values() for s in states}
check("كل حالة في النموذج يغطّيها مرشّح",
      covered == MODEL_STATES, MODEL_STATES ^ covered)


# ── محاكاة الاستعلام ──
class QS:
    def __init__(self, rows): self.rows = list(rows)
    def filter(self, **kw):
        out = self.rows
        for k, v in kw.items():
            if k == "status__in":
                out = [r for r in out if r["status"] in v]
            elif k.endswith("__isnull"):
                continue
            else:
                out = [r for r in out if r.get(k) == v]
        return QS(out)
    def __len__(self): return len(self.rows)
    def __iter__(self): return iter(self.rows)


def apply_status(qs, status):
    wanted = STATUS_FILTERS.get(status) or ()
    return qs.filter(status__in=wanted) if wanted else qs


ROWS = ([{"status": "won", "r_multiple": 2.0}] * 4 +
        [{"status": "lost", "r_multiple": -1.0}] * 6 +
        [{"status": "open", "r_multiple": 0.3}] * 3 +
        [{"status": "pending", "r_multiple": None}] * 2 +
        [{"status": "expired", "r_multiple": None}] * 5 +
        [{"status": "cancelled", "r_multiple": None}] * 1)
ALL = QS(ROWS)

for key, expect in (("all", 21), ("closed", 10), ("won", 4), ("lost", 6),
                    ("open", 3), ("pending", 2), ("expired", 6)):
    got = len(apply_status(ALL, key))
    check(f"مرشّح «{STATUS_LABELS[key]}» يعطي {expect}", got == expect, got)

check("مرشّح مجهول يُعامَل كـ الكل",
      len(apply_status(ALL, "لا-يوجد")) == 21)

# ── الفخّ: الإحصاءات لا تتبع المرشّح ──
from scanner.tracking import summarize

full = summarize(list(ALL))
filtered = summarize(list(apply_status(ALL, "won")))
check("لو رُشّحت الإحصاءات لأعطت 100% مضلّلة",
      filtered["win_rate"] == 100.0, filtered["win_rate"])
check("والصحيح أن العيّنة الكاملة تعطي 40%",
      full["win_rate"] == 40.0, full["win_rate"])

# ── وأن الكود فعلاً يفعل ذلك ──
qs_fn = VIEWS[VIEWS.index("def _trade_queryset"):VIEWS.index("def _apply_status")]
check("‏_trade_queryset لا يمسّ الحالة إطلاقاً",
      "status" not in qs_fn.replace("الحالة", ""),
      "لو رشّح الحالة لفسدت كل البطاقات")
perf = VIEWS[VIEWS.index("def performance("):VIEWS.index("def _storage_format")]
check("rows_for_stats تُبنى من الاستعلام غير المرشَّح",
      re.search(r"rows_for_stats\(qs\)", perf) is not None)
check("والجدول يُبنى من المرشَّح",
      re.search(r"_apply_status\(qs, f\[.status.\]\)", perf) is not None)

# ── الواجهة ──
check("رقائق الحالة موجودة في القالب", "aria-label=\"حالة الصفقة\"" in TPL)
check("وتحمل عدّاداً لكل حالة", 'data-count="{{ st.key }}"' in TPL)
check("والصفحة تنبّه أن البطاقات غير مرشَّحة",
      "بلا معنى" in TPL and 'filters.status != "all"' in TPL)
check("وحالة فراغ تشرح السبب وتعرض مخرجاً",
      "لا صفقة بحالة" in TPL and "اعرض كل الحالات" in TPL)
check("والأعداد تتحدّث حيّاً", 'data-count="' in TPL and "d.counts" in TPL)
check("المرشّح يبقى في نداء التحديث",
      'parts["status"] = f["status"]' in VIEWS)

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
