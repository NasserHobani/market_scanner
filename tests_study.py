# -*- coding: utf-8 -*-
"""دراسة الرمز — وأربعة مواضع تصنع فيها الدراسةُ وهماً.

═══ الأوّل: البحث بدل القياس ═══

لو جُرّبت عتبات RSI من ٥ إلى ٩٥ وأفقٌ من ٤ إلى ٩٦ لوُجدت تركيبةٌ
نسبتها ٨٠٪ — على بياناتٍ عشوائية أيضاً. ألفُ محاولةٍ تُنتج صدفةً
تبدو قانوناً.

فالشروط **مكتوبةٌ سلفاً**، وعددُها ثابت، فتصحيح المقارنات له معنى.

═══ الثاني: النظر إلى المستقبل ═══

ثلاثة منافذ: ‏ATR من شمعةٍ لم تُغلق، ومشيٌ يبدأ من الشمعة نفسها،
وقاعٌ يُعرَف قاعاً بشمعاتٍ بعده ثمّ يُستعمل إشارةً حيّة.

═══ الثالث: «متوسّط العائد» بدل الحاجزين ═══

من دخل ثمّ نزل السعر ٣×ATR قبل أن يصعد خرج بوقفه، ولا يناله ذلك
المتوسّط أبداً. فالرقم يبدو ممتازاً لأنّه يُحسب على مَن لم يُوقَف.

═══ والرابع: النسبة بلا فاصل ═══

«ارتدّ ٣ من ٣ = ١٠٠٪» صحيحٌ ومضلّل: فاصله ‎[31–100]‎. والترتيب
بالنسبة يجعل أضعف العيّنات تتصدّر.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scanner.study import labels as L  # noqa: E402
from scanner.study import zones as Z  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


def frame(closes, *, spread=0.5):
    """إطارٌ بسيط: المدى حول الإغلاق بمقدارٍ ثابت."""
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    cl = np.asarray(closes, dtype="float64")
    return pd.DataFrame({
        "open": cl, "high": cl + spread, "low": cl - spread,
        "close": cl, "volume": np.full(n, 1000.0),
    }, index=idx)


# ═══════════ ١) الحاجزان ═══════════
#
# صعودٌ مطّرد: كل دخولٍ يبلغ الهدف قبل الوقف.
up = frame(list(np.linspace(100, 160, 400)))
lab = L.label_forward(up, target_atr=2.0, stop_atr=1.0, horizon=24)
c("١ الوسم يعمل", lab["ok"], lab.get("why", ""))
r = L.rate(lab["label"])
c("  والصاعد يربح", r["rate"] is not None and r["rate"] > 90, str(r))

down = frame(list(np.linspace(160, 100, 400)))
r2 = L.rate(L.label_forward(down)["label"])
c("  والهابط يخسر", r2["rate"] is not None and r2["rate"] < 10, str(r2))

# ═══ والأخيرة لا تُوسَم ═══
#
# شمعةٌ لا يتبعها أفقٌ كامل تُقاس بأفقٍ أقصر، فتبدو أسوأ أو أفضل
# لسببٍ لا علاقة له بالإشارة.
lb = L.label_forward(up, horizon=24)["label"]
c("  والذيل غير موسوم",
  bool((lb[-24:] == L.OPEN).all()), str(lb[-5:]))

# ═══ ولا يُحتسب المفتوح ═══
#
# عدُّه خسارةً يخلط «لم يُحسم في الأفق» بـ«بلغ الوقف».
flat = frame([100.0] * 400)
rf = L.rate(L.label_forward(flat, horizon=10)["label"])
c("  والمفتوح لا يُحتسب", rf["n"] == 0 or rf["open"] > 0, str(rf))


# ═══════════ ٢) لا نظر إلى المستقبل ═══════════
src = source_of(ROOT / "scanner" / "study" / "labels.py")
code = code_of(ROOT / "scanner" / "study" / "labels.py")
c("٢ المشي يبدأ بعد الدخول", "range(i + 1" in code, "يبدأ من i")
c("  والسبب مكتوب", "تسريبٌ: لحظة القرار" in src)
# ═══ والشمعة التي تبلغ الحاجزين ═══
#
# عدُّها ربحاً يُنتج نظاماً يبدو رابحاً وهو يُوقَف في التطبيق.
c("  والملتبسة خسارة",
  "ambiguous[i] = True" in code and "label[i] = LOSS" in code)
c("  وعددها يُعلَن", "ambiguous_n" in code)
# والقاع يُعرَف بعد شمعات — فلا يصلح إشارةً حيّة
zsrc = source_of(ROOT / "scanner" / "study" / "zones.py")
c("  وحدّ القاع مكتوب", "لا تصلح للقرار اللحظي" in zsrc)


# ═══════════ ٣) الشروط تُقاس ولا تُبحَث ═══════════
csrc = source_of(ROOT / "scanner" / "study" / "conditions.py")
ccode = code_of(ROOT / "scanner" / "study" / "conditions.py")
c("٣ الشروط مكتوبة سلفاً", "مكتوبةٌ سلفاً" in csrc)
c("  ولا بحثَ عن عتبة",
  "for thresh in" not in ccode and "itertools" not in ccode)
c("  وتصحيح المقارنات", "def _bh" in ccode)
c("  واختبارٌ دقيق لا تقريب", "def _binom_p" in ccode and "comb(" in ccode)
c("  وتقسيمٌ زمنيّ لا عشوائيّ",
  "cut = int(n * split)" in ccode and "shuffle" not in ccode)
c("  والسبب مكتوب", "لا تُبعثَر عشوائياً" in csrc)
# ═══ والحكم يُقال بكلمة ═══
#
# شرطٌ يتفوّق داخل العيّنة ويسقط خارجها ملاءمةٌ لا اكتشاف.
c("  والملاءمة تُسمّى", "ملاءمة" in ccode)
c("  والعيّنة القصيرة لا حكم لها", "عيّنة قصيرة — لا حكم" in ccode)

# والشروط تُحسب فعلاً
_masks = ccode.count('("')
c("  وعددها كافٍ", _masks >= 12, str(_masks))


# ═══════════ ٤) النسبة لا تُعرَض بلا فاصل ═══════════
c("٤ المنطقة تحمل فاصلها",
  all(k in zsrc for k in ("_wilson", '"lo"', '"hi"')))
# ═══ والترتيب بالحدّ الأدنى ═══
#
# منطقةٌ ٣ من ٣ نسبتها ١٠٠٪ وتتصدّر كل شيء بلا معنى.
zcode = code_of(ROOT / "scanner" / "study" / "zones.py")
c("  والترتيب بالحدّ الأدنى", '-z["lo"]' in zcode, "يرتّب بالنسبة")
c("  وحدٌّ أدنى للمسات", "MIN_TOUCHES" in zcode)
c("  واللمسات كلّها تُعدّ لا القيعان",
  "inside = within" in zcode)
c("  والسبب مكتوب", "يُحصي النجاحات ويُسقط الاختراقات" in zsrc)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "study-page.js").read_text(encoding="utf-8")
c("  والواجهة تعرض الفاصل", "ciBar" in js)
c("  وتقول لماذا", "ولا تعني شيئاً" in js)


# ═══════════ ٥) التجميع والمناطق ═══════════
#
# قاعان عند ١٠٠ ثمّ ارتدادان — منطقةٌ واحدة لا اثنتان.
wave = []
for _ in range(10):
    wave += list(np.linspace(110, 100, 20)) + list(np.linspace(100, 110, 20))
wf = frame(wave)
wl = L.label_forward(wf, horizon=20)
zs = Z.build(wf, wl, min_touches=3)
c("٥ المناطق تُبنى", isinstance(zs, list))
if zs:
    c("  ولكلٍّ فاصل", all("lo" in z and "hi" in z for z in zs))
    c("  ومسافةٌ عن السعر", all("distance_pct" in z for z in zs))
    c("  والعيّنة مذكورة", all(z["settled"] >= 3 for z in zs))
# قاعٌ محلّي يُكتشَف
piv = Z.pivots(np.array([5.0, 4, 3, 2, 1, 2, 3, 4, 5]), span=3)
c("  والقاع يُكتشَف", 4 in piv, str(piv))


# ═══════════ ٦) الربط ═══════════
v = code_of(ROOT / "web" / "dashboard" / "study_views.py")
c("٦ الدراسة في خيط", "threading.Thread" in v)
c("  والسبب: ثلاثة عمّال", "ثلاثة عمّالٍ" in source_of(
    ROOT / "web" / "dashboard" / "study_views.py"))
c("  وحدٌّ للمتزامنات", ">= 2" in v)
c("  والمدخلات تُحصر", "max(lo, min(hi, v))" in v)
u = code_of(ROOT / "web" / "dashboard" / "urls.py")
for p in ("study/", "api/study/start/", "api/study/status/"):
    c(f"  والمسار {p}", f'"{p}"' in u)
cp = code_of(ROOT / "web" / "dashboard" / "context_processors.py")
c("  والرابط في القائمة", '"/study/"' in cp)
tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "study.html").read_text(encoding="utf-8")
# ═══ والحاجزان ظاهران ═══
#
# «نسبة النجاح ٦٤٪» بلا ذكر الهدف والوقف رقمٌ بلا معنى.
c("  والحاجزان قابلان للتغيير",
  'id="s-target"' in tpl and 'id="s-stop"' in tpl)
c("  والسبب مكتوب", "هدفٌ قريب يرفعها" in tpl)


sys.exit(c.report())
