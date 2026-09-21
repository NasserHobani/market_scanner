# -*- coding: utf-8 -*-
"""استراتيجيات المستخدم — وأربعة مواضع يكذب فيها الفرز.

═══ الأوّل: الغائب يُعدّ ناجحاً ═══

رمزٌ بلا قيمةٍ لهذا الحقل — مؤشّرٌ لم يُحسب، أو موجة فيب غير
صالحة. وعدُّه مطابقاً يُدخل في النتيجة رموزاً **لم تُفحَص**،
فتبدو القائمة أطول وتبدو الاستراتيجية أنجح.

═══ الثاني: «أو» خفيّة ═══

الشروط تجتمع كلّها. وشرطٌ واحد لا يتحقّق يُسقط الرمز — وإلّا
صارت الاستراتيجية أوسع ممّا كتبه صاحبها بلا أن يدري.

═══ الثالث: شرطٌ معطوب يُحفظ ═══

«بين» بلا حدّين، أو حقلٌ لا وجود له. ويُحفَظ فيفشل صامتاً عند كل
فرز: لا رمز يُطابق، ولا شيء يقول لماذا. فالتحقّق **قبل** الحفظ.

═══ والرابع: النقاط بدل النسبة ═══

شرطٌ على «نقاط الحجم ≥ ١٢» يتغيّر معناه بتغيّر الأوزان في
‎config/pes.yaml‎ — بلا أن ينتبه أحد. فالحقول عوامل**نسبةً** من
سقفها، والنسبة تبقى نسبة.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.strategies import custom as C  # noqa: E402
from tests_helpers import Checks, code_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


def row(**kw) -> dict:
    """صفُّ مسحٍ مصغَّر — بالحقول التي تقرؤها الاستراتيجيات."""
    base = {
        "symbol": "TSTUSDT", "score": 70.0, "state": "PRE_BREAKOUT",
        "confidence": 1.0, "family_count": 4, "distance": 2.5,
        "close": 100.0, "already_expanded": False,
        "momentum": {"score": 7.0},
        "supertrend": {"direction": 1, "bars_since_flip": 3},
        "fib": {"room_pct": 12.0},
        "factors": [{"key": "volume", "points": 12.0, "max": 15.0},
                    {"key": "compression", "points": 3.0, "max": 15.0}],
    }
    base.update(kw)
    return base


# ═══════════ ١) المقارنات ═══════════
def ev(conds, **kw):
    return C.evaluate(row(**kw), conds)


c("١ ‎>=‎ يطابق", ev([{"field": "score", "op": ">=", "args": [60]}])["match"])
c("  ولا يطابق دونه",
  not ev([{"field": "score", "op": ">=", "args": [80]}])["match"])
c("  و‎between‎ داخل المدى",
  ev([{"field": "score", "op": "between", "args": [60, 80]}])["match"])
c("  ولا خارجه",
  not ev([{"field": "score", "op": "between", "args": [80, 90]}])["match"])
c("  و‎in‎ على المرحلة",
  ev([{"field": "state", "op": "in",
       "args": ["PRE_BREAKOUT", "BREAKOUT"]}])["match"])
c("  والمنطقيّ", ev([{"field": "already_expanded", "op": "==",
                      "args": ["false"]}])["match"])
c("  والنصّيّ", ev([{"field": "supertrend_dir", "op": "==",
                     "args": ["up"]}])["match"])


# ═══════════ ٢) الغائب لا يُطابق ═══════════
#
# هذا هو الفحص الذي يمنع «قائمةً تبدو أطول فتبدو أنجح».
c("٢ الغائب لا يطابق",
  not ev([{"field": "fib_room", "op": "<=", "args": [50]}],
         fib={})["match"])
c("  ولا بالمساواة",
  not ev([{"field": "supertrend_dir", "op": "==", "args": ["up"]}],
         supertrend={})["match"])
# ═══ والصفر ليس غياباً ═══
#
# ‏Supertrend باتّجاه صفر يعني «لم يستقرّ بعد» لا «هابط» — وعدُّه
# هبوطاً يُسقط رمزاً لم يُفحَص.
c("  والاتّجاه صفرٌ = غير محسوب",
  not ev([{"field": "supertrend_dir", "op": "==", "args": ["down"]}],
         supertrend={"direction": 0})["match"])
c("  و‎NaN‎ لا تطابق",
  not ev([{"field": "score", "op": ">=", "args": [0]}],
         score=float("nan"))["match"])


# ═══════════ ٣) كلّها معاً ═══════════
both = [{"field": "score", "op": ">=", "args": [60]},
        {"field": "momentum_score", "op": ">=", "args": [7]}]
c("٣ الشرطان معاً يطابقان", ev(both)["match"])
one_fails = both + [{"field": "distance", "op": "<=", "args": [0.1]}]
r = ev(one_fails)
c("  وواحدٌ يفشل يُسقط الكلّ", not r["match"], str(r["met"]) + "/" + str(r["total"]))
# ═══ والعدد يُحفظ للعرض لا للمطابقة ═══
c("  والعدد المتحقّق يُعلَن", r["met"] == 2 and r["total"] == 3,
  f"{r['met']}/{r['total']}")
c("  وتفصيل كل شرط يُعاد", len(r["conditions"]) == 3)
c("  وفيه القيمة المقروءة",
  any(x["value"] == 2.5 for x in r["conditions"]),
  str([x["value"] for x in r["conditions"]]))
# قائمةٌ فارغة ليست «يطابق كلّ شيء»
c("  وبلا شروط لا مطابقة", not C.evaluate(row(), [])["match"])


# ═══════════ ٤) العوامل نسبةً ═══════════
#
# ‏12 من 15 = ٨٠٪. ولو كان الشرط على النقاط لتغيّر معناه مع أيّ
# تعديلٍ للأوزان.
c("٤ العامل يُقرأ نسبةً",
  ev([{"field": "factor_volume", "op": ">=", "args": [79]}])["match"])
c("  والمنخفض لا يطابق",
  not ev([{"field": "factor_compression", "op": ">=", "args": [50]}])["match"])
c("  والعامل الغائب لا يطابق",
  not ev([{"field": "factor_adx", "op": ">=", "args": [0]}])["match"])
_dsrc = code_of(ROOT / "scanner" / "strategies" / "custom.py")
c("  والنسبة في الكود لا النقاط", "points / mx * 100" in _dsrc)


# ═══════════ ٥) التحقّق قبل الحفظ ═══════════
c("٥ الفارغة مرفوضة", C.validate([]) != [])
c("  والحقل المجهول مرفوض",
  C.validate([{"field": "لا_يوجد", "op": ">=", "args": [1]}]) != [])
c("  والعملية المجهولة مرفوضة",
  C.validate([{"field": "score", "op": "~~", "args": [1]}]) != [])
# ═══ والعملية التي لا تنطبق ═══
#
# «بين» على المرحلة خيارٌ لا معنى له — ويُنتج استراتيجيةً لا
# تفرز شيئاً أبداً.
c("  و«بين» لا تنطبق على المرحلة",
  C.validate([{"field": "state", "op": "between", "args": ["a", "b"]}]) != [])
c("  و«بين» بحدٍّ واحد مرفوضة",
  C.validate([{"field": "score", "op": "between", "args": [10]}]) != [])
c("  والصحيحة تمرّ",
  C.validate([{"field": "score", "op": ">=", "args": [60]}]) == [])
# والرسالة تذكر رقم الشرط كي يُعرف أيّها
c("  والرسالة ترقّم الشرط",
  "2" in " ".join(C.validate([
      {"field": "score", "op": ">=", "args": [60]},
      {"field": "score", "op": "??", "args": [1]}])))


# ═══════════ ٦) سجلّ الحقول ═══════════
cat = C.field_catalog()
c("٦ السجلّ غير فارغ", len(cat) > 8, str(len(cat)))
c("  ولا دوالّ فيه", all("get" not in f for f in cat))
c("  ولكلّ حقلٍ اسمٌ عربيّ", all(f.get("label") for f in cat))
c("  ونوعٌ معروف",
  all(f.get("kind") in ("number", "enum", "bool") for f in cat))
# ═══ والعمليات تُشتقّ من النوع ═══
#
# عرضُ «بين» على حقلٍ نصّيّ في الواجهة يعني خياراً لا يُنتج شيئاً.
c("  والعمليات مشتقّة", all(f.get("ops") for f in cat))
_enum = [f for f in cat if f["kind"] == "enum"]
c("  ولا ‎between‎ للنصّي",
  all("between" not in f["ops"] for f in _enum), str(_enum[:1]))
c("  والنصّي له خياراته",
  all(f.get("choices") for f in _enum))


# ═══════════ ٧) الربط ═══════════
_urls = code_of(ROOT / "web" / "dashboard" / "urls.py")
for p in ("strategies/", "board/", "api/strategies/save/", "api/board/"):
    c(f"٧ المسار {p}", f'"{p}"' in _urls)
_cp = code_of(ROOT / "web" / "dashboard" / "context_processors.py")
c("  والرابطان في القائمة",
  '"/strategies/"' in _cp and '"/board/"' in _cp)
_v = code_of(ROOT / "web" / "dashboard" / "strategy_views.py")
# اللوحة تقرأ المحفوظ ولا تحسب — وإلّا شغلت خيط الخادم دقائق
c("  واللوحة تقرأ ولا تحسب", "pes_scan" not in _v)
c("  وعمودٌ يفشل لا يُسقط اللوحة", '"error"' in _v)

# ═══ ولا تشفيرٌ مزدوج للسجلّ ═══
#
# ``json_script`` يُسلسِل ما يُعطى. وتمريرُ ``json.dumps`` إليه
# يُشفّرها مرّتين: يصير محتوى الوسم نصّاً لا مصفوفة، فيعيد
# ``JSON.parse`` سلسلةً — و«FIELDS.forEach is not a function».
# وقد وقع.
_ctx = _v.split("def builder_page")[1][:900] if "def builder_page" in _v else ""
c("  والسجلّ يُمرَّر كائناً",
  "custom.field_catalog()" in _ctx and "json.dumps" not in _ctx,
  _ctx[:160])
_bjs = code_of(ROOT / "web" / "dashboard" / "static" / "dashboard"
               / "strategy-builder.js")
# والواجهة تتحقّق من الشكل: TypeError غامض أسوأ من رسالةٍ تدلّ
c("  والواجهة تتحقّق من الشكل", "مُشفَّر مرّتين" in _bjs
  or "[object Array]" in _bjs)
_store = code_of(ROOT / "scanner" / "strategies" / "custom_store.py")
c("  والحفظ يتحقّق أوّلاً", "custom.validate" in _store)
c("  وملفٌّ معطوب يُتخطّى", "continue" in _store)


sys.exit(c.report())
