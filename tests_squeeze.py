# -*- coding: utf-8 -*-
"""الانضغاط والتمدّد — احتمالٌ مقيس لا رقمٌ يُعرض.

═══ ما قِيس قبل بناء الصفحة ═══

على شموع مخزّنة حقيقية، أفق ١٢ شمعة وتمدّد = ٣× ATR::

    crypto 4h   منضغط  6202/9936  = 62.4٪ [61–63]
                الأساس 28506/52612 = 54.2٪ [54–55]   +8.2

    us 1d       منضغط  5116/7550  = 67.8٪ [67–69]
                الأساس 26823/45306 = 59.2٪ [59–60]   +8.6

الفواصل لا تتقاطع والعيّنات بالآلاف. ولو لم يتجاوز الأساس لعُرضت
الصفحة بلا احتمال — فالبناء تبع القياس لا العكس.

═══ وما يحرسه هذا الملف ═══

    ١) ألّا يُنظر إلى المستقبل عند حساب الرتبة أو التسمية.
    ٢) ألّا تُحسب آخر الشموع التي لم يمضِ عليها الأفق.
    ٣) ألّا يُعرض احتمال بلا معدّل أساس بجانبه.
    ٤) ألّا يُنطق برقم على عيّنة صغيرة.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner import squeeze_scan as sq  # noqa: E402
from scanner.indicators import squeeze  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def frame(closes) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    idx = pd.date_range("2026-01-01", periods=len(c), freq="h", tz="UTC")
    return pd.DataFrame({"open": c, "high": c * 1.002, "low": c * 0.998,
                         "close": c, "volume": np.ones(len(c))}, index=idx)


# ── ١) عرض القناة نسبيّ ──
#
# رمزٌ سعره 5 وآخر سعره 64000 لا يُقارَنان بعرضٍ مطلق.
rng = np.random.default_rng(7)
noise = rng.normal(0, 1, 400)
cheap = frame(5 + noise * 0.05)
rich = frame(64000 + noise * 640)
wc = squeeze.bb_width(cheap).iloc[-1]
wr = squeeze.bb_width(rich).iloc[-1]
check("١ العرض نسبيّ للسعر", abs(wc - wr) < max(wc, wr) * 0.35,
      f"{wc:.3f} مقابل {wr:.3f}")


# ═══ ٢) الرتبة لا تنظر إلى المستقبل ═══
#
# نافذةٌ تشمل شموعاً لاحقة تجعل النتيجة ممتازة على الورق عاجزة في
# السوق. فتُقارَن الرتبة على سلسلةٍ مقتطعة بالرتبة على السلسلة
# كاملةً عند النقطة نفسها.
long_c = frame(100 + np.cumsum(rng.normal(0, 0.5, 500)))
full = squeeze.squeeze_rank(long_c)
cut = squeeze.squeeze_rank(long_c.iloc[:300])
a, b = full.iloc[299], cut.iloc[299]
check("٢ الرتبة لا ترى المستقبل",
      (np.isnan(a) and np.isnan(b)) or abs(float(a) - float(b)) < 1e-9,
      f"{a} مقابل {b}")


# ═══ ٣) آخر الشموع لا تُحسب ═══
#
# شمعةٌ لم يمضِ عليها الأفق لا يُعرف هل تمدّدت. واعتبارها «لم
# تتمدّد» يخفض الاحتمال كذباً.
h = 12
m = squeeze.measure(long_c, horizon=h)
check("٣ الحالات أقلّ من الشموع",
      m["base"] <= len(long_c) - squeeze.LOOKBACK - h + 1,
      f"{m['base']} من {len(long_c)}")
check("  وتُقاس حالات فعلاً", m["base"] > 0)
# والقصيرة لا تُقاس بل تُعلَن صفراً
short = squeeze.measure(frame(100 + rng.normal(0, 1, 50)), horizon=h)
check("  والسلسلة القصيرة صفر", short["base"] == 0 and short["usable"] == 0)
check("  ولا ترمي", isinstance(short, dict))
check("  والفارغ لا يكسر", squeeze.measure(None, horizon=h)["base"] == 0)


# ── ٤) المنضغط جزءٌ من الأساس لا شيءٌ آخر ──
check("٤ المنضغط ⊆ الأساس", m["squeezed"] <= m["base"])
check("  والإصابات ⊆ الحالات", m["squeezed_hits"] <= m["squeezed"])
check("  وأوقات الإصابة بعددها",
      len(m["bars_to_hit"]) == m["squeezed_hits"])
# ولا يقع وقتٌ خارج الأفق
check("  ولا وقت خارج الأفق",
      all(1 <= x <= h for x in m["bars_to_hit"]),
      str([x for x in m["bars_to_hit"] if not 1 <= x <= h][:3]))


# ═══ ٥) سلسلةٌ هادئة ثمّ قافزة ═══
#
# اختبارٌ للمعنى لا للصيغة: مدىً ضيّق طويل ثمّ قفزة كبيرة يجب أن
# يُرصد انضغاطاً ثمّ تمدّداً.
calm = list(100 + rng.normal(0, 0.02, 300))
jump = list(np.linspace(100, 130, 40))
mixed = squeeze.measure(frame(calm + jump), horizon=20)
check("٥ الهدوء ثمّ القفزة يُرصد",
      mixed["squeezed"] > 0 and mixed["squeezed_hits"] > 0,
      f"منضغط {mixed['squeezed']} · إصابات {mixed['squeezed_hits']}")


# ── ٦) الحالة الحالية ──
st = squeeze.current_state(long_c)
check("٦ الحالة فيها رتبة", "squeeze_rank" in st)
check("  والحركة المطلوبة نسبةً", st.get("expansion_pct", 0) > 0)
check("  والقصيرة تعيد فارغاً",
      squeeze.current_state(frame([1, 2, 3])) == {})


# ═══ ٧) الأساس ملازم للاحتمال ═══
#
# «62٪» يبدو كبيراً والأساس 54٪ — أي أنّ الانضغاط يضيف ثمانياً لا
# اثنتين وستّين. وعرض الرقم وحده يوهم القارئ بما لم يكتشفه.
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "squeeze-page.js").read_text(encoding="utf-8")
check("٧ الواجهة تعرض الأساس", "base_pct" in js)
check("  وتعرض الفارق", "p.edge" in js)
check("  وتقول إن لم يتجاوزه", "ضمن الأساس" in js)
check("  وتمتنع عند العيّنة الصغيرة", "دون حدّ النطق" in js)
check("  والحدّ معقول", 50 <= sq.MIN_SAMPLE <= 1000, str(sq.MIN_SAMPLE))

html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "squeeze.html").read_text(encoding="utf-8")
# الاحتمال للسوق لا للرمز — والصفحة تقولها
check("  والصفحة تنفي أنّه للرمز", "لا لهذا الرمز وحده" in html)
check("  وتعرّف التمدّد", "3× مدى ATR" in html)
# ولا يقول اتجاهاً: قد يتمدّد صعوداً أو هبوطاً
check("  وتنفي الاتجاه", "لا يقول اتجاهاً" in html)


# ── ٨) الحساب خارج الطلب ──
views = (ROOT / "web" / "dashboard"
         / "squeeze_views.py").read_text(encoding="utf-8")
vcode = "\n".join(l for l in views.splitlines()
                  if not l.strip().startswith("#"))
check("٨ القراءة من المحفوظ", "squeeze_scan.load(" in vcode)
check("  ولا بناء في GET",
      "squeeze_scan.build(" not in vcode.split("api_squeeze_refresh")[0])
check("  والإعادة في خيط", "threading.Thread" in vcode)
check("  والقِدم يُعلَن", "stale" in vcode and "STALE_HOURS" in views)

cron = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
check("  ولها مهمّة مجدولة", '"squeeze": _h_squeeze' in cron)
check("  كل ساعتين", '"interval_type": "hours"' in cron)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
check("  والمسارات مسجّلة",
      "api_squeeze" in urls and "squeeze_page" in urls)
cp = (ROOT / "web" / "dashboard"
      / "context_processors.py").read_text(encoding="utf-8")
check("  وفي الشريط الجانبي", '"squeeze"' in cp)


# ── ٩) الحفظ ذرّي ──
#
# ملفٌّ يُقرأ أثناء كتابته يُعطي JSON ناقصاً.
src = (ROOT / "scanner" / "squeeze_scan.py").read_text(encoding="utf-8")
check("٩ الحفظ ذرّي", "tmp.replace(p)" in src)
check("  ولكل فريم أفق", set(sq.HORIZONS) >= {"1h", "4h", "1d"})
check("  ولكل فريم طول", set(sq.TF_MINUTES) >= set(sq.HORIZONS))
check("  والوقت يُعرَّب", sq.humanize(120) == "ساعتان",
      sq.humanize(120))
check("  والفارغ —", sq.humanize(None) == "—")


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
