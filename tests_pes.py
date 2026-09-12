# -*- coding: utf-8 -*-
"""‏PES — العائلات، ومانع المطاردة، والاختراق بالجسم لا بالفتيل.

═══ ما قِيس على التاريخ قبل اعتمادها ═══

‏١٤ رمزاً · أفق ١٢ شمعة (4H) · تمدّد ≥ ٣× ATR::

    تمدّد في أيّ اتجاه            تمدّد صعوداً فقط
    ────────────────────        ────────────────────
    0–39    42.9٪  -11.8 ▼      0–39    13.2٪   -4.6 ▼
    40–54   56.3٪   +1.6        40–54   18.8٪   +1.0
    55–64   65.8٪  +11.1 ★      55–64   22.3٪   +4.5
    65–74   65.3٪  +10.6 ★      65–74   16.6٪   -1.2 ▼
    75–100  75.8٪  +21.1 ★      75–100  37.1٪  +19.3 ★
    الأساس  54.7٪                الأساس  17.8٪

والخلاصة التي تغيّر الاستعمال: **صعوداً**، لا يتجاوز الأساس إلّا
شريحة ‎75+‎ — وهي عتبة ‏PRE_BREAKOUT نفسها. أمّا شريحة ‏WATCH
(‎65–74‎) فدون الأساس.

فالاستراتيجية تعمل عند عتبتها، و«للمراقبة» ليست إشارة شراء.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.indicators import trend  # noqa: E402
from scanner.strategies import pes  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def frame(close, vol=None, n=None):
    c = np.asarray(close, dtype=float)
    v = np.asarray(vol if vol is not None else np.ones(len(c)), dtype=float)
    idx = pd.date_range("2026-01-01", periods=len(c), freq="4h", tz="UTC")
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": v}, index=idx)


# ═══ ١) الميل يفرّق بين البداية والنضج ═══
#
# ‎18→26‎ اتجاهٌ يتكوّن، و‎42→47‎ اتجاهٌ نضج. والقيمة وحدها لا
# تفرّق: كلتاهما «فوق ٢٥».
young = trend.slope(pd.Series([18, 20, 23, 26.0]), 4)
mature = trend.slope(pd.Series([42, 45, 47.0]), 3)
check("١ الميل يميّز البداية", young > mature, f"{young} مقابل {mature}")
check("  والهابط سالب", trend.slope(pd.Series([26, 23, 20, 18.0]), 4) < 0)
check("  والثابت صفر", abs(trend.slope(pd.Series([20.0] * 6), 5)) < 1e-9)
# الميل مطبَّع: يُقارَن بين رمزٍ ADX له 20 وآخر له 50
big = trend.slope(pd.Series([200, 220, 230, 260.0]), 4)
check("  ومطبَّع على المقياس", abs(big - young) < 0.05,
      f"{big} مقابل {young}")


# ── ٢) المؤشّرات تُحسب ──
rng = np.random.default_rng(3)
df = frame(100 + np.cumsum(rng.normal(0, 1, 300)),
           vol=rng.uniform(80, 120, 300))
a = trend.adx(df)
check("٢ ADX في مداه",
      0 <= float(a["adx"].dropna().iloc[-1]) <= 100,
      str(a["adx"].dropna().iloc[-1]))
check("  و DI موجبان",
      float(a["plus_di"].dropna().iloc[-1]) >= 0
      and float(a["minus_di"].dropna().iloc[-1]) >= 0)
m = trend.macd(df["close"])
check("  والمدرَّج = الخطّ − الإشارة",
      abs(float(m["hist"].iloc[-1])
          - (float(m["macd"].iloc[-1]) - float(m["signal"].iloc[-1]))) < 1e-9)
st = trend.supertrend(df)
check("  و Supertrend اتجاهه ±1",
      set(np.unique(st["direction"].to_numpy())) <= {1.0, -1.0})


# ═══ ٣) الشمعة الجارية مستبعَدة ═══
#
# قيمها تتغيّر حتى تُغلق. وبناء قرارٍ عليها يجعل الاختبار الخلفي
# ممتازاً والتطبيق عاجزاً.
src = (ROOT / "scanner" / "strategies" / "pes.py").read_text(encoding="utf-8")
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
check("٣ تُسقَط الشمعة الجارية", "df.iloc[:-1]" in code)
check("  ويُستعمل في كل عامل", code.count("_closed(") >= 10,
      str(code.count("_closed(")))


# ═══ ٤) العائلات — المادّة ١٧ ═══
#
# ‏EMA و Supertrend و ADX ثلاثتها «اتجاه». واجتماعها إشارةٌ واحدة
# بثلاثة أسماء لا ثلاث إشارات.
fams = set(pes.FAMILY.values())
check("٤ ستّ عائلات", len(fams) == 6, str(fams))
check("  والاتجاه يضمّ ADX", pes.FAMILY["adx"] == "trend")
check("  والزخم يضمّ RSI و MACD",
      pes.FAMILY["rsi"] == pes.FAMILY["macd"] == "momentum")
check("  والحجم يضمّ OBV", pes.FAMILY["obv"] == "volume")
check("  ولكل عائلة اسم عربي",
      set(pes.FAMILY_LABELS) >= fams)
p = pes.load_params()
check("  والأوزان مجموعها 100",
      abs(sum((p.get("weights") or {}).values()) - 100) < 1e-9,
      str(sum((p.get("weights") or {}).values())))
check("  والتنوّع شرطٌ للترقية",
      int((p.get("families") or {}).get("min_for_pre_breakout", 0)) >= 3)
check("  ويُطبَّق في التصنيف", "enough_families" in code)


# ═══ ٥) مانع المطاردة ═══
#
# عملةٌ ارتفعت ٣٠٪ أمس ليست «ما قبل الانفجار» مهما بلغت نقاطها.
# ═══ الشمعة الأخيرة تُسقَط — فالتركيبة تحتاج واحدةً زائدة ═══
#
# أوّل ما كتبتُ هنا وضعتُ القفزة في آخر صفّ، فأسقطها ``_closed``
# ولم تُرصد. وهذا دليلٌ على أنّ إسقاط الشمعة الجارية يعمل — لا
# على عطبٍ في المانع.
jumped = frame([100.0] * 250 + [100.0, 135.0, 135.0])
res = pes.already_expanded(jumped, None, p)
check("٥ القفزة اليومية تُرصد", res["expanded"], str(res))
check("  ويُقال سببها", bool(res["reasons"]))
calm = frame([100.0] * 260)
check("  والهادئة تمرّ", not pes.already_expanded(calm, calm, p)["expanded"])
# والتصنيف يوقفها قبل كل شيء
check("  والتصنيف يسبقه", 'if result.get("already_expanded")' in code)


# ═══ ٦) الاختراق بالجسم لا بالفتيل ═══
#
# فتيلٌ يخترق ثمّ يعود ليس اختراقاً بل رفضاً.
n = 60
base = [100.0] * n
# الشمعة المقصودة قبل الأخيرة: الأخيرة تُسقَط بوصفها جارية
def _shape(df, *, o, h, lo, c, v):
    j = -2
    for col, val in (("open", o), ("high", h), ("low", lo),
                     ("close", c), ("volume", v)):
        df.iloc[j, df.columns.get_loc(col)] = val
    return df


wick = _shape(frame(base, vol=[100.0] * n).copy(),
              o=100.0, h=120.0, lo=99.0, c=101.0, v=400.0)
bo = pes.breakout_check(wick, 100.5, p)
check("٦ الفتيل ليس اختراقاً", not bo["broke"], str(bo))
check("  ويُقال لماذا", "فتيل" in bo["why"] or "الجسم" in bo["why"],
      bo["why"])

solid = _shape(frame(base, vol=[100.0] * n).copy(),
               o=100.0, h=109.0, lo=99.5, c=108.0, v=400.0)
bo2 = pes.breakout_check(solid, 100.5, p)
check("  والجسم القويّ اختراق", bo2["broke"], str(bo2))
# وبحجمٍ ضعيف لا يُعدّ اختراقاً
weak = solid.copy()
weak.iloc[-2, weak.columns.get_loc("volume")] = 50.0
check("  والحجم الضعيف يمنعه",
      not pes.breakout_check(weak, 100.5, p)["broke"])


# ═══ ٧) ENTRY_READY تسلسلٌ لا لحظة ═══
#
# لا تُمنح إلّا لمن مرّ بالمراحل. ورمزٌ يظهر فجأةً «جاهزاً» ادّعاء.
check("٧ التصنيف يقرأ السابقة", "previous" in code and "previous in (" in code)
check("  و ENTRY_READY بعد إعادة اختبار",
      'state, why = "ENTRY_READY"' in code
      and "BREAKOUT_RETEST" in code)
scan_src = (ROOT / "scanner" / "strategies"
            / "pes_scan.py").read_text(encoding="utf-8")
check("  والحالة تُحفظ بين الدورات", "_previous_states" in scan_src)
check("  والمحظور لا يُقيَّم", "blocklist.is_blocked" in scan_src)


# ── ٨) سبب عدم الترقية يُقال ──
#
# «نقاطٌ عالية ومرحلةٌ منخفضة» بلا سبب تجعل العتبة تبدو معطّلة.
check("٨ يُذكر سبب البقاء في WATCH", "miss.append" in code)
check("  ومنه بُعد المقاومة", "المقاومة على بعد" in src)
check("  ومنه نقص العائلات", "العائلات" in src)


# ── ٩) الربط ──
cron = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
check("٩ مهمّة مجدولة", '"pes": _h_pes' in cron)
urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
check("  والمسارات", "api_pes" in urls and "pes_page" in urls)
html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "pes.html").read_text(encoding="utf-8")
check("  والصفحة تنفي الاحتمال", "ترتيبٌ لا احتمال" in html)
check("  وتشرح قاعدة العائلات", "ثلاث" in html and "عائلات" in html)
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "pes-page.js").read_text(encoding="utf-8")
check("  والواجهة تعرض العائلات", "famChips" in js)
check("  وتعرض الثقة المخفَّضة", "confidence" in js)
cfg = ROOT / "config" / "pes.yaml"
check("  والمعاملات في ملفّ", cfg.exists())
check("  وأداة القياس موجودة",
      (ROOT / "tools_pes_measure.py").exists())


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
