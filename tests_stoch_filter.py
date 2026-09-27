# -*- coding: utf-8 -*-
"""«راكب التشبّع» — فرزٌ بحالةٍ، وثلاثة مواضع يكذب فيها.

═══ الأوّل: «فوق ٨٠» تجمع نقيضين ═══

تشبّعٌ شرائيّ **في اتّجاهٍ صاعد** استمرار — يبقى المؤشّر هناك
أسابيع. وتشبّعٌ شرائيّ بلا اتّجاه قمّة. والفرز بالمنطقة وحدها
يجمعهما في قائمةٍ نصفُها ضدّ المطلوب، ثمّ تُنسَب نتيجتُها كلّها
إلى «الفلتر».

═══ الثاني: المجهول يمرّ ═══

رمزٌ بلا شموعٍ كافية لا اتّجاه له. وعدُّه «راكباً» يُدخل ما لم
يُفحَص في القائمة فتبدو أطول وأنجح — وهو نفس العطب الذي عولج في
مُنشئ الاستراتيجيات.

═══ الثالث: الشمعة الجارية ═══

‏%K يعبر %D ويرتدّ داخل الشمعة الواحدة مراراً. والفرز عليها يجعل
القائمة تتبدّل كل دقيقة بلا أن يتغيّر شيء.

═══ ورابعٌ ليس في الكود ═══

«أغلب صفقاتي الناجحة كانت هكذا» ذاكرةٌ لا قياس — والذاكرة تحتفظ
بالرابحات. فالفلتر يُعرَض، و``tools_stoch_measure.py`` يفحص
المقولة على الصفقات المحسومة: نسبةُ الربح **داخل** الحالة مقابل
خارجها، لا نسبةُ الحالة بين الرابحات.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.analysis import stoch_watch as SW  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


# ═══════════ ١) الاتّجاه يفصل النقيضين ═══════════
c("١ تشبّعٌ واتّجاه = راكب",
  SW.classify("overbought", True) == "riding")
c("  وتشبّعٌ بلا اتّجاه = منهَك",
  SW.classify("overbought", False) == "exhausted")
c("  والبيعيّ يبقى بيعيّاً",
  SW.classify("oversold", True) == "oversold")
c("  والوسط وسط", SW.classify("middle", True) == "middle")


# ═══════════ ٢) المجهول لا يصير راكباً ═══════════
#
# ``uptrend is None`` = «شموع لا تكفي» لا «ليس صاعداً».
c("٢ اتّجاهٌ مجهول = غير محسوب",
  SW.classify("overbought", None) == "unknown",
  SW.classify("overbought", None))
c("  ولا يصير راكباً", SW.classify("overbought", None) != "riding")
c("  ولا منهَكاً", SW.classify("overbought", None) != "exhausted")
c("  ومنطقةٌ مجهولة كذلك",
  SW.classify("unknown", True) == "unknown")
# ولكلّ حالةٍ وسمٌ عربيّ — وإلّا ظهر مفتاحٌ إنجليزيّ في الشاشة
c("  ولكلّ حالةٍ وسم", all(s in SW.STATE_LABELS for s in SW.STATES))


# ═══════════ ٣) الشمعة المغلقة وحدها ═══════════
src = source_of(ROOT / "scanner" / "analysis" / "stoch_watch.py")
c("٣ الاتّجاه من المغلق", "iloc[-2]" in src)
c("  ولا يقرأ الجارية", "iloc[-1]" not in code_of(
    ROOT / "scanner" / "analysis" / "stoch_watch.py"))
c("  والوصف يقرأ ‎-2‎ أصلاً",
  "iloc[-2]" in source_of(ROOT / "scanner" / "indicators" / "momentum.py"))
# والتخبئة بزمن آخر شمعة: شمعةٌ جديدة تُبطلها تلقائياً
c("  والتخبئة بزمن الشمعة", "df.index[-1]" in src)
# ولا شبكة: الشاشة تعرض عشرات الصفوف
c("  ولا طلب شبكة", "urlopen" not in src and "requests" not in src)
c("  ولا ترمي", "except Exception" in src)


# ═══════════ ٤) الواجهة: تُعرَض وتُرشَّح ═══════════
v = code_of(ROOT / "web" / "dashboard" / "views.py")
c("٤ المرشّح يُقرأ", '"stoch"' in v)
c("  ويُتحقَّق منه", "stoch_watch.STATES" in v)
c("  ويُطبَّق على المراقبة", "_with_stoch(rows, f)" in v)
# ═══ والحالة تُعرَض على كل صفّ ═══
#
# فلترٌ يخفي معياره يُقرأ سحراً، والقارئ لا يملك ما يصحّح به فهمه.
_ws = v.split("def _with_stoch")[1][:900] if "def _with_stoch" in v else ""
c("  والحالة تُلحَق قبل الترشيح",
  _ws.index('r["stoch"]') < _ws.index('f.get("stoch")')
  if ('r["stoch"]' in _ws and 'f.get("stoch")' in _ws) else False, _ws[:160])
c("  و«مرشَّح» يشمله", 'or f["stoch"]' in v)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "watches-page.js").read_text(encoding="utf-8")
c("  والرقائق موجودة", "STOCH_CHIPS" in js)
c("  وتحمل «راكب»", '"riding"' in js)
c("  وعمودٌ في الجدول", '"stoch"' in js and "stochCell" in js)
# والمفتاح يُنقل من العنوان إلى النداء — وإلّا بدا الفلتر يعمل
c("  والمفتاح يُنقل للنداء", '"stoch"' in js.split("FILTER_KEYS")[1][:120],
  js.split("FILTER_KEYS")[1][:120] if "FILTER_KEYS" in js else "")
tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "watches.html").read_text(encoding="utf-8")
c("  ومكانها في القالب", 'id="stoch-chips"' in tpl)


# ═══════════ ٥) المقولة تُقاس لا تُصدَّق ═══════════
tool = ROOT / "tools_stoch_measure.py"
c("٥ أداة القياس موجودة", tool.exists())
if tool.exists():
    t = source_of(tool)
    # ═══ السؤال الصحيح ═══
    #
    # «كم من الرابحات كانت راكبة؟» يجيب عنه التحيّز. والصحيح:
    # نسبة الربح داخل الحالة مقابل خارجها.
    c("  تقارن داخل بخارج", "outside" in t and "inside" in t)
    c("  وتذكر تحيّز الذاكرة", "تحتفظ بالرابحات" in t)
    c("  وتعرض النسبة العكسية للمقارنة", "من رابحاتك" in t)
    # ولا نظرَ إلى المستقبل: الحالة قبل الدخول
    c("  والحالة قبل الدخول", "idx < pd.Timestamp(opened)" in t)
    c("  وفاصل ثقة", "def wilson" in t)
    c("  واختبار دلالة", "two_prop_z" in t)
    # وعيّنةٌ قصيرة = لا حكم، لا حكمٌ ضعيف
    c("  والقصيرة بلا حكم", "MIN_PER_GROUP" in t)
    c("  والمتعذّر يُعلَن", "skipped" in t)


sys.exit(c.report())
