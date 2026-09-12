# -*- coding: utf-8 -*-
"""«لماذا قد تنجح» — سببٌ مقيسٌ لا سببٌ مزعوم.

═══ ما يحرسه هذا الملف ═══

الماسح يكتب لكل إشارة سطر أسباب::

    خصم · قاع القناة · الدرجة 35 · هيكل صاعد · BOS ⇧ · فيبوناتشي

يقرأه المتداول فيرى ستّة مؤيّدات. وقياسُ الستّة على ٢٩٥ صفقة
محسومة يقول شيئاً آخر: واحدٌ منها — «قاع القناة» — يفوز ٣٤٪ مقابل
أساسٍ ٤٦٪، أي أنّه **يعمل ضدّه**.

فالمطلوب ليس سرد الأسباب، بل وزنُها. وهذا الملف يحرس ثلاثة أشياء:

    ١) أن يُقاس كل سبب على السجلّ لا يُصدَّق كما قيل.
    ٢) أن يُضبط تعدّد الفرضيات — ٢١ فرضية تُنتج «اكتشافاً» بالصدفة.
    ٣) أن يُعرض المضادّ دائماً — لا يُنتقى المؤيّد وحده.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.ai_advisor import evidence as ev  # noqa: E402
from scanner.ai_advisor import verdict as vd  # noqa: E402
from scanner.ai_advisor import why as wy  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def trades(won: int, lost: int, reasons: str, start: int = 0) -> list[dict]:
    out = []
    for i in range(won + lost):
        out.append({"id": start + i, "symbol": f"S{start + i}",
                    "market": "crypto", "timeframe": "1h", "side": "buy",
                    "grade": "B", "source": "auto", "score": 30.0, "rr": 2.0,
                    "reasons": reasons,
                    "status": "won" if i < won else "lost",
                    "r_multiple": 2.0 if i < won else -1.0})
    return out


# ── ١) التقسيم والتوحيد ──
check("١ الفاصل يُقسَّم",
      wy.split_reasons("أ · ب · ج") == ["أ", "ب", "ج"])
check("  والفراغ يُسقَط", wy.split_reasons(" · أ ·  · ") == ["أ"])
check("  والفارغ كلّه", wy.split_reasons(None) == [])
# «الدرجة 35» و«الدرجة 41» سببٌ واحد بقيمتين — وتركهما منفصلين
# يفتّت السجلّ إلى عشرات المجموعات كلٌّ منها دون حدّ النطق
check("  والمرقَّم يُوحَّد",
      wy.split_reasons("الدرجة 35") == wy.split_reasons("الدرجة 41"),
      str(wy.split_reasons("الدرجة 35")))
check("  والمكرّر مرّة واحدة",
      wy.split_reasons("أ · أ · ب") == ["أ", "ب"])


# ── ٢) ضبط تعدّد الفرضيات ──
#
# قِيس على السجلّ الحقيقي: ٢١ سبباً لها عيّنة كافية، ستّة منها
# «ذات دلالة» منفردةً، و**صفر** ينجو الضبط. أصغر p = 0.009 وعتبة
# الرتبة الأولى 0.05×1/21 = 0.0024.
bh = wy.benjamini_hochberg
check("٢ الفارغ لا يكسر", bh([]) == [])
check("  والواحدة القويّة تنجو", bh([0.001]) == [True])
check("  والواحدة الضعيفة لا", bh([0.20]) == [False])
real = [0.009, 0.010, 0.021, 0.041, 0.044, 0.044, 0.080, 0.089, 0.106,
        0.170, 0.179, 0.194, 0.234, 0.337, 0.384, 0.384, 0.444, 0.465,
        0.631, 0.657, 1.000]
check("  وقيم السجلّ الحقيقية لا ينجو منها شيء",
      sum(bh(real)) == 0, str(sum(bh(real))))
# ولولا الضبط لنجت ستّ — وهو بالضبط ما يُتوقَّع بالصدفة
check("  ولولا الضبط لمرّت ستّ",
      sum(1 for p in real if p < 0.05) == 6)
# ═══ الإجراء صعوديّ لا فرديّ ═══
#
# أوّل ما كتبتُ هنا توقّعتُ ``[0.001, 0.04, 0.9] → [T, T, F]``،
# والصواب ``[T, F, F]``: عتبة الرتبة الثانية 0.05×2/3 = 0.0333
# و0.04 فوقها. الخطأ كان في توقّعي لا في الشيفرة.
#
# والخاصّية الصعوديّة تظهر هنا: 0.02 يتجاوز عتبة رتبته
# (0.0167)، ومع ذلك يُقبل لأنّ رتبةً **أعلى** نجحت — وهو ما
# يميّز بنياميني-هوخبرغ عن فحص كل فرضية وحدها.
check("  والرتبة الثانية تُقاس بعتبتها",
      bh([0.001, 0.04, 0.9]) == [True, False, False],
      str(bh([0.001, 0.04, 0.9])))
check("  ورتبةٌ أعلى تسحب ما تحتها",
      bh([0.02, 0.03, 0.04]) == [True, True, True],
      str(bh([0.02, 0.03, 0.04])))
check("  ولولا الصعود لسقط الأوّل",
      0.02 > 0.05 * 1 / 3)
check("  والترتيب يُحفَظ للمدخلات",
      bh([0.9, 0.001]) == [False, True], str(bh([0.9, 0.001])))


# ── ٣) السبب يُقاس لا يُصدَّق ──
#
# «سبب سيّئ» يفوز 2 من 40، و«سبب حسن» 34 من 40، والأساس بينهما.
pop = (trades(2, 38, "سبب سيّئ", 0)
       + trades(34, 6, "سبب حسن", 100)
       + trades(20, 20, "سبب محايد", 200))
setup = {"symbol": "X", "market": "crypto", "timeframe": "1h",
         "grade": "B", "source": "auto", "score": 30.0, "rr": 2.0,
         "reasons": "سبب حسن · سبب سيّئ · سبب محايد · سبب مجهول"}
w = wy.explain(setup, pop)
by = {r.text: r for r in w.reasons}
check("٣ كل سبب يُقاس", len(w.reasons) == 4, str(list(by)))
check("  والحسن مؤيّد", by["سبب حسن"].supports, by["سبب حسن"].strength)
check("  والسيّئ مضادّ", by["سبب سيّئ"].against, by["سبب سيّئ"].strength)
check("  والمحايد لا هذا ولا ذاك",
      by["سبب محايد"].strength == "محايدة", by["سبب محايد"].strength)
# سببٌ لم يظهر في السجلّ قطّ لا يُحسب مؤيّداً بالصمت
check("  والمجهول يُعلَن مجهولاً",
      by["سبب مجهول"].strength == "لم تُختبر", by["سبب مجهول"].strength)
check("  ولا يُعدّ مؤيّداً", not by["سبب مجهول"].supports)

# ═══ المضادّ يُعرَض دائماً ═══
#
# سردُ المؤيّدات وحدها هو الذي جعل المستشار القديم لا يقول
# «لا تدخل» ولا مرّة في ١٦٤ مراجعة.
lines = w.as_lines()
check("  والمضادّ في المخرَج",
      any("[مضادّ]" in ln and "سبب سيّئ" in ln for ln in lines),
      str(lines))
check("  والعنوان يذكره",
      "يخسر" in w.headline() or "تخسر" in w.headline(), w.headline())
check("  والمجهول يُذكر عدداً", any("[مجهول]" in ln for ln in lines))


# ── ٤) الترتيب بالإسناد ──
check("٤ الأقوى إسناداً أوّلاً",
      w.reasons[0].strength in ("أثبتت", "مبشّرة"), w.reasons[0].strength)
check("  والدرجات معرَّفة",
      set(r.strength for r in w.reasons) <= set(wy.STRENGTH))


# ── ٥) العدّ العربي ──
#
# نصٌّ يُقرأ على أنّه من النظام؛ وركاكته تجعله يُقرأ ترجمةً آلية.
check("٥ المفرد", wy.count_ar(1, "سبب") == "سبب واحد")
check("  والمثنّى", wy.count_ar(2, "سبب") == "سببان")
check("  والجمع", wy.count_ar(3, "سبب") == "3 أسباب")
check("  والتمييز", wy.count_ar(11, "سبب") == "11 سبباً")
check("  والصفة تطابق",
      wy._adj(2, "مبشّر", "مبشّران", "مبشّرة") == "مبشّران"
      and wy._adj(5, "مبشّر", "مبشّران", "مبشّرة") == "مبشّرة")
for n in (1, 2, 3, 11):
    h = wy.WhyPack([wy.Reason("ر", None, "ضدّك")] * n, 21, 0).headline()
    check(f"  ولا «{n} سبب» حرفياً", not re.search(rf"\b{n} سبب\b", h), h)


# ── ٦) الاندماج مع الأدلّة ──
pk = ev.for_prospective({**setup, "entry": 100.0, "stop": 95.0,
                         "target1": 110.0}, pop)
blk = pk.as_prompt_block()
check("٦ الحزمة تحمل التفسير", pk.why is not None)
check("  ويظهر في كتلة الأدلّة", "[مؤيّد]" in blk and "[مضادّ]" in blk)
# إشارة بلا أسباب مسجّلة لا تخترع تفسيراً
bare = ev.for_prospective({"symbol": "Y", "market": "crypto",
                           "timeframe": "1h", "grade": "B",
                           "source": "auto"}, pop)
check("  وبلا أسباب لا تفسير", bare.why is None)

# ═══ كل رقمٍ معروضٍ مسموحٌ بذكره ═══
#
# هذا العطب وقع ثلاث مرّات: «27 نقطة» رُفضت، ثمّ «64٪» (صورة 63.9
# المطبوعة)، ثمّ حدود الشرائح «1.5–2.5» ونصّ «اختراق قمة 20 شمعة».
# القائمة المعدودة يدوياً تتخلّف عن العرض دائماً — فتُشتقّ منه.
#
# وفاحصٌ يرفض الصواب أسوأ من متساهل: الأوّل يُدرَّب المستخدم على
# تجاهله، والثاني يُصلَح.
allowed = pk.numbers
shown = re.sub(r"\[\s*-?\d+\.?\d*\s*–\s*-?\d+\.?\d*\s*\]", " ", blk)
shown = re.sub(r"^\[\d+\]", " ", shown, flags=re.M)
leaked = [t for t in re.findall(r"-?\d+\.?\d*", shown)
          if not any(abs(float(t) - a) < 1e-6 for a in allowed)]
check("  ولا رقم معروضٍ ممنوع", not leaked, str(leaked))

# ═══ إلّا حدّي فاصل الثقة ═══
#
# مرّ مخرَجٌ يقول «احتمال النجاح 88٪» — و88 هو الحدّ الأعلى
# للفاصل [49–88] لا الاحتمال. اقتطافُ الطرف المتفائل وعرضه نقطةً.
edge_pop = trades(13, 5, "سبب نادر", 0) + trades(40, 55, "غيره", 100)
epk = ev.for_prospective({"symbol": "Z", "market": "crypto",
                          "timeframe": "1h", "grade": "B",
                          "source": "auto", "score": 30.0, "rr": 2.0,
                          "entry": 100.0, "stop": 95.0, "target1": 110.0,
                          "reasons": "سبب نادر"}, edge_pop)
if epk.rate is not None and epk.rate.readable:
    hi = round(100 * epk.rate.high)
    en = epk.numbers
    # يُسمح فقط إن صادف رقماً آخر معروضاً فعلاً
    txt = re.sub(r"\[\s*-?\d+\.?\d*\s*–\s*-?\d+\.?\d*\s*\]", " ",
                 epk.as_prompt_block())
    coincides = str(hi) in txt
    check("  وحدّ الفاصل الأعلى ممنوع",
          coincides or not any(abs(x - hi) < 1e-6 for x in en), str(hi))
    raw = json.dumps({"القرار": "ادخل", "السبب": f"احتمال النجاح {hi}٪",
                      "الرقم": "95", "الإبطال": "95", "الثقة": 70},
                     ensure_ascii=False)
    v = vd.parse(raw, epk, "prospective")
    check("  والمخرَج المقتطِف يُرفض", not v.accepted, v.rejected_because)


# ── ٧) الموجّه يشرح درجة الإسناد ──
#
# بلا هذا يقرأ النموذج «مبشّرة» و«أثبتت» سواءً فيبني يقيناً على
# ملاحظة.
pr = vd.build_prompt(pk, "prospective")
check("٧ الموجّه يفرّق بين الدرجتين",
      "أثبتت" in pr["user"] and "مبشّرة" in pr["user"])
check("  ويأمر بذكر المضادّ", "[مضادّ]" in pr["user"])
check("  ويبقى موجزاً", len(pr["user"]) < 2600, str(len(pr["user"])))
# وبلا تفسير لا تُضاف التعليمات
check("  وبلا تفسير لا تُقحَم",
      "أثبتت" not in vd.build_prompt(bare, "prospective")["user"])


# ── ٨) الواجهة البرمجية ──
views = (ROOT / "web" / "dashboard" / "advice_views.py").read_text(
    encoding="utf-8")
check("٨ الأدلّة تُصدِّر التفسير", '"why": _why_json(' in views)
for key in ("headline", "supporting", "opposing", "untested", "tested"):
    check(f"  وفيه {key}", f'"{key}"' in views)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "advice.js").read_text(encoding="utf-8")
check("  والواجهة ترسمه", "whyBlock" in js and "d.why" in js)
check("  وتفصل الدرجات بلون", "STRENGTH_TONE" in js)
check("  وتعرض المضادّ", "opposing" in js)
check("  وتذكر عدد الفرضيات", "w.tested" in js)


# ── النتيجة ──
bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
