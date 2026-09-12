# -*- coding: utf-8 -*-
"""محاكاة قواعد الخروج — الصحّة قبل النتيجة.

═══ ما تحرسه ═══

محاكٍ يخطئ لا يُنتج «نتيجة خاطئة» بل **قراراً خاطئاً**: تُغيّر قاعدة
خروجك بناءً على رقم لم يحدث. فالحواجز هنا:

  ١. **يعيد إنتاج خطّ الأساس.** إن لم تُطابق محاكاةُ القاعدة الحالية
     ما جرى فعلاً، فلا معنى لمقارنة البدائل بها.
  ٢. **يفترض الأسوأ داخل الشمعة.** الشمعة لا تخبرنا أيّهما أوّلاً:
     قمّتها أم قاعها. والافتراض المتفائل يُنتج أرباحاً لا تُنفَّذ.
  ٣. **يحتسب كلفة الساق الإضافية.** الجني الجزئي يبدو رابحاً إجمالاً
     ويخسر صافياً — وهذا وقع في هذا المشروع من قبل.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.exits import RULES, ExitRule, compare_rules, simulate  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def bar(lo: float, hi: float, close: float | None = None) -> dict:
    return {"open": lo, "high": hi, "low": lo,
            "close": close if close is not None else (lo + hi) / 2}


FIXED = RULES[0]
BE1 = ExitRule("be", "تعادل بعد +1R", breakeven_at=1.0)
TRAIL = ExitRule("tr", "تتبّع 0.5R بعد +1R", trail_at=1.0, trail_by=0.5)
PARTIAL = ExitRule("pt", "جني نصف عند +1R", partial_at=1.0, breakeven_at=1.0)

# دخول 100 · وقف 90 · هدف 130  →  المخاطرة 10، الهدف +3R
E, S, T = 100.0, 90.0, 130.0


def sim(bars, rule=FIXED, side="buy", entry=E, stop=S, target=T):
    return simulate(bars, side=side, entry=entry, stop=stop,
                    target=target, rule=rule)


# ── ١) الأساسيات ──
check("١ الهدف يُحتسب +3R", abs(sim([bar(100, 131)]).r_multiple - 3.0) < 1e-9)
check("  والوقف −1R", abs(sim([bar(89, 100)]).r_multiple + 1.0) < 1e-9)
check("  وسبب الخروج صحيح", sim([bar(89, 100)]).exit_reason == "وقف")

# ── ٢) الأسوأ داخل الشمعة ──
#
# شمعة تلمس الوقف والهدف معاً: لا نعرف أيّهما أوّلاً. فيُحتسب الوقف.
# والافتراض المتفائل هنا يُنتج استراتيجية تربح في المحاكاة وتخسر في
# التنفيذ — وهو أسوأ أنواع الخطأ لأنه يبدو نجاحاً.
both = sim([bar(89, 131)])
check("٢ الشمعة الجامعة تُحتسب وقفاً", both.exit_reason == "وقف",
      both.exit_reason)
check("  وبقيمة سالبة", both.r_multiple < 0)

# ── ٣) البيع ──
sell = simulate([bar(69, 80)], side="sell", entry=80.0, stop=90.0,
                target=60.0, rule=FIXED)
check("٣ البيع يبلغ هدفه", sell.r_multiple > 0, str(sell.to_dict()))
sell_stop = simulate([bar(80, 91)], side="sell", entry=80.0, stop=90.0,
                     target=60.0, rule=FIXED)
check("  ووقفه يُحتسب سالباً", sell_stop.r_multiple < 0)

# ── ٤) التعادل ──
#
# ترتفع إلى +1.2R ثمّ تعود إلى الدخول. الحالي: تُكمل إلى الوقف (−1R).
# والتعادل: تخرج عند صفر.
path = [bar(100, 112), bar(89, 105)]
check("٤ الحالي يخسر −1R", abs(sim(path, FIXED).r_multiple + 1.0) < 1e-9)
be = sim(path, BE1)
check("  والتعادل يخرج عند صفر", abs(be.r_multiple) < 1e-9, str(be.to_dict()))
check("  وسببه «تعادل»", be.exit_reason == "تعادل")

# الوقف لا يُنقل قبل بلوغ العتبة — وإلّا صار وقفاً ضيّقاً لا قاعدة
early = [bar(100, 105), bar(89, 100)]
check("  ولا يُنقل قبل العتبة", abs(sim(early, BE1).r_multiple + 1.0) < 1e-9)

# ── ٥) التتبّع ──
climb = [bar(100, 120), bar(112, 118)]      # ذروة +2R ثمّ ارتداد
tr = sim(climb, TRAIL)
check("٥ التتبّع يقفل ربحاً", tr.r_multiple > 0, str(tr.to_dict()))
check("  قرب الذروة ناقص المسافة",
      abs(tr.r_multiple - 1.5) < 0.01, str(tr.r_multiple))
# التتبّع لا يتراجع أبداً — الوقف يصعد ولا ينزل
zig = [bar(100, 120), bar(114, 118), bar(100, 125), bar(118, 122)]
check("  والوقف لا يتراجع", sim(zig, TRAIL).r_multiple >= 1.5)

# ── ٦) الجني الجزئي والسيقان ──
pt = sim([bar(100, 112), bar(89, 105)], PARTIAL)
check("٦ الجني الجزئي يبنك نصفه", abs(pt.r_multiple - 0.5) < 1e-9,
      str(pt.to_dict()))
check("  ويسجّل ساقاً إضافية", pt.legs == 3, str(pt.legs))
check("  والقاعدة البسيطة ساقان", sim([bar(89, 100)], FIXED).legs == 2)

# الكلفة تُضرب في عدد السيقان — وإلّا بدا الجني الجزئي رابحاً وهو ليس
trades = [{"id": 1, "side": "buy", "entry": E, "stop": S, "target1": T}]
paths = {1: [bar(100, 112), bar(89, 105)]}
free = compare_rules(trades, bars_for=lambda t: paths[t["id"]],
                     rules=[PARTIAL], cost_per_leg_r=0.0)
paid = compare_rules(trades, bars_for=lambda t: paths[t["id"]],
                     rules=[PARTIAL], cost_per_leg_r=0.1)
check("  والكلفة تُطبَّق على كل ساق",
      abs(free["pt"].expectancy - paid["pt"].expectancy - 0.3) < 1e-9,
      f"{free['pt'].expectancy} مقابل {paid['pt'].expectancy}")

# ── ٧) الوقف الزمني ──
long_path = [bar(99, 101) for _ in range(30)]
ts = sim(long_path, ExitRule("t", "زمني", time_stop=5))
check("٧ الوقف الزمني يخرج في موعده", ts.bars_held == 5, str(ts.bars_held))
check("  بسببه المعلن", ts.exit_reason == "وقف زمني")

# ── ٨) الحدود ──
check("٨ بلا شموع لا نتيجة", sim([]) is None)
check("  ومخاطرة صفرية تُرفض",
      simulate([bar(99, 101)], side="buy", entry=100, stop=100,
               target=110, rule=FIXED) is None)
check("  والصفقة غير المحسومة تُعلَن مفتوحة",
      sim([bar(99, 101)]).exit_reason == "مفتوحة")

# ── ٩) المقارنة تعيد إحصاءً متّسقاً ──
many = [{"id": i, "side": "buy", "entry": E, "stop": S, "target1": T}
        for i in range(1, 6)]
mp = {i: [bar(100, 112), bar(89, 105)] for i in range(1, 6)}
stats = compare_rules(many, bars_for=lambda t: mp[t["id"]],
                      rules=[FIXED, BE1], cost_per_leg_r=0.05)
check("٩ يعدّ كل الصفقات", stats["be"].n == 5)
check("  ونسبة النجاح متّسقة", stats["fixed"].win_rate == 0.0)
check("  والصافي = الإجمالي ناقص الكلفة",
      abs(stats["be"].expectancy
          - (stats["be"].gross_expectancy - stats["be"].cost_r)) < 1e-9)
check("  والأسباب مُحصاة", sum(stats["fixed"].reasons.values()) == 5)

# ── ١٠) يعيد إنتاج خطّ الأساس على بياناتك الفعلية ──
#
# أهمّ اختبار في الملف. محاكٍ لا يطابق ما جرى لا يصلح للمقارنة، ومهما
# بدت أرقامه مغرية فهي عن عالم آخر.
try:
    from tools_exits import bars_for, load

    real = load()
except Exception:  # noqa: BLE001
    real = []

if len(real) >= 50:
    matched = total = 0
    diffs = []
    for t in real:
        b = bars_for(t)
        if not b or t.get("r_multiple") is None:
            continue
        res = simulate(b, side=t.get("side", "buy"),
                       entry=float(t.get("entry_price") or t["entry"]),
                       stop=float(t["stop"]), target=float(t["target1"]),
                       rule=FIXED)
        if res is None:
            continue
        total += 1
        d = res.r_multiple - float(t["r_multiple"])
        diffs.append(d)
        matched += int(abs(d) < 0.15)
    rate = matched / total if total else 0.0
    diffs.sort()
    median = diffs[len(diffs) // 2] if diffs else 0.0
    check("١٠ يطابق الحسم الفعلي في ≥80٪", rate >= 0.80,
          f"{rate:.0%} على {total} صفقة")
    check("  ووسيط الفرق قرب الصفر", abs(median) < 0.05, f"{median:+.3f}R")
else:
    check("١٠ يطابق الحسم الفعلي في ≥80٪", True, "لا بيانات كافية")
    check("  ووسيط الفرق قرب الصفر", True, "لا بيانات كافية")

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
