# -*- coding: utf-8 -*-
"""اختبارات نموذج التنفيذ — بلا Django ولا شبكة.

الوحدة صغيرة لكن أثرها أكبر من أي ملف آخر: هي التي تحوّل كل رقم في
المشروع من إجمالي إلى صافٍ. خطأ فيها لا يظهر كعُطل بل كقرار خاطئ.

    python tests_execution.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import execution as ex

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


def near(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ══════════════════════ الحساب الأساسي

m = ex.CostModel(maker_bps=10, taker_bps=10, slippage_scale=0,
                 spread_scale=0)
check("الأمر المحدَّد يدفع العمولة وحدها", near(m.leg_bps("maker"), 10))
check("وأمر السوق مثلها بلا انزلاق مقدَّر", near(m.leg_bps("taker"), 10))
check("والرحلة ضعف الساق", near(m.round_trip_bps("high"), 20))

full = ex.CostModel()
check("الانزلاق يزيد مع ضعف السيولة",
      full.leg_bps("taker", "micro") > full.leg_bps("taker", "high"))
check("والمجهول يُعامل كالأسوأ لا كالأفضل",
      full.leg_bps("taker", "unknown") >= full.leg_bps("taker", "low"),
      "تجميل المجهول يجعل الرموز الغامضة تبدو أرخص من الواضحة")
check("والوقف أغلى من أمر سوق عادي",
      full.leg_bps("stop", "micro") > full.leg_bps("taker", "micro"),
      "الوقف يُضرب في حركة أحادية الاتجاه")
check("وفئة غير معروفة لا تُسقط الحساب",
      full.leg_bps("taker", "فئة-غريبة") == full.leg_bps("taker", "unknown"))

# ══════════════════════ القسمة على المخاطرة — جوهر الوحدة

# 20 نقطة أساس = 0.2% ؛ على وقف 2% تساوي 0.10R
check("الكلفة بالـR = الكلفة% ÷ الوقف%",
      near(m.cost_in_r(2.0, "high"), 0.10), m.cost_in_r(2.0, "high"))
check("ووقف نصف العرض يضاعف العبء",
      near(m.cost_in_r(1.0, "high"), 0.20))
check("ووقف عُشر العرض يعشّره",
      near(m.cost_in_r(0.2, "high"), 1.00),
      "هنا تُبتلع الخطة كاملةً — وهذا ما حدث فعلاً")

# العلاقة عكسية صارمة: أي كسر لها يعني خطأ في القسمة
wide, narrow = m.cost_in_r(4.0, "mid"), m.cost_in_r(0.5, "mid")
check("العلاقة عكسية مع عرض الوقف", narrow > wide * 7, f"{narrow:.3f} vs {wide:.3f}")
check("ووقف صفر أو سالب لا يقسم على صفر",
      m.cost_in_r(0.0, "high") == 0.0 and m.cost_in_r(-1, "high") == 0.0)

check("الخروج الجزئي ساق إضافية لا مجانية",
      full.cost_in_r(2.0, "mid", legs=3) > full.cost_in_r(2.0, "mid", legs=2),
      "الجني الجزئي يخرج مرّتين فيدفع مرّتين")
check("وساقان هما الافتراض",
      near(full.cost_in_r(2.0, "mid", legs=2),
           full.cost_in_r(2.0, "mid")))

check("الصافي = الإجمالي − الكلفة",
      near(m.net_r(2.0, 2.0, "high"), 1.90), m.net_r(2.0, 2.0, "high"))
check("والخسارة تزداد بالكلفة لا تنقص",
      m.net_r(-1.0, 2.0, "high") < -1.0)

check("نموذج بلا تكلفة يعيد الإجمالي كما هو",
      near(ex.FREE.net_r(1.7, 0.3, "micro"), 1.7),
      "لازم لإظهار الفرق صراحةً بدل إخفائه")

# ══════════════════════ الاستقلال عن الاستراتيجية

src = (ROOT / "scanner" / "execution.py").read_text(encoding="utf-8")
for forbidden in ("recommend", "scoring", "breakout", "analysis"):
    check(f"لا يستورد {forbidden} (الكلفة خاصية سوق لا إشارة)",
          f"import {forbidden}" not in src and f"from .{forbidden}" not in src)
check("ولا يعرف Django", "django" not in src.lower())
check("والنموذج ثابت بعد الإنشاء (قابل للأرشفة مع التجربة)",
      getattr(ex.CostModel, "__dataclass_params__").frozen)

# ══════════════════════ الحساسية

rows = [{"r_multiple": 2.0, "risk_pct": 2.0, "liquidity": "mid"},
        {"r_multiple": -1.0, "risk_pct": 2.0, "liquidity": "mid"},
        {"r_multiple": 2.0, "risk_pct": 2.0, "liquidity": "mid"}]
table = ex.sensitivity(rows)
check("الجدول يعطي صفاً لكل تقدير", len(table) == 5, len(table))
check("وأولها بلا تكلفة يساوي الإجمالي",
      near(table[0]["expectancy"], 1.0), table[0]["expectancy"])
check("والتوقّع ينخفض كلما ارتفع التقدير",
      all(table[i]["expectancy"] > table[i + 1]["expectancy"]
          for i in range(len(table) - 1)),
      [round(t["expectancy"], 3) for t in table])
check("وعدد الصفقات لا يتغيّر بين الصفوف",
      len({t["trades"] for t in table}) == 1)
check("وصفوف بلا r_multiple تُتجاهل لا تُسقط",
      ex.sensitivity([{"risk_pct": 1.0}])[0]["trades"] == 0)
check("وقائمة فارغة لا تنهار", len(ex.sensitivity([])) == 5)

check("نقطة التعادل تُحسب بالاتجاه الصحيح",
      near(ex.breakeven_bps(0.20, 1.19), 23.8), ex.breakeven_bps(0.20, 1.19))
check("وتوقّع سالب يعطي صفراً لا رقماً سالباً",
      ex.breakeven_bps(-0.3, 2.0) == 0.0)

# ══════════════════════ بوّابة الجدوى

v_tight = ex.viability(0.10, "micro")
v_wide = ex.viability(5.0, "high")
check("وقف 0.10% على سيولة دقيقة يُرفض", not v_tight["ok"], v_tight["cost_r"])
check("ويُذكر السبب برقمه لا برسالة عامة",
      "0.10" in v_tight["reason"] and "R" in v_tight["reason"],
      v_tight["reason"])
check("ووقف 5% على سيولة عالية يُقبل", v_wide["ok"], v_wide["cost_r"])
# وقف 1% على سيولة دقيقة كلفته 0.75R — يُرفض عند 0.25 ويُقبل عند 0.95
check("الخطة نفسها تُرفض بحدّ صارم وتُقبل بحدّ متساهل",
      not ex.viability(1.0, "micro")["ok"]
      and ex.viability(1.0, "micro", max_ratio=0.95)["ok"],
      "الحدّ اختيار معلن لا قانون")
check("ونفس الوقف يُرفض على الضعيف ويُقبل على القوي",
      ex.viability(1.2, "micro")["ok"] is False
      and ex.viability(1.2, "high")["ok"] is True,
      "السيولة تدخل الحكم لا العرض وحده")

floor_micro = ex.min_risk_pct("micro")
floor_high = ex.min_risk_pct("high")
check("أضيق وقف مسموح أوسع على السيولة الضعيفة",
      floor_micro > floor_high, f"{floor_micro:.2f}% vs {floor_high:.2f}%")
check("وهو متّسق مع البوّابة نفسها",
      ex.viability(floor_micro * 1.01, "micro")["ok"]
      and not ex.viability(floor_micro * 0.99, "micro")["ok"])

# ══════════════════════ تأخير التنفيذ

bars = [{"open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5}]
check("التنفيذ عند افتتاح الشمعة التالية لا إغلاق شمعة القرار",
      ex.delayed_fill(bars, 100.0) == 101.0,
      "سعر الإغلاق مضى حين رأيته")
check("وبلا شمعة تالية لا تنفيذ", ex.delayed_fill([], 100.0) is None)
check("وشمعة بلا افتتاح ترجع لسعر القرار",
      ex.delayed_fill([{"high": 1}], 100.0) == 100.0)

gap = ex.gap_cost_r(101.0, 100.0, 2.0, "buy")
check("فجوة صاعدة تكلّف المشتري", gap > 0 and near(gap, 0.5), gap)
check("ونفسها تفيد البائع", ex.gap_cost_r(101.0, 100.0, 2.0, "sell") < 0)
check("ومخاطرة صفر لا تقسم على صفر",
      ex.gap_cost_r(101.0, 100.0, 0.0, "buy") == 0.0)

# ══════════════════════ الربط بالمخطط والمحرّك

from scanner import settings_schema as S
for key in ("maker_bps", "taker_bps", "slippage_scale", "max_cost_ratio"):
    check(f"الإعداد {key} معرَّف", key in S.FIELDS)
check("وبوّابة الجدوى قابلة للتعطيل بصفر",
      S.FIELDS["max_cost_ratio"].minimum == 0)

trades_src = (ROOT / "web" / "dashboard" / "trades.py").read_text("utf-8")
check("والبوّابة مطبَّقة على التوصيات", "_viability(plan, result_row)" in trades_src)
check("وعلى الاختراقات أيضاً",
      trades_src.count("_viability(") >= 3)
check("وفشلها لا يمنع تسجيل الصفقة (ميزة لا شرط تشغيل)",
      "return {\"ok\": True" in trades_src)

bin_src = (ROOT / "scanner" / "adapters" / "binance.py").read_text("utf-8")
check("والعملات المربوطة المكتشفة أُضيفت للاستبعاد",
      "BFUSD" in bin_src, "أصدر المحرّك خطة عليها بوقف 0.01%")


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
