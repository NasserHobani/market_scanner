# -*- coding: utf-8 -*-
"""المستشار: أدلّةٌ مقيسة وحكمٌ مفحوص — لا كلامٌ لطيف.

═══ العطب المقيس ═══

قِيست ١٦٤ مراجعة أنتجها المستشار القديم::

    actionable_advice        فارغ 164/164  (100٪)
    positive_signals         فارغ 164/164  (100٪)
    data_quality_note        فارغ 164/164  (100٪)
    invalidation_conditions  فارغ 145/164  ( 88٪)
    شرط إبطال برقم محدَّد        0/164  (  0٪)
    احتمال إحصائي               0/164  (  0٪)
    في وضع الظلّ              164/164  (100٪)

    الفعل: بلا فعل 123 · انتظر 30 · تجنّب 3 · **اشترِ: صفر**

ومخرَجٌ حرفيّ::

    ما يُراقَب:   «التحوّل في الاتجاه»
    شرط الإبطال: «السعر يتجاوز مناطق المقاومة»

الأوّل إعادةُ صياغةٍ للسؤال. والثاني **يناقض التحليل**: النصّ
يجعل المقاومة خطراً ثمّ يجعل تجاوزها إبطالاً — وتجاوزها تأكيد.

═══ التشخيص ═══

العقد ستّة وثلاثون حقلاً. والحقول الفارغة ١٠٠٪ هي وحدها التي
تتطلّب **رقماً أو موقفاً**؛ أمّا ``summary`` و``reasoning``
فتقبلان الكلام العامّ فمُلئتا به.

═══ والفصل الذي يحرسه هذا الملف ═══

    · ``evidence`` يحسب الأرقام من سجلّك.
    · النموذج يشرح ويقرّر **بها**.
    · و``verdict`` يرفض ما لا يُفحص.

فإن كتب النموذج «٧٢٪» ولم تكن في الأدلّة فقد اخترعها — ورقمٌ بلا
مصدر يُبنى عليه قرارُ مال أخطر من صمت.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.ai_advisor import evidence as ev  # noqa: E402
from scanner.ai_advisor import verdict as vd  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def pop(n_win: int, n_loss: int, **traits) -> list[dict]:
    base = {"market": "crypto", "timeframe": "1h", "side": "buy",
            "grade": "B", "source": "auto", "score": 30.0, "rr": 2.0}
    base.update(traits)
    return ([{**base, "symbol": f"W{i}", "status": "won", "r_multiple": 2.0}
             for i in range(n_win)]
            + [{**base, "symbol": f"L{i}", "status": "lost",
                "r_multiple": -1.0} for i in range(n_loss)])


# ── ١) المعدّل يُحسب ولا يُخترَع ──
p = pop(30, 30)
r = ev.rate_of(p[:20], p)
check("١ المعدّل يُحسب", r.total == 20 and r.wins == 20)
check("  والأساس من السكّان", abs(r.baseline - 0.5) < 1e-9)
check("  وله فاصل ثقة", 0.0 < r.low < r.high <= 1.0)
check("  والعربية تحمل العدد",
      "20" in r.arabic() and "٪" in r.arabic(), r.arabic())

# ═══ العيّنة الصغيرة لا يُنطق فيها برقم ═══
#
# «٦٧٪ فوزاً» عن ثلاث صفقات جهلٌ يرتدي ثوب العلم.
small = ev.rate_of(p[:3], p)
check("  والعيّنة الصغيرة لا تُقرأ", small.readable is False)
check("  وتقول لماذا", "دون حدّ النطق" in small.arabic(), small.arabic())
check("  والحدّ معقول", 8 <= ev.MIN_SAMPLE <= 40, str(ev.MIN_SAMPLE))

# فرقٌ ضئيل لا يُعدّ ميزة مهما كبرت العيّنة
tiny = ev.rate_of(pop(31, 29), p)
check("  والفرق الضئيل ليس ميزة", tiny.significant is False,
      f"{tiny.edge:+.1f}")


# ── ٢) السبب من التكرار لا من البلاغة ──
#
# كل خاسرة يمكن أن يُروى لها سببٌ بعد وقوعها. والسؤال: هل يتكرّر؟
mixed = (pop(2, 18, source="breakout") + pop(40, 20, source="auto"))
losing = [t for t in mixed if t["source"] == "breakout"][0]
causes = ev.causes_for(losing, mixed)
names = [c.trait for c in causes]
check("٢ السمة الخاسرة تُرصَد", "source=breakout" in names, str(names))
brk = next(c for c in causes if c.trait == "source=breakout")
check("  بمعدّلها الحقيقي", brk.rate.wins == 2 and brk.rate.total == 20)
check("  وتُعلَن ذات دلالة", brk.rate.significant is True, brk.rate.arabic())
# الترتيب بالبُعد عن الأساس لا بالفوز: سمةٌ تفوز ٩٠٪ وأساسها ٨٨٪
# لا تفسّر شيئاً
check("  والترتيب بالبُعد عن الأساس",
      abs(causes[0].rate.edge) >= abs(causes[-1].rate.edge))

# ═══ حقيقةٌ واحدة لا تُعدّ ثلاثاً ═══
#
# قِيس على السجلّ الحقيقي (٢٩٢ صفقة) فخرجت ثلاثة «أسباب» بأرقامٍ
# متطابقة — ``grade=—`` و``source=breakout`` و``action=breakout`` —
# وهي الصفقات الثمانية عشر **نفسها**. وثلاثة أسطر متطابقة تُقرأ
# إجماعاً وهي دليلٌ واحد.
twins = ([{**t, "grade": "—"} for t in pop(2, 18, source="breakout")]
         + pop(40, 20, source="auto", grade="A"))
for i, t in enumerate(twins):
    t["id"] = i
tw_loss = [t for t in twins if t["source"] == "breakout"][0]
tc = ev.causes_for(tw_loss, twins)
sets = [c.members for c in tc]
check("  والسمتان المتطابقتان سببٌ واحد",
      len(sets) == len(set(sets)), str([c.trait for c in tc]))
merged = next((c for c in tc if c.aliases), None)
check("  ويُذكر المرادف لا يُخفى",
      merged is not None and "=" in merged.arabic(),
      merged.arabic() if merged else "لا دمج")
# والدمج لا يبتلع سمةً تصف صفقاتٍ أخرى
check("  والسمة المختلفة تبقى",
      any(not c.aliases for c in tc) or len(tc) == 1)

# سمةٌ دون العيّنة لا تُذكر سبباً
rare = ev.causes_for({**losing, "grade": "Z"}, mixed)
check("  والسمة النادرة تُسقَط",
      "grade=Z" not in [c.trait for c in rare])


# ── ٣) الحزمة تُنتج أرقاماً مسموحة فقط ──
pk = ev.for_prospective(
    {"symbol": "X", "market": "crypto", "timeframe": "1h", "grade": "B",
     "source": "auto", "score": 30.0, "rr": 2.0,
     "entry": 100.0, "stop": 95.0, "target1": 110.0}, mixed)
check("٣ الحزمة تُبنى", pk.symbol == "X")
check("  وفيها المستويات", pk.levels.get("الوقف") == 95.0)
nums = pk.numbers
check("  والمستويات مسموحة", 95.0 in nums and 110.0 in nums)

# ═══ حدّا فاصل الثقة لا يُقتطفان ═══
#
# أضفتُهما أوّلاً فمرّ مخرَجٌ يقول «احتمال النجاح 88٪» — و88 هو
# الحدّ الأعلى للفاصل [49–88] لا الاحتمال. اقتطافُ الطرف المتفائل
# وعرضه نقطةً.
if pk.rate is not None and pk.rate.readable:
    hi = round(100 * pk.rate.high)
    lo = round(100 * pk.rate.low)
    check("  وحدّا الفاصل خارج المسموح",
          hi not in nums and lo not in nums, f"[{lo}–{hi}]")


# ── ٤) الفاحص يرفض ما لا يُفحَص ──
def raw(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


ok_num = int(pk.rate.pct) if (pk.rate and pk.rate.readable) else 95

BAD = [
    ("مخرَج فارغ", "", "مخرَج فارغ"),
    ("بلا JSON", "لا أعرف بصراحة", "لا JSON"),
    ("JSON تالف", "{القرار: ادخل", "JSON"),
    ("حقل ناقص", raw(القرار="ادخل", السبب="جيد", الرقم="95", الثقة=50),
     "حقول ناقصة"),
    ("حقل الرقم بلا رقم",
     raw(القرار="ادخل", السبب="جيد", الرقم="مرتفع", الإبطال="95", الثقة=50),
     "بلا رقم"),
    ("قرار غير معرَّف",
     raw(القرار="ربما", السبب="جيد", الرقم="95", الإبطال="95", الثقة=50),
     "قرار غير معرَّف"),
    ("رقم مخترَع",
     raw(القرار="ادخل", السبب="فرصة 63.7٪", الرقم="95", الإبطال="95",
         الثقة=50),
     "ليس من الأدلّة"),
    ("كلامٌ يصف السؤال",
     raw(القرار="انتظر", السبب="راقب التحوّل في الاتجاه", الرقم="95",
         الإبطال="95", الثقة=50),
     "تصف السؤال"),
]
for name, text, expect in BAD:
    v = vd.parse(text, pk, "prospective")
    check(f"٤ يرفض: {name}", not v.accepted, "قُبل!")
    check("  بالسبب الصحيح", expect in v.rejected_because,
          v.rejected_because)

good = raw(القرار="ادخل", السبب="مستوى الوقف 95",
           الرقم="95", الإبطال="95", الثقة=70)
gv = vd.parse(good, pk, "prospective")
check("  ويقبل المفحوص", gv.accepted, gv.rejected_because)
check("  ويعرض حقوله", "ادخل" in gv.arabic())

# والعقد صغير عمداً: ٣٦ حقلاً كانت سبب الفراغ
check("  والعقد خمسة حقول", len(vd.PROSPECTIVE_FIELDS) == 5
      and len(vd.SETTLED_FIELDS) == 5)
check("  والقرارات محدودة", set(vd.DECISIONS) == {"ادخل", "لا تدخل",
                                                  "انتظر"})


# ── ٥) الموجّه يمنع الاختراع صراحةً ──
pr = vd.build_prompt(pk, "prospective")
check("٥ الموجّه فيه الأدلّة", "الأدلّة:" in pr["user"])
check("  ويمنع الرقم الخارجي",
      "لا تذكر رقماً غير موجود" in pr["user"])
check("  ويمنع كلام التحفّظ", "راقب التحوّل" in pr["user"])
check("  ويسمح بالعجز صراحةً", "الأدلّة لا تكفي" in pr["user"])
# ثلاثون سطراً من التعليمات على نموذجٍ محلّي تُضيّع المطلوب
check("  والموجّه موجز", len(pr["user"]) < 2500, str(len(pr["user"])))


# ── ٦) الربط ──
adv = (ROOT / "scanner" / "ai_advisor" / "advise.py").read_text(encoding="utf-8")
code = "\n".join(l for l in adv.splitlines() if not l.strip().startswith("#"))
check("٦ محاولتان لا واحدة", "MAX_ATTEMPTS = 2" in adv)
# إعادة الموجّه نفسه تُنتج الخطأ نفسه
check("  والثانية تحمل سبب الرفض",
      "محاولتك السابقة رُفضت" in adv)
check("  والفشل يُعاد كحكمٍ مرفوض لا استثناء",
      "rejected_because=f\"فشل النداء" in adv)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for n in ("api_advice_evidence", "api_advice_settled",
          "api_advice_prospective", "api_advice_status"):
    check(f"  المسار {n}", f'name="{n}"' in urls)

views = (ROOT / "web" / "dashboard"
         / "advice_views.py").read_text(encoding="utf-8")
import ast  # noqa: E402

defined = {n.name for n in ast.walk(ast.parse(views))
           if isinstance(n, ast.FunctionDef)}
for n in ("api_advice_evidence", "api_advice_settled",
          "api_advice_prospective", "api_advice_status"):
    check(f"  والدالّة {n} معرَّفة", n in defined)

# الأدلّة بلا نموذج: عطلُه لا يحجب أرقام سجلّك
check("  والأدلّة نقطةٌ مستقلّة عن النموذج",
      "def api_advice_evidence" in views
      and "advise" not in views.split("def api_advice_evidence")[1][:400])

# ولا وضع ظلّ: مستشارٌ لا يُسمَع ليس مستشاراً.
#
# والفحص على **الشيفرة** لا على النصّ: النسخة الأولى بحثت في الملفّ
# كلّه فرصدت ذكر ``shadow_mode`` في شرح العطب القديم وظنّته سلوكاً.
# وفحصٌ يقرأ التوثيق ويحكم به يمنع توثيق ما أُصلح.
def _code_only(src: str) -> str:
    """الشيفرة بلا تعليقات ولا سلاسل نصّية."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


check("  ولا وضع ظلّ في المسار الجديد",
      "shadow_mode" not in _code_only(views)
      and "shadow_mode" not in _code_only(adv))
# ويُذكر في الشرح عمداً — كي يُعرَف ما استُبدل ولماذا
check("  ويُشرَح لماذا أُلغي", "shadow_mode" in adv)


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
