# -*- coding: utf-8 -*-
"""عقدُ المستشار الجديد — خمسة حقول تُملأ، لا ستّة وثلاثون تُترَك.

═══ لماذا صَغُر العقد ═══

العقد القديم ستّة وثلاثون حقلاً. والقياس على ١٦٤ مخرَجاً::

    actionable_advice     فارغ 100٪
    positive_signals      فارغ 100٪
    negative_signals      فارغ 100٪
    data_quality_note     فارغ 100٪
    invalidation برقم     فارغ 100٪

والحقول الفارغة كلّها هي **التي تتطلّب التزاماً**. أمّا التي
تُملأ (summary · reasoning · risks) فتقبل الكلام العامّ، فمُلئت به.

ونموذجٌ محلّيّ يُطلب منه ستّة وثلاثون حقلاً بالعربية دفعةً واحدة
يوزّع انتباهه عليها كلّها، فيخرج كلٌّ منها رقيقاً. والتقليل هنا
ليس تبسيطاً بل شرطُ العمق: خمسة حقول إلزامية أنفع من ستّة
وثلاثين اختيارية.

═══ ولماذا التحقّق من الأرقام ═══

النموذج لا يعرف احتمالاً. وإن كتب «٧٢٪» من عنده فهو اختراع —
ورقمٌ بلا مصدر يُبنى عليه قرارُ مال أخطر من صمت.

فكل رقم في المخرَج يجب أن يكون **من حزمة الأدلّة** المحسوبة في
``evidence.py``. وما سواه يُرفَض المخرَج كلّه لأجله.

═══ والرفض موقف ═══

مخرَجٌ بلا رقم أو بلا قرار يُرمى، ويُكتب مكانه أنّ النموذج لم
يُنتج جواباً قابلاً للفحص. وهذا خيرٌ من عرض كلامٍ لطيف: الأوّل
يُعلمك أنّك بلا مستشار، والثاني يوهمك أنّ لك مستشاراً.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any

# ═══ العقدان ═══
#
# لكلٍّ خمسة حقول. والأسماء عربية عمداً: النموذج يكتب بالعربية،
# ومطالبته بمفاتيح إنجليزية تُضيف طبقة ترجمةٍ تُفقد الدقّة.

SETTLED_FIELDS = ("السبب", "الرقم", "متكرر", "القاعدة", "الثقة")
PROSPECTIVE_FIELDS = ("القرار", "السبب", "الرقم", "الإبطال", "الثقة")

DECISIONS = ("ادخل", "لا تدخل", "انتظر")

# أقلّ رقمٍ يُعتدّ به في المطابقة — الأرقام الصغيرة كـ«1» و«2»
# تظهر صدفةً في أي نصّ.
_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


@dataclass
class Verdict:
    """حكمٌ مفحوص — أو مرفوضٌ بسببه."""

    kind: str
    accepted: bool
    fields: dict[str, Any] = field(default_factory=dict)
    rejected_because: str = ""
    raw: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def arabic(self) -> str:
        if not self.accepted:
            return f"لم يُنتج النموذج جواباً قابلاً للفحص — {self.rejected_because}"
        return " · ".join(f"{k}: {v}" for k, v in self.fields.items() if v)


def build_prompt(pack, kind: str) -> dict[str, str]:
    """الموجّه: أدلّةٌ مرقّمة، وخمسة حقول، ومنعٌ صريح للاختراع."""
    if kind == "settled":
        task = (
            "حلّل هذه الصفقة **المحسومة** وقل لماذا انتهت كما انتهت.\n"
            "أجب بـ JSON فيه هذه المفاتيح الخمسة فقط:\n"
            '  "السبب"   — جملة واحدة: لماذا فازت أو خسرت.\n'
            '  "الرقم"   — رقم واحد من الأدلّة يسند السبب.\n'
            '  "متكرر"   — "نعم" إن كان سبباً يتكرّر في السجلّ، '
            'و"لا" إن كانت حالة مفردة.\n'
            '  "القاعدة" — قاعدة واحدة بصيغة رقمية كانت ستغيّر '
            "النتيجة، أو \"لا شيء\".\n"
            '  "الثقة"   — عدد من 0 إلى 100.\n'
        )
    else:
        task = (
            "هل يدخل المتداول هذه الصفقة؟\n"
            "أجب بـ JSON فيه هذه المفاتيح الخمسة فقط:\n"
            '  "القرار"  — واحدة من: "ادخل" أو "لا تدخل" أو "انتظر".\n'
            '  "السبب"   — جملة واحدة.\n'
            '  "الرقم"   — رقم واحد من الأدلّة يسند القرار.\n'
            '  "الإبطال" — سعر محدَّد يبطل هذا القرار إن بلغه السوق.\n'
            '  "الثقة"   — عدد من 0 إلى 100.\n'
        )

    rules = (
        "\nقواعد ملزمة:\n"
        "• لا تذكر رقماً غير موجود في الأدلّة أعلاه. ولا تحسب "
        "أرقاماً جديدة.\n"
        "• إن لم تكفِ الأدلّة لقرار، فاكتب في السبب: "
        '"الأدلّة لا تكفي" — ولا تُجمّل.\n'
        "• جملة واحدة لكل حقل. لا مقدّمات ولا تحفّظات.\n"
        "• ممنوع: «قد» «ربما» «يُنصح بالحذر» «راقب التحوّل» — "
        "هذه كلماتٌ تصف السؤال لا تجيبه.\n"
    )

    # ═══ درجة الإسناد تُشرَح للنموذج ═══
    #
    # بلا هذا يقرأ النموذج «مبشّرة» و«أثبتت» سواءً، فيبني قراراً
    # على سببٍ لم ينجُ ضبط التعدّد ويقدّمه يقيناً. والفرق بينهما
    # هو الفرق بين ملاحظةٍ وحقيقة.
    if getattr(pack, "why", None) is not None:
        rules += (
            "\n• أسطر [مؤيّد] و[مضادّ] هي أسباب الإشارة مقيسةً على "
            "سجلّ المتداول:\n"
            "  «أثبتت» = نجت ضبط تعدّد الفرضيات — يُبنى عليها.\n"
            "  «مبشّرة» = فرقٌ ظاهر لم ينجُ الضبط — تُذكر ملاحظةً "
            "لا يقيناً.\n"
            "• إن وُجد [مضادّ] فاذكره في السبب. تجاهلُه انتقاءٌ "
            "للأدلّة.\n"
        )

    return {
        "system": ("أنت محلّل يجيب بالأرقام. تُعطى أدلّة مقيسة "
                   "وتبني عليها حكماً واحداً. لا تخترع رقماً، ولا "
                   "تُعيد صياغة السؤال."),
        "user": (f"الأدلّة:\n{pack.as_prompt_block()}\n\n{task}{rules}"),
    }


def _numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.finditer(text):
        try:
            out.append(float(m.group(0).replace(",", ".")))
        except ValueError:
            continue
    return out


def _grounded(value: Any, allowed: list[float], tol: float = 0.02) -> bool:
    """هل كل رقمٍ في القيمة من الأدلّة؟

    التسامح نسبيّ لا مطلق: النموذج قد يكتب ٧٢ بدل ٧٢٫٢، وهذا
    تقريبٌ مقبول. أمّا ٦٥ بدل ٧٢ فاختراع.
    """
    nums = _numbers_in(str(value))
    if not nums:
        return True                      # لا رقم = لا اختراع
    for n in nums:
        # النِسب المئوية والدرجات الصغيرة تمرّ: الثقة رقمٌ ذاتيّ
        if 0 <= n <= 100 and any(abs(n - a) <= max(1.0, abs(a) * tol)
                                 for a in allowed):
            continue
        if any(abs(n - a) <= max(1e-9, abs(a) * tol) for a in allowed):
            continue
        return False
    return True


def parse(raw: str, pack, kind: str) -> Verdict:
    """يفحص مخرَج النموذج ويقبله أو يرفضه بسببٍ مذكور."""
    fields_wanted = (SETTLED_FIELDS if kind == "settled"
                     else PROSPECTIVE_FIELDS)
    text = (raw or "").strip()
    if not text:
        return Verdict(kind, False, rejected_because="مخرَج فارغ", raw=raw)

    # الـJSON قد يأتي داخل سياج شيفرة أو مع مقدّمة
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return Verdict(kind, False,
                       rejected_because="لا JSON في المخرَج", raw=raw)
    try:
        data = json.loads(m.group(0))
    except ValueError as exc:
        return Verdict(kind, False,
                       rejected_because=f"JSON غير صالح: {str(exc)[:60]}",
                       raw=raw)
    if not isinstance(data, dict):
        return Verdict(kind, False, rejected_because="المخرَج ليس كائناً",
                       raw=raw)

    out = {k: data.get(k) for k in fields_wanted}

    missing = [k for k in fields_wanted
               if out.get(k) in (None, "", [], {})]
    if missing:
        return Verdict(kind, False, fields=out,
                       rejected_because="حقول ناقصة: " + " · ".join(missing),
                       raw=raw)

    # ═══ القرار من القائمة لا من الخيال ═══
    if kind == "prospective":
        d = str(out["القرار"]).strip()
        if d not in DECISIONS:
            return Verdict(kind, False, fields=out,
                           rejected_because=f"قرار غير معرَّف: {d!r}",
                           raw=raw)

    # ═══ لا رقم = لا حكم ═══
    #
    # هذا الشرط وحده يقتل ٩٥٪ من المخرجات القديمة — وذلك مقصود.
    if not _numbers_in(str(out["الرقم"])):
        return Verdict(kind, False, fields=out,
                       rejected_because="حقل «الرقم» بلا رقم", raw=raw)

    allowed = pack.numbers
    for key in fields_wanted:
        if key == "الثقة":
            continue
        if not _grounded(out[key], allowed):
            return Verdict(
                kind, False, fields=out,
                rejected_because=f"رقمٌ في «{key}» ليس من الأدلّة",
                raw=raw)

    # ═══ الكلام الذي يصف السؤال ═══
    banned = ("راقب التحوّل", "يُنصح بالحذر", "قد يستمر", "قد يتغير",
              "التحوّل في الاتجاه", "ينبغي المتابعة")
    joined = " ".join(str(out[k]) for k in fields_wanted)
    hit = [b for b in banned if b in joined]
    if hit:
        return Verdict(kind, False, fields=out,
                       rejected_because="عبارة تصف السؤال: " + hit[0],
                       raw=raw)

    return Verdict(kind, True, fields=out, raw=raw)


__all__ = ["Verdict", "build_prompt", "parse", "SETTLED_FIELDS",
           "PROSPECTIVE_FIELDS", "DECISIONS"]
