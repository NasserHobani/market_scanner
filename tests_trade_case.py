# -*- coding: utf-8 -*-
"""لماذا تنجح ولماذا تفشل — وأربعة مواضع يكذب فيها الجواب.

═══ الأوّل: حجّةٌ من طرفٍ واحد ═══

كل شاشةٍ هنا تعرض **أسباب الدخول** ولا تعرض ما يضعفه. وقائمةُ
أسبابٍ من جانبٍ واحد تُقرأ تأكيداً مهما كان محتواها، فيدخل القارئ
وهو يظنّ أنّه فحص.

═══ الثاني: عائلةٌ تُعدّ ثلاث مرّات ═══

‏EMA و ADX و Supertrend تقيس الاتّجاه. وثلاث نقاطٍ في عمود «يدعم»
ليست ثلاثة شهود بل شاهدٌ واحد بثلاثة أسماء — وهو العطب نفسه الذي
عولج في وحدة الأدلّة: ثلاثة «أسباب» بأرقامٍ متطابقة كانت الصفقات
الثمانية عشر نفسها.

═══ الثالث: احتمالٌ يُخترع ═══

«احتمال نجاحها ٧٢٪» غير قابلٍ للتكذيب. و‏LightGBM — النموذج الوحيد
الذي حاول ذلك هنا — لم يتجاوز خطّ الأساس فأُخفي احتماله. والمعيار
نفسه يُطبَّق: تُعرَض نسبةُ **وسمٍ في سجلّك** بعدده وفاصله، لا
تنبّؤ بهذه الصفقة.

═══ والرابع: «خسرت» تُخفي أين الخلل ═══

صفقةٌ بلغت ‎+2.3R‎ ثمّ أُغلقت خاسرة ليست كصفقةٍ لم تتحرّك لصالحك
قطّ. الأولى عطبُ **خروج** والثانية عطبُ **دخول** — ونتيجتهما في
الجدول واحدة. فمن يقرأ نسبة النجاح وحدها يصلح ما ليس مكسوراً.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.analysis import trade_case as TC  # noqa: E402
from scanner.postmortem import anatomy as AN  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


def F(key, share, mx=10.0):
    return {"key": key, "label": key, "points": share / 100.0 * mx, "max": mx}


# ═══════════ ١) الوجهان دائماً ═══════════
strong = TC.build({"factors": [F("volume", 90), F("compression", 85)],
                   "family_count": 4, "rr": 3.0}, [])
c("١ يعيد الوجهين", bool(strong["pro"]) and bool(strong["con"]))
c("  والخالي من الاعتراض يُعلَن",
  any("نادر" in x["text"] for x in strong["con"]),
  str([x["text"][:40] for x in strong["con"]]))

weak = TC.build({"factors": [F("volume", 5)], "family_count": 1,
                 "rr": 1.1}, [])
c("  والخالي من الدعم يُعلَن",
  any("لا عامل بلغ" in x["text"] for x in weak["pro"]),
  str([x["text"][:40] for x in weak["pro"]]))
c("  والضعيف يُقال", any("٥٪" in x["text"] or "5٪" in x["text"]
                         for x in weak["con"]),
  str([x["text"][:50] for x in weak["con"]]))


# ═══════════ ٢) العائلة مرّةً واحدة ═══════════
#
# ثلاثة مؤشّرات اتّجاه بدرجاتٍ عالية = شاهدٌ واحد.
trend3 = TC.build({"factors": [F("daily_trend", 95), F("h4_trend", 90),
                               F("supertrend", 88), F("adx", 85)],
                   "family_count": 4}, [])
fams = [x.get("family") for x in trend3["pro"] if x.get("family")]
c("٢ الاتّجاه يُعدّ مرّة", fams.count("trend") <= 1, str(fams))
c("  والعائلات تُعلَن", trend3["families_supporting"] == ["trend"],
  str(trend3["families_supporting"]))

mixed = TC.build({"factors": [F("daily_trend", 95), F("volume", 90),
                              F("rsi", 88), F("compression", 92)],
                  "family_count": 4}, [])
c("  وأربع عائلات تُعدّ أربعاً",
  len(mixed["families_supporting"]) == 4,
  str(mixed["families_supporting"]))
c("  والتصنيف صحيح", TC.family_of("supertrend") == "trend"
  and TC.family_of("obv") == "volume"
  and TC.family_of("macd") == "momentum")
c("  والمجهول «أخرى»", TC.family_of("شيء_غريب") == "other")


# ═══════════ ٣) لا احتمال يُخترع ═══════════
c("٣ لا حكم واحد", strong["verdict"] is None)
src = source_of(ROOT / "scanner" / "analysis" / "trade_case.py")
c("  والسبب مكتوب", "LightGBM" in src and "لم يتجاوز خطّ الأساس" in src)
code = code_of(ROOT / "scanner" / "analysis" / "trade_case.py")
for bad in ("probability", "prob_up", "win_chance"):
    c(f"  ولا {bad}", bad not in code)
# والنسبة من السجلّ بعددها وفاصلها
settled = ([{"status": "won", "factors": ["اختراق"]}] * 20 +
           [{"status": "lost", "factors": ["اختراق"]}] * 5 +
           [{"status": "lost", "factors": ["شيء آخر"]}] * 25)
r = TC.tag_rate("اختراق", settled)
c("  والوسم بعدده", r and r["n"] == 25, str(r))
c("  وبفاصله", r and r["lo"] < r["rate"] < r["hi"], str(r))
c("  والغائب لا يُخترع", TC.tag_rate("لا_يوجد", settled) is None)
# ═══ والعيّنة القصيرة تُوسَم لا تُخفى ═══
thin = TC.tag_rate("نادر", [{"status": "won", "factors": ["نادر"]}] * 3)
c("  والقصيرة مَوسومة", thin and thin["thin"], str(thin))


# ═══════════ ٤) تشريح النتيجة ═══════════
def T(status, best, worst, r_):
    return {"status": status, "best_r": best, "worst_r": worst,
            "r_multiple": r_}


c("٤ رُدّ الربح", AN.classify(T("lost", 2.3, -0.4, -1.0)) == "gave_back")
c("  والفكرة الميتة",
  AN.classify(T("lost", 0.1, -1.0, -1.0)) == "thesis_dead")
c("  والوقف العاديّ",
  AN.classify(T("lost", 0.5, -1.0, -1.0)) == "stopped_normal")
c("  وكادت", AN.classify(T("lost", 0.85, -1.0, -1.0)) == "near_miss")
c("  والربح النظيف",
  AN.classify(T("won", 2.0, -0.2, 2.0)) == "clean_win")
# ═══ النجاة ليست نظافة ═══
#
# صفقةٌ نزلت إلى ‎−0.9R‎ ثمّ ربحت كانت على حافّة الحظّ.
c("  والنجاة تُميَّز",
  AN.classify(T("won", 2.0, -0.9, 2.0)) == "survived_win")
c("  والربح الهزيل",
  AN.classify(T("won", 0.5, -0.1, 0.3)) == "scraped_win")
# والغائب لا يُصنَّف: تصنيفُه من حقلٍ فارغ يخترع حكماً من غياب
c("  والغائب لا يُصنَّف",
  AN.classify({"status": "lost", "best_r": None,
               "r_multiple": -1.0}) == "unknown")
c("  وغير المحسومة كذلك",
  AN.classify(T("open", 1.0, -0.1, 0.5)) == "unknown")

# ═══ وموضع الخلل يُسمّى ═══
a = AN.anatomy(T("lost", 2.3, -0.4, -1.0))
c("  والخلل في الخروج", a["blame"] == "exit", a["blame"])
c("  وما رُدّ يُحسب", a["given_back_r"] == 3.3, str(a["given_back_r"]))
c("  وسببه مكتوب", any("رُدّ" in n for n in a["notes"]))
a2 = AN.anatomy(T("lost", 0.1, -1.0, -1.0))
c("  والخلل في الدخول", a2["blame"] == "entry", a2["blame"])
c("  والمرشّح هو موضع النظر",
  any("المرشّح" in n for n in a2["notes"]))


# ═══════════ ٥) هل كان الوقف ضيّقاً؟ ═══════════
#
# لا يُجاب بالرأي بل بتوزيع ``worst_r`` في **الرابحة** وحدها:
# الخاسرة تُوقَف عند ‎−1R‎ بالتعريف فتوزيعها مقطوع.
deep = [{"worst_r": -1.2} for _ in range(20)]
sc = AN.stop_context({"worst_r": -1.0}, deep)
c("٥ رابحون عميقون ⇒ الوقف ليس ضيّقاً",
  sc["ok"] and sc["stop_too_tight"] is False, str(sc)[:120])
c("  والسبب مذكور", "الدخول" in sc["verdict"])
shallow = [{"worst_r": -0.1} for _ in range(20)]
sc2 = AN.stop_context({"worst_r": -1.0}, shallow)
c("  ورابحون سطحيّون ⇒ الفكرة خاطئة",
  sc2["ok"] and "الفكرة كانت" in sc2["verdict"], sc2["verdict"][:70])
c("  والعيّنة القصيرة بلا حكم",
  not AN.stop_context({"worst_r": -1.0}, deep[:5])["ok"])
c("  وبلا مسار لا حكم",
  not AN.stop_context({"worst_r": None}, deep)["ok"])
asrc = source_of(ROOT / "scanner" / "postmortem" / "anatomy.py")
c("  ولماذا الرابحة وحدها", "فتوزيعها مقطوعٌ هناك" in asrc)


# ═══════════ ٦) الربط ═══════════
pv = code_of(ROOT / "web" / "dashboard" / "postmortem_views.py")
c("٦ التشريح في البطاقة", '"anatomy": anat' in pv)
c("  والحجّة معها", '"case": _case_for(t)' in pv)
c("  ونقطةٌ لما قبل الدخول", "def api_case" in pv)
# والرابحون يُقرأون من القاعدة لا يُخترعون
c("  والرابحون من السجلّ", "def _winners" in pv and 'status="won"' in pv)
_urls = code_of(ROOT / "web" / "dashboard" / "urls.py")
c("  والمسار مسجَّل", '"api/case/"' in _urls)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "trade-case.js").read_text(encoding="utf-8")
c("  والعارض مشترك", "window.TradeCase" in js)
# ═══ والمضادّ أوّلاً ═══
#
# ما يُقرأ أوّلاً يُوزن أكثر، والانحياز الطبيعيّ نحو التأكيد.
c("  والمضادّ يُرسَم أوّلاً",
  js.index("side(d.con") < js.index("side(d.pro"))
c("  ولا احتمال في العرض", "لا يُعرَض احتمال" in js)
wj = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "watches-page.js").read_text(encoding="utf-8")
c("  وزرٌّ في المراقبة", "w-case" in wj and "/api/case/" in wj)
tj = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "trades-page.js").read_text(encoding="utf-8")
c("  ولوحةٌ في الصفقات", "caseBox" in tj and "renderAnatomy" in tj)
# والأرقام قبل النموذج: التشريح فوريّ والتقييم ينتظر دقيقتين
c("  والأرقام قبل النموذج",
  tj.index("caseBox(t)") < tj.index("decisionBox(t)"))


sys.exit(c.report())
