# -*- coding: utf-8 -*-
"""الأدلّة المقيسة — الأرقام التي يُبنى عليها الحكم، لا التي تُخترَع.

═══ لماذا وُجد هذا الملفّ ═══

قِيست ١٦٤ مراجعة أنتجها المستشار فكانت الحصيلة::

    actionable_advice        فارغ في 164/164  (100٪)
    invalidation_conditions  فارغ في 145/164  ( 88٪)
    شرط إبطال برقم محدَّد        0/164  (  0٪)
    معه احتمال إحصائي           0/164  (  0٪)
    توزيع الفعل: بلا فعل 123 · انتظر 30 · تجنّب 3 · **اشترِ: صفر**

ومثالٌ حرفيّ ممّا كان يُعرَض::

    ما يُراقَب: «التحوّل في الاتجاه · التحوّل في مستوى المقاومة»
    شرط الإبطال: «السعر يتجاوز مناطق المقاومة»

«راقب تحوّل الاتجاه» إعادةُ صياغةٍ للسؤال لا جواب. وشرط الإبطال
**متناقض**: النصّ يجعل المقاومة خطراً ثمّ يجعل تجاوزها إبطالاً —
وتجاوزها تأكيدٌ صاعد.

═══ التشخيص ═══

العقد كان **ستّة وثلاثين حقلاً** يُطلب من نموذجٍ محلّي ملؤها
بالعربية دفعةً واحدة. فيملأ ما يُملأ بالكلام العامّ، ويترك ما
يحتاج التزاماً فارغاً. والحقول «الفارغة ١٠٠٪» ليست صدفة: هي
وحدها التي تتطلّب **رقماً أو موقفاً**.

═══ والعلاج ليس ضبط الموجّه ═══

النموذج اللغوي لا يعرف احتمالاً. وإن قال «٧٢٪» فقد اخترعه، وهذا
أسوأ من صمته: رقمٌ بلا مصدر يُبنى عليه قرارُ مال.

فالتقسيم هنا صارم:

    · هذا الملفّ يحسب الأرقام من **صفقاتك المحسومة**.
    · والنموذج يشرح ويقرّر **بها** ولا يولّدها.
    · وما لم يُحسب هنا لا يُذكَر هناك.

فإن سأل المستخدم «ما احتمال نجاحها؟» كان الجواب معدّل الفوز
التاريخي للإعدادات المشابهة في سجلّه هو، بفاصل ثقة وعدد — لا
تخميناً لغويّاً.
"""
from __future__ import annotations

import re

# قوالب الاقتناص — تُعرَّف مرّة لا في كل نداء
_CI = re.compile(r"\[\s*-?\d+\.?\d*\s*–\s*-?\d+\.?\d*\s*\]")
_INDEX = re.compile(r"^\[\d+\]", re.M)
_NUM = re.compile(r"-?\d+\.?\d*")

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from scanner.postmortem.separation import (Z95, binom_two_sided_p,
                                           wilson_interval)

# ═══ أقلّ عيّنة يُنطق عندها برقم ═══
#
# دون هذا لا يُعطى احتمال أصلاً. وقول «٦٧٪ فوزاً» عن ثلاث صفقات
# أسوأ من قول «لا أعرف»: كلاهما جهل، لكنّ الأوّل يرتدي ثوب العلم.
MIN_SAMPLE = 12

# وفوق هذا يُعتدّ بالفرق عن معدّل الأساس
MIN_EDGE_PCT = 8.0


@dataclass(frozen=True)
class Rate:
    """معدّل فوز مقيس — بعدده وفاصل ثقته دائماً."""

    wins: int
    total: int
    low: float
    high: float
    baseline: float
    p_value: float

    @property
    def pct(self) -> float:
        return 100.0 * self.wins / self.total if self.total else 0.0

    @property
    def edge(self) -> float:
        return self.pct - self.baseline * 100.0

    @property
    def readable(self) -> bool:
        """هل العيّنة تكفي للنطق برقم؟"""
        return self.total >= MIN_SAMPLE

    @property
    def significant(self) -> bool:
        """هل الفرق عن الأساس يتجاوز الصدفة والهامش معاً؟"""
        return (self.readable and abs(self.edge) >= MIN_EDGE_PCT
                and self.p_value < 0.05)

    def arabic(self) -> str:
        if not self.readable:
            return (f"العيّنة {self.total} صفقة فقط — دون حدّ النطق "
                    f"({MIN_SAMPLE}). لا احتمال.")
        return (f"{self.wins} من {self.total} = {self.pct:.0f}٪ "
                f"[{100 * self.low:.0f}–{100 * self.high:.0f}] · "
                f"الأساس {self.baseline * 100:.0f}٪ · "
                f"الفارق {self.edge:+.0f} نقطة"
                + (" (يتجاوز الصدفة)" if self.significant
                   else " (ضمن الصدفة)"))


def rate_of(subset: Sequence[dict], population: Sequence[dict]) -> Rate:
    """معدّل فوز شريحةٍ مقابل معدّل الأساس."""
    n = len(subset)
    w = sum(1 for t in subset if t.get("status") == "won")
    pop_n = len(population) or 1
    base = sum(1 for t in population if t.get("status") == "won") / pop_n
    if n == 0:
        return Rate(0, 0, 0.0, 0.0, base, 1.0)
    lo, hi = wilson_interval(w, n, Z95)
    p = binom_two_sided_p(w, n, base)
    return Rate(w, n, lo, hi, base, p)


# ═══════════════════ ما يميّز الصفقة عن غيرها ═══════════════════

# الخصائص المتاحة **عند الدخول** فقط. وإدخال أي حقل نتيجة هنا
# يجعل كل تفسيرٍ نبوءةً بعد وقوعها.
ENTRY_TRAITS = ("market", "timeframe", "side", "grade", "source", "action")

# والعدديّة تُقسَّم إلى شرائح: «النقاط 63.2» لا تتكرّر، و«النقاط
# عالية» تتكرّر فتُقاس.
NUMERIC_TRAITS = {
    "score": ((None, 20.0, "نقاط منخفضة"),
              (20.0, 45.0, "نقاط متوسّطة"),
              (45.0, None, "نقاط عالية")),
    "rr": ((None, 1.5, "عائد/مخاطرة دون 1.5"),
           (1.5, 2.5, "عائد/مخاطرة 1.5–2.5"),
           (2.5, None, "عائد/مخاطرة فوق 2.5")),
    "confidence": ((None, 40.0, "ثقة منخفضة"),
                   (40.0, 70.0, "ثقة متوسّطة"),
                   (70.0, None, "ثقة عالية")),
}


def _bucket(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    for lo, hi, label in NUMERIC_TRAITS.get(name, ()):
        if (lo is None or v >= lo) and (hi is None or v < hi):
            return label
    return None


def traits_of(trade: dict) -> list[str]:
    """سمات الصفقة عند دخولها — نصوصٌ قابلة للتجميع."""
    out: list[str] = []
    for k in ENTRY_TRAITS:
        v = trade.get(k)
        if v not in (None, "", "—"):
            out.append(f"{k}={v}")
    for k in NUMERIC_TRAITS:
        b = _bucket(k, trade.get(k))
        if b:
            out.append(b)
    return out


@dataclass
class Cause:
    """سببٌ مرشَّح — سمةٌ ومعدّل فوزها.

    و``members`` هويّات الصفقات التي تحملها: بها يُعرَف أنّ سمتين
    مختلفتي الاسم تصفان الصفقات نفسها فلا تُعدّان دليلين.
    """

    trait: str
    rate: Rate
    members: frozenset = frozenset()
    aliases: list = field(default_factory=list)

    def arabic(self) -> str:
        name = self.trait
        if self.aliases:
            # الأسماء المرادفة تُذكر ولا تُكرَّر سطراً: إخفاؤها
            # يضيّع أنّها شيءٌ واحد، وتكرارها يضخّم الدليل ثلاثاً.
            name += " (= " + " = ".join(self.aliases) + ")"
        return f"{name}: {self.rate.arabic()}"


def causes_for(trade: dict, population: Sequence[dict],
               *, top: int = 3) -> list[Cause]:
    """لماذا فازت هذه الصفقة أو خسرت — من سجلّك لا من الحدس.

    ═══ لماذا من السكّان لا من الصفقة ═══

    الصفقة الواحدة لا تُفسَّر بنفسها: كل خاسرة يمكن أن يُروى لها
    سببٌ بليغ بعد وقوعها. والسؤال الوحيد المفيد: **هل تتكرّر؟**

    فتُؤخذ كل سمةٍ فيها، ويُقاس معدّل فوز كل الصفقات التي تشاركها
    تلك السمة. فإن كانت «مصدر=اختراق» تفوز 3 من 19 في سجلّك كلّه،
    فذاك سببٌ يتكرّر. وإن كانت تفوز 50٪ فالسمة بريئة والسبب آخر.
    """
    out: list[Cause] = []
    for t in traits_of(trade):
        same = [x for x in population if t in traits_of(x)]
        r = rate_of(same, population)
        if r.readable:
            out.append(Cause(t, r, frozenset(_ident(x) for x in same)))
    # الأبعد عن الأساس أوّلاً — لا الأعلى فوزاً. سمةٌ تفوز 90٪
    # وأساسها 88٪ لا تفسّر شيئاً.
    out.sort(key=lambda c: -abs(c.rate.edge))
    return _dedupe(out)[:top]


# ═══ حقيقةٌ واحدة لا تُعدّ ثلاثاً ═══
#
# قِيس على سجلّ ٢٩٢ صفقة فخرجت ثلاثة «أسباب» بأرقامٍ متطابقة::
#
#     grade=—           2 من 18 = 11٪ · الفارق -35 نقطة
#     source=breakout   2 من 18 = 11٪ · الفارق -35 نقطة
#     action=breakout   2 من 18 = 11٪ · الفارق -35 نقطة
#
# وهي **الصفقات الثمانية عشر نفسها**: صفقات الاختراق لا يصنّفها
# النظام، فيبقى تقديرها «—». فاسمٌ واحد يظهر ثلاثاً.
#
# وثلاثة أسطر متطابقة تُقرأ إجماعاً — «ثلاثة أدلّة مستقلّة» — وهي
# دليلٌ واحد. فيُبقى الأوّل، ويُذكر ما رافقه كي لا يضيع أنّ
# «اختراق» و«بلا تقدير» شيءٌ واحد في سجلّك.
def _ident(trade: dict) -> Any:
    """هويّة الصفقة — بالمعرّف إن وُجد، وإلّا برمزها ونتيجتها."""
    tid = trade.get("id")
    if tid is not None:
        return ("id", tid)
    return ("k", trade.get("symbol"), trade.get("status"),
            trade.get("r_multiple"))


def _dedupe(causes: list["Cause"]) -> list["Cause"]:
    kept: list[Cause] = []
    for c in causes:
        twin = next((k for k in kept if k.members == c.members), None)
        if twin is None:
            kept.append(c)
        else:
            twin.aliases.append(c.trait)
    return kept


# ═════════════════════ حزمة الأدلّة للنموذج ═════════════════════

@dataclass
class EvidencePack:
    """كل ما يُسمح للنموذج أن يبني عليه — ولا شيء غيره."""

    kind: str                     # "settled" | "prospective"
    symbol: str
    facts: list[str] = field(default_factory=list)
    rate: Rate | None = None
    causes: list[Cause] = field(default_factory=list)
    levels: dict[str, float] = field(default_factory=dict)
    note: str = ""
    # «لماذا قد تنجح» — أسباب الإشارة مقيسةً على السجلّ
    why: Any = None

    def as_prompt_block(self) -> str:
        """الأدلّة نصّاً — مرقّمة ليُشار إليها بالرقم."""
        lines: list[str] = []
        for i, f in enumerate(self.facts, 1):
            lines.append(f"[{i}] {f}")
        if self.rate is not None:
            lines.append(f"[معدّل] {self.rate.arabic()}")
        for c in self.causes:
            lines.append(f"[سبب] {c.arabic()}")
        if self.why is not None:
            lines.extend(self.why.as_lines())
        if self.levels:
            nums = " · ".join(f"{k}={v:g}" for k, v in self.levels.items())
            lines.append(f"[مستويات] {nums}")
        if self.note:
            lines.append(f"[تنبيه] {self.note}")
        return "\n".join(lines)

    @property
    def numbers(self) -> list[float]:
        """كل رقمٍ مسموحٍ ذكره — يُتحقّق به من مخرَج النموذج.

        ═══ ولماذا يشمل المشتقّات ═══

        النسخة الأولى سردت الفوز والمجموع والنسبة فقط، فرفضت
        مخرَجاً **صحيحاً** كتب «27 نقطة فوق الأساس» — والفارق
        رقمٌ معروضٌ في الأدلّة نفسها.

        وفاحصٌ يرفض الصواب أسوأ من فاحصٍ متساهل: الأوّل يُدرَّب
        المستخدم على تجاهله، والثاني يُصلَح. فكل رقمٍ **يُعرَض**
        في كتلة الأدلّة يجب أن يكون مسموحاً بذكره.
        """
        out = list(self.levels.values())

        def _from(r) -> list[float]:
            if not r.readable:
                return []
            # ═══ ولماذا لا يشمل حدَّي فاصل الثقة ═══
            #
            # أضفتُهما أوّلاً فمرّ مخرَجٌ يقول «احتمال النجاح 88٪»
            # — و88 هو الحدّ **الأعلى** للفاصل [49–88]، لا
            # الاحتمال. فسماحُهما يتيح للنموذج اقتطاف الطرف
            # المتفائل وعرضه نقطةً.
            #
            # الفاصل يُعرَض للقارئ في كتلة الأدلّة ليرى السعة،
            # ولا يُقتطف رقماً مفرداً. ومن أراد التعبير عن عدم
            # اليقين فليقل «13 من 18».
            # ═══ الصورة المعروضة تُسمَح، لا القيمة الخام ═══
            #
            # ``arabic()`` يطبع ``{pct:.0f}`` — فالنسبة 63.9 تُعرض
            # «64٪». وقائمةٌ تحوي 63.9 وحدها ترفض نموذجاً كتب
            # «64٪» نقلاً عن السطر المعروض أمامه حرفياً.
            #
            # وهذا هو العطب نفسه للمرّة الثالثة: مرّة في «27
            # نقطة»، ومرّة هنا. فتُضاف صورتا التقريب — الخام
            # للحساب، والمعروضة للنقل.
            return [float(r.wins), float(r.total),
                    round(r.pct, 1), float(round(r.pct)),
                    round(r.edge, 1), float(round(r.edge)),
                    abs(round(r.edge, 1)), float(abs(round(r.edge))),
                    round(r.baseline * 100)]

        if self.rate is not None:
            out += _from(self.rate)
        for c in self.causes:
            out += _from(c.rate)
        if self.why is not None:
            out += list(self.why.numbers)
            out.append(float(self.why.tested))

        # ═══ وكل رقمٍ يراه النموذج ═══
        #
        # عدّدتُ المصادر يدوياً ثلاث مرّات فتسرّب في كل مرّة رقمٌ
        # معروضٌ وغير مسموح: «27 نقطة»، ثمّ «64٪» (صورة 63.9
        # المطبوعة)، ثمّ «1.5–2.5» و«اختراق قمة 20 شمعة» — حدودُ
        # الشرائح ونصوصُ الأسباب.
        #
        # وقائمةٌ تُعدَّد يدوياً ستتخلّف عن العرض دائماً. فتُشتقّ
        # من **الكتلة المعروضة نفسها**: ما يراه النموذج هو ما
        # يُسمح له بنقله، لا أكثر.
        out += self._shown_numbers()
        return out

    def _shown_numbers(self) -> list[float]:
        """أرقام كتلة الأدلّة — عدا حدَّي فاصل الثقة.

        ``[49–88]`` يُقنَّع قبل الاستخراج: الفاصل يُعرَض للقارئ
        ليرى السعة، ولا يُقتطف طرفُه المتفائل ويُعرَض احتمالاً.
        وهذا الاستثناء الوحيد، ولذلك يُقنَّع صراحةً لا يُنسى.
        """
        text = self.as_prompt_block()
        text = _CI.sub(" ", text)          # حدّا الفاصل
        text = _INDEX.sub(" ", text)       # ترقيم الأسطر [1] [2]
        out: list[float] = []
        for tok in _NUM.findall(text):
            try:
                v = float(tok)
            except ValueError:
                continue
            out += [v, float(round(v))]
        return out



def _why(item: dict, population: Sequence[dict]):
    """تفسير أسباب الإشارة — أو ``None`` إن لم تُسجَّل أسباب.

    الاستيراد مؤجَّل: ``why`` يستورد ``evidence``، واستيرادٌ
    علويّ متبادل يكسر تحميل الحزمة.
    """
    if not (item.get("reasons") or "").strip():
        return None
    from .why import explain

    return explain(item, population)


def for_settled(trade: dict, population: Sequence[dict]) -> EvidencePack:
    """حزمة تشريح صفقة محسومة — «لماذا فازت / لماذا خسرت»."""
    status = trade.get("status")
    r = trade.get("r_multiple")
    facts = [
        f"النتيجة: {'ربح' if status == 'won' else 'خسارة'}"
        + (f" · {float(r):+.2f}R" if r is not None else ""),
        f"الرمز {trade.get('symbol')} · {trade.get('market')} · "
        f"{trade.get('timeframe')}",
    ]
    for k, label in (("score", "النقاط"), ("rr", "عائد/مخاطرة"),
                     ("grade", "التقدير"), ("source", "المصدر")):
        v = trade.get(k)
        if v not in (None, "", "—"):
            facts.append(f"عند الدخول — {label}: {v}")

    levels = {}
    for k, label in (("entry_price", "الدخول"), ("stop", "الوقف"),
                     ("target1", "الهدف")):
        try:
            levels[label] = float(trade[k])
        except (KeyError, TypeError, ValueError):
            pass

    causes = causes_for(trade, population)
    note = ""
    if not causes:
        note = ("لا سمة في هذه الصفقة بلغت عيّنةً كافية — "
                "فلا سبب متكرّر يُنسب إليه.")
    return EvidencePack(kind="settled", symbol=str(trade.get("symbol") or ""),
                        facts=facts, causes=causes, levels=levels, note=note,
                        why=_why(trade, population))


def for_prospective(setup: dict, population: Sequence[dict]) -> EvidencePack:
    """حزمة «هل أدخل؟» — الاحتمال من سجلّك لا من النموذج.

    ═══ من أين يأتي الاحتمال ═══

    من الصفقات التي تشارك هذا الإعداد **كل** سماته. فإن قلّت عن
    ``MIN_SAMPLE`` تُخفَّف الشروط سمةً سمةً حتى تكفي العيّنة، ويُذكر
    ما أُسقط — كي يعرف القارئ أنّ الرقم عن شريحةٍ أوسع.

    وإن لم تكفِ بحال، فلا احتمال. والصمت هنا موقفٌ لا عجز.
    """
    want = traits_of(setup)
    used = list(want)
    same: list[dict] = []
    dropped: list[str] = []

    while used:
        same = [t for t in population if all(w in traits_of(t) for w in used)]
        if len(same) >= MIN_SAMPLE:
            break
        dropped.append(used.pop())      # أضعف السمات آخراً في القائمة

    r = rate_of(same, population) if same else rate_of([], population)

    facts = [f"الرمز {setup.get('symbol')} · {setup.get('market')} · "
             f"{setup.get('timeframe')}"]
    for k, label in (("score", "النقاط"), ("rr", "عائد/مخاطرة"),
                     ("grade", "التقدير"), ("action", "التوصية"),
                     ("confluence", "الالتقاء")):
        v = setup.get(k)
        if v not in (None, "", "—"):
            facts.append(f"{label}: {v}")

    levels = {}
    for k, label in (("entry", "الدخول"), ("stop", "الوقف"),
                     ("target1", "الهدف"), ("close", "السعر الآن")):
        try:
            levels[label] = float(setup[k])
        except (KeyError, TypeError, ValueError):
            pass

    note = ""
    if dropped:
        note = ("العيّنة الدقيقة لم تكفِ، فوُسّعت بإسقاط: "
                + " · ".join(dropped))
    if not r.readable:
        note = (note + " " if note else "") + (
            "لا سابقة كافية في سجلّك لهذا الإعداد — "
            "فلا نسبة نجاح تُذكَر.")
    return EvidencePack(kind="prospective",
                        symbol=str(setup.get("symbol") or ""),
                        facts=facts, rate=r, levels=levels, note=note,
                        why=_why(setup, population))


__all__ = ["Rate", "Cause", "EvidencePack", "rate_of", "causes_for",
           "traits_of", "for_settled", "for_prospective",
           "MIN_SAMPLE", "MIN_EDGE_PCT"]
