# -*- coding: utf-8 -*-
"""‏StochRSI و MACD — الحساب والعرض وحدود ما يدّعيانه.

═══ ثلاثة أعطال تُنتج شاشةً تبدو سليمة ═══

**ستوكاستيك السعر باسم StochRSI.** الخطأ الشائع: يُحسب ستوكاستيك
على السعر ويُسمّى ‏StochRSI. والرسم يبدو معقولاً تماماً — خطّان
يتذبذبان بين ٠ و١٠٠ — وهو مؤشّرٌ آخر. فيُقارَن هنا بحسابٍ مستقلّ
ويُطلَب أن يختلف عن ستوكاستيك السعر.

**إعادة الرسم.** الحساب على الشمعة الجارية يجعل التقاطع يظهر
ويختفي قبل الإغلاق: الاختبار الخلفي ممتاز والتطبيق عاجز. فيُغيَّر
إغلاق آخر شمعة ويُطلَب ألّا تتغيّر القراءة.

**‏NaN في JSON.** ‏``NaN`` الحرفية ليست JSON صالحاً، فيرفضها
``JSON.parse`` ويسقط **الرسم كلّه** لا النقطة وحدها.

═══ وادّعاءٌ رابع ═══

مؤشّرٌ مرسوم في الصفحة يُفترَض أنّه يؤثّر في القرار. وهذان لم
يُقاسا على الصفقات بعد — فيُطلَب أن تقول الشاشة ذلك صراحةً، وألّا
يمسّا النقاط ولا التوصية.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.analysis.oscillators import build          # noqa: E402
from scanner.indicators.momentum import (                # noqa: E402
    OVERBOUGHT, OVERSOLD, macd_state, stoch_rsi, stoch_rsi_state,
)
from scanner.indicators.pine import rsi                  # noqa: E402
from scanner.indicators.trend import macd                # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def _series(n=400, seed=11):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1.2, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({
        "open": close, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": rng.uniform(1e3, 9e3, n),
    }, index=idx)


df = _series()
close = df["close"]
F = stoch_rsi(close)
M = macd(close)


# ═══ ١) الحساب هو StochRSI لا ستوكاستيك السعر ═══
r = rsi(close, 14)
lo, hi = (r.rolling(14, min_periods=14).min(),
          r.rolling(14, min_periods=14).max())
k_ref = ((r - lo) / (hi - lo) * 100).rolling(3, min_periods=3).mean()
d_ref = k_ref.rolling(3, min_periods=3).mean()
check("١ ‎%K‎ يطابق حساباً مستقلّاً",
      float(np.nanmax(np.abs(F["k"] - k_ref))) < 1e-9)
check("  و‎%D‎ كذلك", float(np.nanmax(np.abs(F["d"] - d_ref))) < 1e-9)
check("  والمدى ٠–١٠٠", bool(F["k"].dropna().between(0, 100).all()))

# ولو حُسب على السعر لكان الارتباط ≈١
plo, phi = close.rolling(14).min(), close.rolling(14).max()
price_stoch = ((close - plo) / (phi - plo) * 100).rolling(3).mean()
corr = float(F["k"].corr(price_stoch))
check("  وليس ستوكاستيك السعر", corr < 0.95, f"الارتباط {corr:.3f}")

# ═══ حساب الإحماء ═══
#
# ‏RSI(14) أوّل قيمةٍ له عند الفهرس ١٤ (أي ١٤ فراغاً)، ثمّ نافذة
# ستوكاستيك ١٤ تضيف ١٣، ثمّ ‎%K‎ يضيف ٢، ثمّ ‎%D‎ يضيف ٢.
# فالمجموع ٣١ لا ٣٤: النوافذ المتتالية تتداخل عند حوافّها،
# وجمعُ أطوالها مباشرةً يبالغ في العدّ.
warm = int(F["d"].isna().sum())
check("  والإحماء ٣١ شمعة", warm == 14 + 13 + 2 + 2, str(warm))


# ═══ ٢) لا إعادة رسم ═══
#
# القراءة من ‎-2‎ لا ‎-1‎. فقفزة في الشمعة الجارية لا تحرّكها.
alt = df.copy()
alt.iloc[-1, alt.columns.get_loc("close")] *= 1.20
s_now, s_alt = stoch_rsi_state(F), stoch_rsi_state(stoch_rsi(alt["close"]))
check("٢ ‏StochRSI لا يعيد الرسم",
      (s_now["k"], s_now["d"], s_now["cross"])
      == (s_alt["k"], s_alt["d"], s_alt["cross"]))
m_now, m_alt = macd_state(M), macd_state(macd(alt["close"]))
check("  و MACD كذلك",
      (m_now["hist"], m_now["cross"]) == (m_alt["hist"], m_alt["cross"]))

src = (ROOT / "scanner" / "indicators" / "momentum.py").read_text(
    encoding="utf-8")
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
check("  والقراءة من ‎-2‎ لا ‎-1‎",
      'iloc[-2]' in code and 'iloc[-1]' not in code)


# ═══ ٣) المقام صفراً لا يُنتج ‎inf‎ ═══
#
# سلسلة ثابتة ← ‎hi == lo‎. والقسمة تعطي ‎inf‎ أو ‎nan‎ حسب البسط،
# ولا معنى لموضعٍ ضمن مدىً معدوم — فالصواب ‎NaN‎ لا صفر ولا مئة.
flat = pd.Series([50.0] * 120)
Ff = stoch_rsi(flat)
check("٣ السلسلة الثابتة ← NaN", bool(Ff["k"].isna().all()))
check("  ولا قيم لا نهائية", not bool(np.isinf(Ff["raw"].to_numpy()).any()))


# ═══ ٤) الخرج JSON صالح — بلا NaN ═══
out = build(df, since_ts=int(df.index[-200].timestamp()))
check("٤ يُبنى بنجاح", out.get("ok") is True, str(out.get("reason")))
try:
    json.dumps(out, ensure_ascii=False, allow_nan=False)
    ok_json = True
except ValueError as exc:
    ok_json, err = False, str(exc)[:60]
check("  و JSON بلا NaN", ok_json, "" if ok_json else err)

s, m = out["stoch_rsi"], out["macd"]
check("  والنافذة مقصوصة", len(s["k"]) <= 200 and len(s["k"]) > 150,
      str(len(s["k"])))
# القصّ بعد الحساب لا قبله: أوّل نقطة في النافذة يجب أن تكون محسوبة
check("  وأوّل نقطة محسوبة", bool(s["k"]) and s["k"][0]["value"] is not None)
check("  والحدود مذكورة",
      s["overbought"] == OVERBOUGHT and s["oversold"] == OVERSOLD)


# ═══ ٥) لون المدرّج يفرّق التمدّد عن التقلّص ═══
#
# أربع حالات لا اثنتان: التقلّص فوق الصفر يعني زخماً صاعداً يخفّ،
# وهو ما يسبق التقاطع. ولونٌ واحد للجانب يخفيه.
colors = {h["color"] for h in m["hist"]}
check("٥ أربعة ألوان للمدرّج", len(colors) == 4, str(len(colors)))


# ═══ ٦) نافذة قصيرة تُرفَض بسببها لا تُخترَع ═══
short = build(_series(n=20))
check("٦ يرفض النافذة القصيرة", short.get("ok") is False)
check("  ويقول العدد المطلوب", "34" in str(short.get("reason")))


# ═══ ٧) عرضٌ لا قرار ═══
check("٧ يُعلَن أنّه خارج التقييم", out.get("scored") is False)
check("  والنصّ صريح", "لا يدخلان" in str(out.get("disclaimer")))

osc_src = (ROOT / "scanner" / "analysis" / "oscillators.py").read_text(
    encoding="utf-8")
# لا يستورد التقييم ولا يمسّه
check("  ولا يستورد scoring",
      "scoring" not in osc_src and "recommendation" not in osc_src)

# والوحدة لا تُستدعى من مسار التقييم أصلاً
scoring_files = list((ROOT / "scanner").rglob("scoring*.py")) + \
    list((ROOT / "scanner" / "strategies").glob("*.py"))
leaked = [p.name for p in scoring_files
          if "momentum" in p.read_text(encoding="utf-8")
          and "oscillators" in p.read_text(encoding="utf-8")]
check("  ولا يدخل الاستراتيجيات", not leaked, str(leaked))

tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "symbol.html").read_text(encoding="utf-8")
check("  والشاشة تعرض التنويه", "osc-note" in tpl)


# ═══ ٨) اللوحتان مربوطتان بمحور السعر ═══
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "oscillators.js").read_text(encoding="utf-8")
check("٨ يشترك في تغيّر النطاق",
      "subscribeVisibleLogicalRangeChange" in js)
check("  ويلغي الاشتراك عند الهدم",
      "unsubscribeVisibleLogicalRangeChange" in js)
# بلا حارس يبثّ المستقبِل بدوره فيعود إلى الأوّل — حلقة تجمّد الصفحة
check("  وبحارسٍ ضدّ الحلقة", "applying" in js)
check("  ويربط شارت السعر", "chartOf" in js)
chart_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
            / "chart.js").read_text(encoding="utf-8")
check("  و chartOf معرَّف", "chartOf: chartOf" in chart_js)
# الرسم يهدم الشارت ويبنيه مع كل تبديل طبقة — فالربط بعده لا قبله
check("  واللوحتان تُرسمان بعد الشارت",
      tpl.index('AnalysisChart.render("chart"')
      < tpl.index("Oscillators.render"))
check("  والقديم يُهدم قبل الجديد", "destroy();" in js)

# غياب الملفّ لا يُسقط الشارت
check("  وغيابه لا يُسقط الرسم", "typeof window.Oscillers" in tpl
      or 'typeof window.Oscillators !== "undefined"' in tpl)


# ═══ ٩) الواجهة البرمجية تمرّرهما بلا أن تُسقط الصفحة ═══
views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
check("٩ ‏api_chart يمرّر oscillators", '"oscillators"' in views)
# النافذة من أوّل شمعة في المخرَج لا من max_bars — overlay يوسّعها
check("  والنافذة من الشموع لا مخمَّنة",
      'payload.get("candles")' in views and "since_ts=_first" in views)
tree = ast.parse(views)
check("  وفشله لا يُسقط الصفحة",
      "تعذّر حساب لوحتي الزخم" in views)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
