# -*- coding: utf-8 -*-
"""اختبارات محرّك حسم الصفقات — بلا Django ولا شبكة.

يُشغَّل:  python tests_tracking.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.tracking import (EXPIRED, LOST, OPEN, PENDING, WON, Plan, resolve,
                              split, split_multi, summarize, wilson)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


# خطة شراء قياسية: دخول 100، وقف 90، هدف 120 ← مخاطرة 10، هدف 2R
BUY = Plan(side="buy", entry=100, stop=90, target=120)
SELL = Plan(side="sell", entry=100, stop=110, target=80)

# ─────────────────────────────── الدخول

r = resolve([bar(105, 106, 104, 105), bar(105, 105, 103, 104)], BUY)
check("لم يبلغ الدخول ← تنتظر", r.status == PENDING, r.status)

r = resolve([bar(105, 106, 99, 101)], BUY)
check("لمس الدخول ← مفتوحة", r.status == OPEN and r.entry_price == 100,
      f"{r.status} @ {r.entry_price}")

r = resolve([bar(98, 99, 97, 98)], BUY)
check("فجوة تحت الدخول ← التنفيذ عند الافتتاح لا عند الدخول",
      r.status == OPEN and r.entry_price == 98, str(r.entry_price))

r = resolve([bar(105, 106, 104, 105)] * 5, BUY, max_bars=3)
check("انقضاء المهلة بلا دخول ← لم تُفعَّل", r.status == EXPIRED, r.status)

# فجوة تفتح تحت الوقف قبل الدخول: الخطة لاغية لا صفقة بصفر
r = resolve([bar(85, 86, 84, 85)], BUY)
check("فجوة تفتح تحت الوقف ← لا صفقة (لا 0R وهمية)",
      r.status == EXPIRED and "لاغية" in r.note, f"{r.status} · {r.note}")
r = resolve([bar(115, 116, 114, 115)], SELL)
check("بيع: فجوة تفتح فوق الوقف ← الخطة لاغية",
      r.status == EXPIRED, r.status)
r = resolve([bar(95, 96, 94, 95)], BUY)
check("فجوة بين الدخول والوقف ← تنفيذ سليم",
      r.status == OPEN and r.entry_price == 95, f"{r.status} @ {r.entry_price}")

# ─────────────────────────────── الحسم

r = resolve([bar(100, 101, 99, 100), bar(100, 121, 99, 120)], BUY)
check("الهدف قبل الوقف ← رابحة +2R",
      r.status == WON and r.r_multiple == 2.0, f"{r.status} {r.r_multiple}")

r = resolve([bar(100, 101, 99, 100), bar(99, 100, 89, 90)], BUY)
check("الوقف قبل الهدف ← خاسرة −1R",
      r.status == LOST and r.r_multiple == -1.0, f"{r.status} {r.r_multiple}")

# الحالة الحرجة: شمعة واحدة تلمس الاثنين
r = resolve([bar(100, 125, 85, 110)], BUY)
check("شمعة تلمس الوقف والهدف ← خسارة (لا تجميل)",
      r.status == LOST and r.r_multiple == -1.0, f"{r.status} {r.r_multiple}")

# فجوة تتخطّى الوقف: الخسارة أكبر من 1R
r = resolve([bar(100, 101, 99, 100), bar(80, 82, 79, 80)], BUY)
check("فجوة تحت الوقف ← خسارة أكبر من 1R",
      r.status == LOST and r.r_multiple == -2.0, str(r.r_multiple))

r = resolve([bar(100, 101, 99, 100), bar(130, 132, 129, 131)], BUY)
check("فجوة فوق الهدف ← ربح أكبر من 2R",
      r.status == WON and r.r_multiple == 3.0, str(r.r_multiple))

# دخول وحسم في الشمعة نفسها
r = resolve([bar(105, 106, 99, 105), bar(105, 121, 104, 120)], BUY)
check("الدخول ثم الهدف في شمعة لاحقة", r.status == WON and r.entry_bar == 0,
      f"{r.status} entry_bar={r.entry_bar}")

# ─────────────────────────────── البيع

r = resolve([bar(100, 101, 99, 100), bar(99, 100, 79, 80)], SELL)
check("بيع: الهدف قبل الوقف ← رابحة +2R",
      r.status == WON and r.r_multiple == 2.0, f"{r.status} {r.r_multiple}")

r = resolve([bar(100, 101, 99, 100), bar(101, 111, 100, 110)], SELL)
check("بيع: الوقف ← خاسرة −1R",
      r.status == LOST and r.r_multiple == -1.0, f"{r.status} {r.r_multiple}")

# ─────────────────────────────── صفقة مفتوحة سلفاً

r = resolve([bar(105, 121, 104, 120)], BUY, already_entered=True, entry_price=100)
check("صفقة مفتوحة تُستأنف من سعر تنفيذها",
      r.status == WON and r.r_multiple == 2.0, str(r.r_multiple))

r = resolve([bar(105, 106, 104, 105)], BUY, already_entered=True, entry_price=100)
check("مفتوحة بلا حسم ← R غير محقّق يُحسب من الإغلاق",
      r.status == OPEN and r.r_multiple == 0.5, str(r.r_multiple))

# ─────────────────────────────── خطط غير صالحة

check("وقف فوق الدخول في شراء ← مرفوضة",
      resolve([bar(100, 101, 99, 100)], Plan("buy", 100, 110, 120)).status == EXPIRED)
check("مخاطرة صفرية ← مرفوضة",
      resolve([bar(100, 101, 99, 100)], Plan("buy", 100, 100, 120)).status == EXPIRED)
check("هدف تحت الدخول في شراء ← مرفوضة",
      resolve([bar(100, 101, 99, 100)], Plan("buy", 100, 90, 95)).status == EXPIRED)

# شموع مشوّهة لا تُسقط المحرّك
r = resolve([{"open": None}, {"high": "x"}, bar(100, 121, 99, 120)], BUY)
check("شموع ناقصة تُتخطّى بلا انهيار", r.status == WON, r.status)

# ─────────────────────────────── الإحصاءات

rows = ([{"status": WON, "r_multiple": 2.0}] * 3 +
        [{"status": LOST, "r_multiple": -1.0}] * 7)
s = summarize(rows)
check("نسبة النجاح 30%", s["win_rate"] == 30.0, str(s["win_rate"]))
check("التوقّع = (3×2 − 7×1)/10 = −0.1", s["expectancy"] == -0.1, str(s["expectancy"]))
check("عامل الربح = 6/7", s["profit_factor"] == 0.86, str(s["profit_factor"]))
check("عيّنة 10 غير موثوقة", s["reliable"] is False)

s = summarize([{"status": WON, "r_multiple": 2.0}] * 3)
check("بلا خسائر ← عامل الربح None لا لانهاية", s["profit_factor"] is None)

s = summarize([{"status": OPEN, "r_multiple": 0.5},
               {"status": PENDING}, {"status": EXPIRED},
               {"status": WON, "r_multiple": 2.0}])
check("غير المحسومة تُستثنى من النسب",
      s["closed"] == 1 and s["win_rate"] == 100.0 and s["open"] == 1
      and s["pending"] == 1 and s["expired"] == 1, str(s))

check("لا صفقات ← لا نسبة", summarize([])["win_rate"] is None)

lo, hi = wilson(3, 4)
check("مجال ويلسون لـ 3/4 واسع (عيّنة صغيرة)",
      lo < 35 and hi > 90, f"{lo}–{hi}")
lo, hi = wilson(300, 400)
check("مجال ويلسون لـ 300/400 ضيّق", hi - lo < 10, f"{lo}–{hi}")

# التقسيم
rows = [
    {"grade": "A", "status": WON, "r_multiple": 2.0},
    {"grade": "A", "status": WON, "r_multiple": 2.0},
    {"grade": "C", "status": LOST, "r_multiple": -1.0},
    {"grade": "C", "status": LOST, "r_multiple": -1.0},
]
sp = split(rows, "grade")
check("التقسيم يرتّب الأفضل أولاً", sp[0]["value"] == "A" and sp[1]["value"] == "C",
      str([x["value"] for x in sp]))
check("min_n يحجب الشرائح الصغيرة", split(rows, "grade", min_n=3) == [])

rows = [
    {"factors": ["إليوت", "التقاء"], "status": WON, "r_multiple": 2.0},
    {"factors": ["إليوت"], "status": LOST, "r_multiple": -1.0},
    {"factors": ["التقاء"], "status": WON, "r_multiple": 2.0},
]
sp = {x["value"]: x for x in split_multi(rows, "factors")}
check("العامل المشترك يُحسب في كل صفقة يظهر فيها",
      sp["إليوت"]["closed"] == 2 and sp["التقاء"]["closed"] == 2,
      str({k: v["closed"] for k, v in sp.items()}))
check("التقاء (2/2) يسبق إليوت (1/2)",
      split_multi(rows, "factors")[0]["value"] == "التقاء")

# ─────────────────────────────── التقرير

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
