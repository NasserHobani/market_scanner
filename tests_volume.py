# -*- coding: utf-8 -*-
"""الفوليوم: VWAP وبروفايل الحجم و VSA — والمؤشّر المسمّى بغير اسمه.

═══ العطب المقيس ═══

كان في التقييم مكوّنٌ اسمه ``vwap`` بوزنٍ كامل، يُحسب هكذا::

    day = df.index.floor("D")        # الجلسة = يومٌ تقويميّ

وهذا صحيح داخل اليوم، وينهار على الفريم اليومي: كل شمعة جلسةٌ
وحدها، فيصير VWAP مساوياً لـ ``(H+L+C)/3`` **لتلك الشمعة**.

القياس على البيانات الفعلية::

    crypto 1d   VWAP == (H+L+C)/3 في 100.0٪ من الشموع
    saudi  1d   VWAP == (H+L+C)/3 في  95.6٪ من الشموع
    crypto 15m  VWAP == (H+L+C)/3 في   1.2٪ من الشموع

فالمكوّن لم يكن يقيس «أين السعر من متوسّط ما دفعه المتداولون» بل
«أين أغلق داخل مداه». وهذا أخطر من مؤشّر غائب: الغائب يُنتبه إليه،
والمسمّى بغير اسمه يُبنى عليه القرار. والسوق السعودي كلّه يُمسَح
على ``1d``.

═══ ولماذا VSA هنا ولا يدخل التقييم ═══

قِيست خصائص VSA على ١١٥ صفقة محسومة فكان حجم أثرها صفراً تقريباً
(‏vol_ratio d=−0.06 · range_ratio d=+0.02). و``above_vwap_20`` وحده
بلغ d=+0.65.

فهي تُحسب وتُعرَض ولا تُوزَن. وإضافتها إلى التقييم لأنّها «معروفة»
كانت ستُضعفه: كل مكوّنٍ جديد يخفّف وزن ما يعمل فعلاً.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scanner.indicators import volume as vol  # noqa: E402
from scanner.indicators import volume_profile as vp  # noqa: E402
from scanner.indicators import vsa  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def frame(n: int, freq: str, seed: int = 7) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq=freq, tz="UTC")
    rng = np.random.default_rng(seed)
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    op = base
    cl = base + rng.normal(0, 0.3, n)
    # الإغلاق **داخل** المدى دائماً — كما في أي شمعة حقيقية.
    # النسخة الأولى ولّدت إغلاقاً خارج المدى، فأسقطت فحص
    # ``close_pos`` بحقّ — وكشفت في الوقت نفسه أنّ الكود لم يكن
    # يحرس من شمعةٍ مشوّهة.
    hi = np.maximum(op, cl) + abs(rng.normal(0, 0.8, n))
    lo = np.minimum(op, cl) - abs(rng.normal(0, 0.8, n))
    return pd.DataFrame({
        "open": op, "high": hi, "low": lo, "close": cl,
        "volume": abs(rng.normal(1e6, 3e5, n)),
    }, index=idx)


def typical(df):
    return (df["high"] + df["low"] + df["close"]) / 3.0


def pct_equal_typical(series, df) -> float:
    return float(np.isclose(series.to_numpy(float), typical(df).to_numpy(float),
                            equal_nan=True).mean() * 100.0)


# ── ١) العطب حقيقيّ: VWAP الجلسة ينهار على اليوميّ ──
daily = frame(300, "1D")
intraday = frame(300, "15min")

check("١ الجلسة تنهار على اليوميّ",
      pct_equal_typical(vol.session_vwap(daily), daily) > 95.0,
      f"{pct_equal_typical(vol.session_vwap(daily), daily):.1f}٪")
check("  وتعمل داخل اليوم",
      pct_equal_typical(vol.session_vwap(intraday), intraday) < 10.0,
      f"{pct_equal_typical(vol.session_vwap(intraday), intraday):.1f}٪")


# ── ٢) والذكيّ يعالجه ──
check("٢ الذكيّ لا ينهار على اليوميّ",
      pct_equal_typical(vp.smart_vwap(daily, 20), daily) < 5.0,
      f"{pct_equal_typical(vp.smart_vwap(daily, 20), daily):.1f}٪")
# وداخل اليوم يبقى VWAP الجلسة كما هو متعارف — لا يُغيَّر ما يعمل
check("  ويطابق الجلسة داخل اليوم",
      np.allclose(vp.smart_vwap(intraday, 20).to_numpy(float),
                  vol.session_vwap(intraday).to_numpy(float),
                  equal_nan=True))
# الاختيار من البيانات لا من اسم الفريم
check("  والقرار من شموع الجلسة لا من اسم الفريم",
      vp.bars_per_session(daily) == 1.0
      and vp.bars_per_session(intraday) == 96.0,
      f"{vp.bars_per_session(daily)} · {vp.bars_per_session(intraday)}")


# ── ٣) VWAP المتدحرج والمثبَّت ──
rv = vp.rolling_vwap(daily, 20)
check("٣ المتدحرج يعطي قيماً", np.isfinite(rv.iloc[-1]))
# محصور بين أدنى وأعلى سعر — متوسّطٌ لا يخرج عن مداه
check("  ومحصور في مدى السعر",
      float(daily["low"].min()) <= float(rv.iloc[-1]) <= float(daily["high"].max()))
# حجمٌ ثابت يجعل الموزون = المتوسّط الحسابي للسعر النموذجي
flat = daily.copy()
flat["volume"] = 1000.0
check("  وبحجم ثابت يساوي المتوسّط الحسابي",
      np.isclose(float(vp.rolling_vwap(flat, 20).iloc[-1]),
                 float(typical(flat).rolling(20).mean().iloc[-1])))

a = vp.anchor_swing(daily, 120, "low")
av = vp.anchored_vwap(daily, a)
check("  والمثبَّت يبدأ من المرساة", bool(np.isnan(av.iloc[max(0, a - 1)]))
      or a == 0)
check("  وقيمته عند المرساة = سعرها النموذجي",
      np.isclose(float(av.iloc[a]), float(typical(daily).iloc[a])))
check("  والمرساة عند أدنى قاع",
      a == int(daily.index.get_loc(daily.iloc[-120:]["low"].idxmin())))


# ── ٤) بروفايل الحجم ──
pr = vp.build(daily)
check("٤ يُبنى", pr is not None)
check("  والـPOC داخل المدى", pr.low <= pr.poc <= pr.high)
check("  ومنطقة القيمة تحوي الـPOC", pr.val <= pr.poc <= pr.vah)
check("  وأضيق من المدى الكامل", pr.value_width < (pr.high - pr.low))
check("  والموضع يُوصف بالعربية",
      pr.position(pr.high + 1) == "فوق منطقة القيمة"
      and pr.position(pr.low - 1) == "تحت منطقة القيمة"
      and pr.position(pr.poc) == "داخل منطقة القيمة")

# ═══ الحجم يُوزَّع على المدى لا يُوضع عند الإغلاق ═══
#
# شمعةٌ واحدة ضخمة الحجم عند سعرٍ واحد يجب أن تصنع الـPOC هناك.
spike = frame(200, "1D", seed=3)
spike.loc[spike.index[100], ["open", "high", "low", "close"]] = [50, 50.2, 49.8, 50]
spike.loc[spike.index[100], "volume"] = spike["volume"].sum() * 3
pr2 = vp.build(spike)
check("  والحجم الضخم يصنع الـPOC عنده",
      abs(pr2.poc - 50.0) < (pr2.high - pr2.low) * 0.12,
      f"POC={pr2.poc:.2f} والمتوقّع ~50")

check("  والإطار القصير يعيد None", vp.build(daily.head(3)) is None)
check("  والأعمدة الناقصة كذلك",
      vp.build(daily[["close"]]) is None)
# حجمٌ صفريّ لا يُنتج بروفايلاً كاذباً
zero = daily.copy()
zero["volume"] = 0.0
check("  والحجم الصفري كذلك", vp.build(zero) is None)


# ── ٥) VSA — تُحسب ولا تُوزَن ──
f = vsa.features(daily, 20)
for col in ("vol_ratio", "range_ratio", "close_pos", "spread_per_volume"):
    check(f"٥ يحسب {col}", col in f.columns)
check("  وموضع الإغلاق بين صفر وواحد",
      bool(((f["close_pos"].dropna() >= -1e-9)
            & (f["close_pos"].dropna() <= 1 + 1e-9)).all()))

# ═══ المتوسّط مزاحٌ بشمعة ═══
#
# متوسّطٌ يشمل الشمعة الحالية يُسرّب معلومةً منها إلى مرجعها،
# فتبدو كل شمعة أقرب إلى «عاديّة» ممّا هي.
src = (ROOT / "scanner" / "indicators" / "vsa.py").read_text(encoding="utf-8")
check("  والمتوسّط مزاحٌ بشمعة (لا تسريب)", ".shift(1)" in src)

# شمعةٌ مشوّهة من مصدرٍ معطوب لا تُنتج موضعاً خارج المدى
_bad = daily.copy()
_bad.loc[_bad.index[-1], "close"] = float(_bad["high"].iloc[-1]) * 1.5
_bf = vsa.features(_bad, 20)
check("  والشمعة المشوّهة تُحصر لا تُمرَّر",
      0.0 <= float(_bf["close_pos"].iloc[-1]) <= 1.0,
      str(_bf["close_pos"].iloc[-1]))

bar = vsa.classify(daily, 20)
check("  والتصنيف يعمل", bar is not None)
check("  ويعيد أسماءً عربية", bar is not None and isinstance(bar.arabic, tuple))
check("  والإطار القصير يعيد None", vsa.classify(daily.head(5), 20) is None)


# ── ٦) التقييم يستعمل الذكيّ لا الجلسة ──
eng = (ROOT / "scanner" / "scoring" / "engine.py").read_text(encoding="utf-8")
code = "\n".join(l for l in eng.splitlines() if not l.strip().startswith("#"))
check("٦ التقييم على VWAP الذكيّ", "vprof.smart_vwap(df" in code)
check("  ولا يستعمل الجلسة مباشرةً", "vol.session_vwap(df)" not in code)
check("  والطول من الإعدادات لا محشوراً",
      "p.vwap_len" in code and "vwap_len" in
      (ROOT / "scanner" / "config.py").read_text(encoding="utf-8"))

# ═══ VSA لا تدخل التقييم ═══
#
# قِيست فكان أثرها صفراً تقريباً. وإدخالها لأنّها «معروفة» يخفّف
# وزن ما يعمل فعلاً.
check("  و VSA لا تدخل التقييم",
      "vsa" not in code and "import vsa" not in eng)

# وأداة القياس موجودة وتقطع عند شمعة الدخول
study = (ROOT / "tools_volume_study.py").read_text(encoding="utf-8")
check("  وأداة القياس موجودة", study != "")
check("  وتقطع عند شمعة الدخول لا بعدها",
      "df.iloc[: pos + 1]" in study)
check("  وتصحّح تعدّد المقارنات", "benjamini_hochberg" in study)


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
