# -*- coding: utf-8 -*-
"""سياق البتكوين: تموضع · أحداث · أخبار — وما لا يُدّعى.

═══ ثلاثة مواضع يكذب فيها السياق ═══

الأوّل: **وصفٌ يصير إشارة.** التمويل والمراكز المفتوحة لا
تتنبّآن بالاتجاه — تصفان تكلفة التموضع الحالي. وربطُهما بالدرجة
قبل قياسٍ يضيف وزناً لم يُختبر إلى نظامٍ كلّ أوزانه مقيسة.

الثاني: **الغائب يصير طبيعياً.** مئينٌ لا تكفيه العيّنة يعني «لا
أعرف» لا «لا ازدحام» — وعدُّه طبيعياً يعطي طمأنينةً لم تُقَس.

الثالث: **تقويمٌ نفد يعرض فراغاً.** والفراغ يُقرأ «لا أحداث
قادمة»، وهو ادّعاء كاذب. فالفرق بين «لا حدث» و«لا أعرف» يجب أن
يُقال.

═══ ورابعٌ في الواجهة ═══

``confluence`` مصفوفةُ أسباب لا عدد. و‏``[] + "/3"`` في جافاسكربت
= ``"/3"`` — فظهر «3/» في الشاشة. والمقام «3» مكتوبٌ باليد بينما
الحدّ الحقيقيّ ``min_confluence`` = 2: الشاشة تعرض مقياساً
والمانع يحسب بآخر.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.analysis import events as EV  # noqa: E402
from scanner.analysis import positioning as POS  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


# ═══════════ ١) التموضع: وصفٌ لا إشارة ═══════════
_psrc = code_of(ROOT / "scanner" / "analysis" / "positioning.py")
c("١ لا يدخل الدرجة", '"scored": False' in _psrc)
_praw = source_of(ROOT / "scanner" / "analysis" / "positioning.py")
c("  وسببه مكتوب", "لم تُقَس بعد" in _praw)
# ولا يُستورَد في محرّك التسجيل — والنيّة وحدها لا تكفي
for mod in ("scanner/scoring/engine.py", "scanner/strategies/pes.py"):
    c(f"  ولا يُستورَد في {Path(mod).name}",
      "positioning" not in code_of(ROOT / mod))


# ═══════════ ٢) الغائب لا يُصنَّف طبيعياً ═══════════
st, why = POS._classify(None, 10.0)
c("٢ مئينٌ غائب = غير معروف", st == "unknown", f"{st} · {why[:40]}")
c("  ولا يُسمّى طبيعياً", st != "neutral")
c("  والمزدحم يحتاج الاثنين",
  POS._classify(95.0, 10.0)[0] == "crowded_long")
# تمويلٌ مرتفع بلا تراكم مراكز ليس ازدحاماً بعد
c("  والمرتفع وحده «تسخين»",
  POS._classify(95.0, 0.0)[0] == "heating",
  str(POS._classify(95.0, 0.0)))
c("  والمنخفض «تصفية»", POS._classify(5.0, -9.0)[0] == "reset")
c("  والوسط طبيعي", POS._classify(50.0, 1.0)[0] == "neutral")
# وكلّ حالةٍ لها وسمٌ عربيّ — وإلّا ظهر مفتاحٌ إنجليزيّ في الشاشة
c("  ولكلّ حالةٍ وسم",
  all(s in POS.STATE_LABELS for s in POS.STATES))


# ═══════════ ٣) المئين لا يُحسب على عيّنةٍ قصيرة ═══════════
#
# عشر قيمٍ تعطي «مئيناً» هو ترتيبُ عشر قيم — رقمٌ يبدو دقيقاً
# وليس كذلك.
c("٣ العيّنة القصيرة لا تعطي مئيناً",
  POS._pctile([0.0001] * 10, 0.0002) is None)
c("  والكافية تعطيه",
  POS._pctile([i / 10000.0 for i in range(200)], 0.0199) is not None)
_p = POS._pctile([0.0] * 100 + [1.0] * 100, 0.9)
c("  والقيمة في موضعها", _p is not None and 45 <= _p <= 55, str(_p))


# ═══════════ ٤) حدّ المراكز المفتوحة معلن ═══════════
#
# ثلاثون يوماً لا تكفي لمئين. وعرضُ النسبة بلا هذا القيد يوحي
# بسياقٍ تاريخيّ لا وجود له.
_fsrc = source_of(ROOT / "scanner" / "adapters" / "binance_futures.py")
c("٤ حدّ الثلاثين يوماً مكتوب", "OI_HISTORY_DAYS = 30" in _fsrc)
c("  ويُعرَض مع الرقم", "oi_note" in _psrc)
c("  ولا مفتاح للمشتقّات", "api_key" not in _fsrc.lower()
  and "secret" not in _fsrc.lower())
# ‏fapi لا data-api: الأخير للسوق الفوريّ ولا يعرف هذه المسارات
c("  والمضيف مضيف المشتقّات", "fapi.binance.com" in _fsrc)
# والتقدير المتحرّك لا يدخل حساباً
c("  والمعدّل الجاري للسياق فقط", "يعيد الرسم بطبيعته" in _fsrc)


# ═══════════ ٥) التقويم يقول حين ينفد ═══════════
_far = date(2026, 1, 1)
h = EV.calendar_health(today=date(2099, 1, 1))
c("٥ التقويم المنتهي يُعلَن", h.get("ok") is False, str(h)[:90])
c("  وسببه مكتوب", "قديم" in h.get("why", ""), h.get("why", "")[:60])
h2 = EV.calendar_health(today=_far)
c("  والحيّ يمرّ", h2.get("ok") is True, str(h2)[:80])
# ولا حدثَ بلا تاريخٍ صالح
c("  والتواريخ تُقرأ", EV._parse("2026-10-14") == date(2026, 10, 14))
c("  والمعطوب يُهمَل", EV._parse("غداً") is None)
_ups = EV.upcoming(60, today=date(2026, 9, 1), with_halving=False)
c("  والقادم مرتّب بالأقرب",
  all(_ups[i]["days"] <= _ups[i + 1]["days"] for i in range(len(_ups) - 1)),
  str([u["days"] for u in _ups]))
c("  والماضي لا يُعرَض",
  all(u["days"] >= 0 for u in _ups), str([u["days"] for u in _ups]))
# وفحصٌ يعتمد على شبكةٍ يسقط لأسبابٍ لا علاقة لها بما يفحصه
c("  والنصف يُعزَل عن الفواحص",
  all(u["kind"] != "halving" for u in _ups),
  str([u["kind"] for u in _ups]))


# ═══════════ ٦) النصف موعدٌ لا هدف ═══════════
#
# نماذج السعر المبنيّة على النصف تفشل خارج العيّنة ولا تتفوّق على
# تنبّؤٍ ساذج بسعر اليوم. وعرضُ هدفٍ منها يوهم بمعرفةٍ لا تُملَك —
# وهو المعيار نفسه الذي أُخفيت به احتمالات LightGBM هنا.
_esrc = source_of(ROOT / "scanner" / "analysis" / "events.py")
c("٦ النصف يُحسب من الكتلة", "HALVING_INTERVAL = 210_000" in _esrc)
c("  والتقدير يُعلَن تقديراً", '"approx": True' in _esrc)
c("  ولا هدف سعريّ منه",
  "S2F" in _esrc and "تفشل في الاختبار خارج العيّنة" in _esrc)
c("  ولا دالّة سعر", "def price_target" not in _esrc
  and "fair_value" not in _esrc)


# ═══════════ ٧) العناوين لا تُوسَم ═══════════
_bsrc = source_of(ROOT / "web" / "dashboard" / "btc_views.py")
c("٧ العناوين للقراءة", "لا تدخل أيّ حساب ولا تُوسَم" in _bsrc)
# وكلّ مصدرٍ في ``try`` منفصل: معطوبٌ واحد كان سيبتلع الثلاثة
_ctx = _bsrc.split("def _context_payload")[1][:2500]
c("  وكلّ مصدرٍ معزول", _ctx.count("try:") >= 3, str(_ctx.count("try:")))
# ولا شبكة في رسم الصفحة — القاعدة المكتوبة أعلى الملفّ
c("  والسياق بنقطةٍ منفصلة", "def api_btc_context" in _bsrc)
_urls = code_of(ROOT / "web" / "dashboard" / "urls.py")
c("  والمسار مسجَّل", '"api/btc/context/"' in _urls)


# ═══════════ ٨) الواجهة: مقياسٌ واحد للحكم والعرض ═══════════
_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "btc-page.js").read_text(encoding="utf-8")
c("٨ لا مقام مكتوب باليد", '+ "/3"' not in _js, "ما زال 3 مكتوباً")
c("  والعدد من طول المصفوفة", "(d.confluence || []).length" in _js)
c("  والمقام من الخادم", "sc.confluence_min" in _js)
_v = code_of(ROOT / "web" / "dashboard" / "views.py")
c("  والخادم يرسله", '"scales": _scales(cfg)' in _v)
c("  من مصدر الحكم نفسه", "min_confluence" in _v)
c("  والدرجة بسقفها", "score_max" in _v and "score_max" in _js)
# والحكم سطرٌ واحد فوق الكلّ
c("  والحكم يُرسَل", "def _verdict" in _v)
c("  ويُرسَم أوّلاً", "paintVerdict(d);" in _js)
c("  والمانع فيه", "blocker" in _v.split("def _verdict")[1][:900])


sys.exit(c.report())
