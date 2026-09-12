# -*- coding: utf-8 -*-
"""امتداد فيبوناتشي المبني على الاتجاه — الصيغة وحدودها.

═══ ما تقوله المصادر وما لا تقوله ═══

الأداة تُرسم بثلاث نقاط: قاع الموجة، وقمّتها، وقاع التصحيح.
والمستوى ‎= P3 + (P2 − P1) × النسبة‎.

وهي أداةُ **أهداف** — والمصدر يقول ذلك صراحةً. فيُطلَب هنا ألّا
تُضيف نقطةً واحدة إلى التقييم: مؤشّرٌ يُرسم في الشاشة يُفترَض
أنّه يؤثّر، وسكوتُ الكود يجعله يؤثّر بلا قياس.

═══ وأكبر عيوبها: ذاتيّة اختيار النقاط ═══

المصدر يضعه أوّل العيوب: متداولان يختاران محورين مختلفين
فيحصلان على مستوياتٍ مختلفة. وهنا القاعدة **واحدة ومكتوبة**،
فتُختبَر: هل ترفض ما يجب رفضه، وبسببٍ مسمّى؟

═══ والثالث: إعادة الرسم ═══

المحاور مؤكَّدة بنافذةٍ على الجانبين. فتُغيَّر الشمعة الجارية
ويُطلَب ألّا يتغيّر شيء.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.indicators import fib_extension as fx     # noqa: E402
from scanner.strategies import pes                     # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ═══ ١) الصيغة — على أرقامٍ تُحسب باليد ═══
#
# ‏P1=100، P2=200، P3=150 → الموجة ١٠٠، والامتداد من ١٥٠.
lv = {x["ratio"]: x["price"] for x in fx.levels_from(100, 200, 150)}
check("١ ‎1.0‎ = 150 + 100×1 = 250", lv[1.0] == 250.0, str(lv[1.0]))
check("  ‎1.618‎ = 311.8", abs(lv[1.618] - 311.8) < 1e-6, str(lv[1.618]))
check("  ‎0.618‎ = 211.8", abs(lv[0.618] - 211.8) < 1e-6, str(lv[0.618]))
check("  ‎2.618‎ = 411.8", abs(lv[2.618] - 411.8) < 1e-6, str(lv[2.618]))
# ═══ ليست ارتداداً ولا امتداداً بنقطتين ═══
#
# الارتداد يضع مستوياته **بين** النقطتين، وهذه تضعها فوق P3
# بمقدار الموجة. فلو خُلط الاثنان لجاء ‎1.0‎ عند ٢٠٠ لا ٢٥٠.
check("  وليست ارتداداً (‎1.0‎ ≠ P2)", lv[1.0] != 200.0)
check("  والإسقاط من P3 لا من P1",
      lv[1.0] == 150 + (200 - 100))


# ═══ ٢) شروط الصحّة تَرفض بسببٍ مسمّى ═══
def _frame(prices) -> pd.DataFrame:
    n = len(prices)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    c = np.asarray(prices, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.002, "low": c * 0.998,
                         "close": c, "volume": np.full(n, 1e3)}, index=idx)


# ═══ لماذا يبدأ التركيب بهبوط ═══
#
# النسخة الأولى بدأت بارتفاعٍ رتيب إلى P1 — فلم يتكوّن قاعٌ هناك
# أصلاً: ``pivot_low`` يشترط شمعاتٍ أدنى على اليسار، وأدنى نقطةٍ في
# ارتفاعٍ رتيب هي أوّل الشمعات، وهي مستبعَدة صراحةً.
#
# ثمّ ذُيِّل التركيب بمنطقةٍ مسطّحة ذات ضجيج — فتكوّنت فيها محاورُ
# صغيرة صارت هي الثلاثة الأخيرة، فجاء ‎P3 ≤ P1‎ ورُفض التركيب
# «السليم». والرفض كان صحيحاً: التركيب هو الذي كان معطوباً.
#
# فالشكل الصحيح: هبوطٌ يصنع P1 قاعاً حقيقياً، ثمّ صعودٌ إلى P2،
# ثمّ تصحيحٌ إلى P3، ثمّ ارتفاعٌ قصير **رتيب** يؤكّد P3 ولا يصنع
# محاور جديدة.

def _leg(p1=100.0, top=140.0, p3=120.0, pre=60, up=70, down=50, tail=18):
    """هبوطٌ إلى P1 ← صعودٌ إلى P2 ← تصحيحٌ إلى P3 ← ارتفاعٌ يؤكّده."""
    a = np.linspace(p1 * 1.30, p1, pre)
    b = np.linspace(p1, top, up)
    c = np.linspace(top, p3, down)
    d = np.linspace(p3, p3 * 1.02, tail)
    return _frame(np.concatenate([a, b, c, d]))


good = fx.find_swings(_leg())
check("٢ الموجة السليمة تُقبل", good.ok, good.why)
if good.ok:
    check("  والنقاط بالترتيب", good.p1 < good.p3 < good.p2,
          f"{good.p1:.1f} · {good.p3:.1f} · {good.p2:.1f}")
    check("  والتصحيح ضمن الحدّين",
          0.236 <= good.retracement <= 0.886, str(good.retracement))

# ‏P3 تحت P1: الموجة كُسرت — انعكاسٌ لا تصحيح
broken = fx.find_swings(_leg(p1=100, top=140, p3=95))
check("  و‏P3 تحت P1 تُرفض", not broken.ok)
check("  بسببٍ مسمّى", "كسر بداية الموجة" in broken.why, broken.why)

# تصحيحٌ ضحل: توقّفٌ لا تصحيح
shallow = fx.find_swings(_leg(p1=100, top=140, p3=138))
check("  والتصحيح الضحل يُرفض", not shallow.ok)
check("  بسببه", "أقلّ من" in shallow.why, shallow.why)

# تصحيحٌ يبتلع الموجة
deep = fx.find_swings(_leg(p1=100, top=140, p3=101))
check("  والعميق يُرفض", not deep.ok)
check("  بسببه", "أُلغيت" in deep.why, deep.why)

# ولا تُرمى أبداً: الرفض قيمةٌ لا استثناء
check("  ولا يرمي بل يعلّل", all(isinstance(s.why, str) and s.why
                                 for s in (broken, shallow, deep)))


# ═══ ٣) لا إعادة رسم ═══
base = _leg()
alt = base.copy()
alt.iloc[-1, alt.columns.get_loc("close")] *= 1.30
alt.iloc[-1, alt.columns.get_loc("high")] *= 1.30
a, b = fx.find_swings(base), fx.find_swings(alt)
check("٣ الشمعة الجارية لا تغيّر النقاط",
      (a.p1, a.p2, a.p3) == (b.p1, b.p2, b.p3))
src = (ROOT / "scanner" / "indicators"
       / "fib_extension.py").read_text(encoding="utf-8")
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
check("  والشمعة الجارية تُسقَط", "def _closed" in code
      and "iloc[:-1]" in code)
# والمحاور نفسها مؤكَّدة بنافذة يمنى — لا محور في آخر ``right`` شمعة
pine = (ROOT / "scanner" / "indicators" / "pine.py").read_text(
    encoding="utf-8")
check("  والمحور يحتاج شموعاً بعده", "ok[n - right:] = False" in pine)


# ═══ ٤) موضع السعر ومانع المطاردة ═══
m = fx.measure(_leg())
check("٤ يُحسب الموضع", m.get("ok") is True, m.get("why", ""))
if m.get("ok"):
    check("  والهدف التالي فوق السعر",
          m["next_level"] is None
          or m["next_level"]["price"] > m["close"])
    check("  والمسافة موجبة",
          m["room_pct"] is None or m["room_pct"] >= 0)
    # سعرٌ عند ‎P3‎ لم يبدأ الحركة بعد
    check("  والمرحلة صفر قبل الانطلاق", m["stage"] == 0.0, str(m["stage"]))
    check("  وغير ممتدّ", m["extended"] is False)

# سعرٌ فوق ‎1.618‎ يُعلَن ممتدّاً
tall = _leg(p1=100, top=140, p3=120)
lvl = fx.levels_from(good.p1, good.p2, good.p3) if good.ok else []
if lvl:
    ext = next(x["price"] for x in lvl if x["ratio"] == 1.618)
    pushed = tall.copy()
    pushed.iloc[-30:, pushed.columns.get_loc("close")] = ext * 1.05
    pushed.iloc[-30:, pushed.columns.get_loc("high")] = ext * 1.06
    mp = fx.measure(pushed)
    check("  والسعر فوق ‎1.618‎ يُعلَن ممتدّاً",
          (not mp.get("ok")) or mp["extended"] is True,
          str(mp.get("why") or mp.get("stage")))


# ═══ ٥) أداةُ أهداف — لا تُضيف نقطة ═══
pes_src = (ROOT / "scanner" / "strategies" / "pes.py").read_text(
    encoding="utf-8")
p = pes.load_params()
check("٥ مجموع الأوزان ما زال ١٠٠", sum(p["weights"].values()) == 100,
      str(sum(p["weights"].values())))
check("  ولا وزن لفيب", not any("fib" in k for k in p["weights"]),
      str(list(p["weights"])))
check("  ولا عامل fib في التقييم",
      "_f_fib" not in pes_src and '"fib_extension"' not in
      str(list(pes.FAMILY)))
check("  وليست في العائلات", "fib" not in " ".join(pes.FAMILY))

# تدخل من بابين فقط: رفضٌ في مانع المطاردة، وهدفٌ في التصنيف
pcode = "\n".join(l for l in pes_src.splitlines()
                  if not l.strip().startswith("#"))
ac = pcode.split("def already_expanded")[1].split("\ndef ")[0]
check("  وتدخل مانع المطاردة", "fib_extension" in ac)
check("  والرفض يُقال بنصّه", "تجاوز امتداد فيب" in pes_src)
cl = pcode.split("def classify")[1]
check("  والهدف في التصنيف", 'fx.measure' in cl)
# ولا تُغيّر الحالة: التصنيف يُقرَّر قبلها
check("  ولا تغيّر الحالة",
      cl.index("state, why = ") < cl.index("fx.measure"))


# ═══ ٦) كل حدٍّ في الملفّ ═══
raw = yaml.safe_load((ROOT / "config" / "pes.yaml").read_text(
    encoding="utf-8"))
fe = raw.get("fib_extension") or {}
for k in ("min_retracement", "max_retracement", "min_leg_atr",
          "extended_ratio", "confluence_pct", "anti_chasing"):
    check(f"٦ {k} في الملفّ", k in fe)
# والتجاوز يسري
check("  والتجاوز يسري",
      fx._cfg({"fib_extension": {"extended_ratio": 2.0}},
              "extended_ratio") == 2.0)
check("  وما لم يُذكر يرتدّ للافتراضي",
      fx._cfg({"fib_extension": {}}, "min_leg_atr") == 2.0)
# ويمكن تعطيل الرفض بلا تعطيل العرض
check("  والرفض قابل للإطفاء", fe.get("anti_chasing") is True
      and "anti_chasing" in ac)


# ═══ ٧) الرسم في طبقةٍ تُطفأ ═══
views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
check("٧ يُرسَم على الشارت", '"fib_ext"' in views)
check("  والنقاط الثلاث موصولة", '"p1_at", "p1"' in views)
tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "symbol.html").read_text(encoding="utf-8")
check("  وله زرّ طبقة", 'data-layer="fib_ext"' in tpl)
# ═══ الزرّ مصدر الحقيقة ═══
#
# كانت ‎hidden‎ تبدأ فارغة، فطبقةٌ زرُّها غير مفعَّل تُرسم رغم ذلك:
# الزرّ يقول «مطفأة» والشارت يعرضها.
check("  وحالته تُقرأ من الـDOM", 'classList.contains("active")' in tpl)
check("  وفشل الرسم لا يُسقط الشارت", "تعذّر رسم امتداد فيب" in views)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
