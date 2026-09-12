# -*- coding: utf-8 -*-
"""لماذا قد تنجح هذه الصفقة — بسجلّك لا بالبلاغة.

═══ السؤال ═══

الماسح يعطي كل إشارة أسبابها نصّاً::

    خصم · قاع القناة · الدرجة 35 · هيكل صاعد: قمم وقيعان أعلى ·
    آخر حدث هيكلي: BOS ⇧ · الدخول عند فيبوناتشي

وهذه أسبابٌ **مزعومة**: قالها النظام وقت الرصد ولم يسأل أحدٌ هل
تصدق. والسطر يقرأه المتداول فيراه ستّة مؤيّدات، فيدخل.

═══ الجواب ═══

كل سببٍ من هذه سُجِّل على ٢٩٥ صفقة محسومة في سجلّك. فيُقاس: كم
مرّة ظهر، وكم مرّة فازت الصفقة التي حملته. وهذا وحده يفصل السبب
الذي يستحقّ الثقة عن الزينة.

وهذا ما خرج من القياس الفعلي (أساس الفوز ٤٦.٤٪)::

    فيبو 0.382              11/15  = 73٪   الفارق +26.9  p=0.041
    نموذج: قاع مزدوج        23/36  = 64٪   الفارق +17.4  p=0.044
    الدخول عند فجوة صاعدة   47/81  = 58٪   الفارق +11.6  p=0.044
    ...
    قاع القناة              28/83  = 34٪   الفارق -12.7  p=0.021
    اختراق قمة 20 شمعة       3/19  = 16٪   الفارق -30.7  p=0.010

═══ ولماذا لا تُعرَض هذه كما هي ═══

سِتّةٌ منها «ذات دلالة» بحساب p منفرداً. لكنّي اختبرتُ **٢١
فرضية** — وباختبار واحدٍ وعشرين فرضية عند ٥٪ يُتوقَّع نجاح واحدة
بالصدفة وحدها.

وبضبط بنياميني-هوخبرغ على الواحد والعشرين: **لم تنجُ ولا واحدة**.
أصغر p هو 0.009 وعتبة الرتبة الأولى 0.0024.

فالعرض هنا يفصل ثلاث درجات صراحةً:

    أثبتت      ← نجت ضبط التعدّد
    مبشّرة     ← دلالة منفردة تسقط بالضبط
    محايدة     ← عيّنة كافية ولا فرق
    لم تُختبر  ← عيّنة أصغر من حدّ النطق
    ضدّك       ← فارقٌ سالب

ومن أراد أن يرقّي «مبشّرة» إلى «أثبتت» فالطريق معروف: فارقُ ٢٠
نقطة يحتاج ١٨٤ صفقة تحمل السبب، وفارقُ ١٥ نقطة يحتاج ٣٣١. ولا
مختصر.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .evidence import MIN_SAMPLE, Rate, rate_of

# الفاصل الذي يستعمله الماسح بين الأسباب
SEP = "·"

# «الدرجة 35» و«الدرجة 41» سببٌ واحد بقيمتين. وتركُهما منفصلين
# يفتّت العيّنة إلى عشرات المجموعات كلٌّ منها دون حدّ النطق —
# فلا يُقاس شيء أبداً.
_NUMBERED = ("الدرجة ",)

STRENGTH = ("أثبتت", "مبشّرة", "محايدة", "لم تُختبر", "ضدّك")


def count_ar(n: int, noun: str) -> str:
    """عدّ عربيّ سليم — «سببان» لا «2 سبب».

    ليست زينة: النصّ يُقرأ على أنّه من النظام، ونصٌّ ركيك يُقرأ
    على أنّه ترجمة آلية فيُوزَن كذلك.
    """
    forms = {"سبب": ("سبب واحد", "سببان", "أسباب", "سبباً")}
    one, two, few, many = forms.get(noun, (noun, noun, noun, noun))
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


def _adj(n: int, singular: str, dual: str, plural: str) -> str:
    """صفةٌ تطابق معدودها.

    العربية تُثنّي وتجمع جمع تكسيرٍ يُعامَل معاملة المؤنّث المفرد:
    «سببان مبشّران» · «ثلاثة أسباب مبشّرة» · «أحد عشر سبباً مبشّر».
    """
    if n == 2:
        return dual
    if 3 <= n <= 10:
        return plural
    return singular


def split_reasons(raw: str | None) -> list[str]:
    """أسباب الإشارة نصّاً → قائمةً موحَّدة."""
    out: list[str] = []
    for p in (raw or "").split(SEP):
        p = p.strip()
        if not p:
            continue
        for pre in _NUMBERED:
            if p.startswith(pre):
                p = pre.strip() + " N"
                break
        if p not in out:
            out.append(p)
    return out


def reasons_of(trade: dict) -> list[str]:
    return split_reasons(trade.get("reasons"))


@dataclass
class Reason:
    """سببٌ مزعوم ومعدّله الحقيقي في السجلّ."""

    text: str
    rate: Rate | None = None
    strength: str = "لم تُختبر"
    survives_fdr: bool = False

    @property
    def supports(self) -> bool:
        """هل هو في صفّك؟"""
        return self.strength in ("أثبتت", "مبشّرة")

    @property
    def against(self) -> bool:
        return self.strength == "ضدّك"

    def arabic(self) -> str:
        if self.rate is None or not self.rate.readable:
            n = 0 if self.rate is None else self.rate.total
            return f"{self.text} — لم تُختبر بعد ({n} صفقة في سجلّك)"
        return f"{self.text} — {self.strength}: {self.rate.arabic()}"


def benjamini_hochberg(pvalues: Sequence[float], alpha: float = 0.05) -> list[bool]:
    """أيّ الفرضيات تنجو بعد ضبط معدّل الاكتشاف الكاذب.

    إجراء صعودي: يُبحث عن أكبر رتبة ``k`` تحقّق ``p(k) ≤ αk/m``،
    فتُقبل هي وكل ما دونها. ونسخةٌ تفحص كل فرضية على حدة تقبل
    فرضيةً بـ p=0.041 وقد اختُبرت إحدى وعشرون — وهو بالضبط ما
    يُتوقَّع بالصدفة.
    """
    m = len(pvalues)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    cutoff = -1
    for rank, idx in enumerate(order, 1):
        if pvalues[idx] <= alpha * rank / m:
            cutoff = rank
    out = [False] * m
    for rank, idx in enumerate(order, 1):
        if rank <= cutoff:
            out[idx] = True
    return out


@dataclass
class WhyPack:
    """تفسير «لماذا قد تنجح» — مفصولاً بدرجة الإسناد."""

    reasons: list[Reason] = field(default_factory=list)
    tested: int = 0
    survived: int = 0

    @property
    def supporting(self) -> list[Reason]:
        return [r for r in self.reasons if r.supports]

    @property
    def opposing(self) -> list[Reason]:
        return [r for r in self.reasons if r.against]

    @property
    def untested(self) -> list[Reason]:
        return [r for r in self.reasons if r.strength == "لم تُختبر"]

    def headline(self) -> str:
        """سطرٌ واحد يلخّص الإسناد — أو غيابه.

        والمضادّ يُذكر في العنوان دائماً إن وُجد: عنوانٌ يقول
        «سببان مبشّران» وتحته سببٌ يخسر ٣١ نقطة تحت الأساس هو
        تضليلٌ بالاختيار لا بالكذب.
        """
        proven = [r for r in self.reasons if r.strength == "أثبتت"]
        promising = [r for r in self.reasons if r.strength == "مبشّرة"]

        if proven:
            k = len(proven)
            verb = _adj(k, "أثبت نفسه", "أثبتا نفسيهما", "أثبتت نفسها")
            good = f"{count_ar(k, 'سبب')} {verb} في سجلّك"
        elif promising:
            k = len(promising)
            good = (f"{count_ar(k, 'سبب')} "
                    f"{_adj(k, 'مبشّر', 'مبشّران', 'مبشّرة')} — "
                    f"{_adj(k, 'لم ينجُ', 'لم ينجوَا', 'لم تنجُ')} "
                    f"ضبط التعدّد ({self.tested} فرضية مختبَرة)")
        else:
            good = ""

        bad = ""
        if self.opposing:
            k = len(self.opposing)
            bad = (f"{count_ar(k, 'سبب')} "
                   f"{_adj(k, 'يخسر', 'يخسران', 'تخسر')} أكثر "
                   "من المتوسّط في سجلّك")

        if good and bad:
            return f"{good} · وفي المقابل {bad}"
        if good:
            return good
        if bad:
            return bad
        return "لا سبب من أسباب هذه الإشارة أثبت نفسه في سجلّك بعد"

    def as_lines(self) -> list[str]:
        """للنموذج: المؤيّد أوّلاً ثمّ المضادّ، والمجهول يُذكر عدداً.

        والمضادّ **يُذكر دائماً**: تفسيرٌ يسرد المؤيّدات وحدها هو
        الذي جعل المستشار القديم لا يقول «لا تدخل» ولا مرّة.
        """
        lines = [f"[لماذا] {self.headline()}"]
        for r in self.supporting:
            lines.append(f"[مؤيّد] {r.arabic()}")
        for r in self.opposing:
            lines.append(f"[مضادّ] {r.arabic()}")
        n = len(self.untested)
        if n:
            lines.append(f"[مجهول] {count_ar(n, 'سبب')} بلا عيّنة كافية "
                         "للحكم")
        return lines

    @property
    def numbers(self) -> list[float]:
        """أرقام المؤيّدات والمضادّات — مسموحٌ للنموذج ذكرها."""
        out: list[float] = []
        for r in self.reasons:
            if r.rate is not None and r.rate.readable:
                # الخام والمعروض معاً — انظر ``evidence._from``
                out += [float(r.rate.wins), float(r.rate.total),
                        round(r.rate.pct, 1), float(round(r.rate.pct)),
                        round(r.rate.edge, 1), float(round(r.rate.edge)),
                        abs(round(r.rate.edge, 1)),
                        float(abs(round(r.rate.edge))),
                        round(r.rate.baseline * 100)]
        return out


def explain(setup: dict, population: Sequence[dict], *,
            alpha: float = 0.05) -> WhyPack:
    """يقيس كل سببٍ زعمه الماسح على سجلّ الصفقات المحسومة.

    ═══ الضبط على كل ما اختُبر لا على المعروض ═══

    الفرضيات المضبوطة هي **كل سببٍ في السجلّ له عيّنة كافية**، لا
    أسباب هذه الإشارة وحدها. فلو ضُبط على ستّةٍ ظهرت هنا لنجا
    بعضها — وهو ضبطٌ صوريّ: البحث جرى على الواحد والعشرين كلّها،
    وأنّ هذه الإشارة تحمل ستّةً منها لا يُلغي البحث.
    """
    pop = list(population)
    mine = split_reasons(setup.get("reasons"))

    # كل سببٍ قابلٍ للقياس في السجلّ — هو فضاء البحث الحقيقي
    universe: list[str] = []
    for t in pop:
        for r in reasons_of(t):
            if r not in universe:
                universe.append(r)

    rates: dict[str, Rate] = {}
    for name in universe:
        sub = [t for t in pop if name in reasons_of(t)]
        rates[name] = rate_of(sub, pop)

    tested = [n for n in universe if rates[n].readable]
    keep = benjamini_hochberg([rates[n].p_value for n in tested], alpha)
    survived = {n for n, k in zip(tested, keep) if k}

    out: list[Reason] = []
    for name in mine:
        r = rates.get(name)
        if r is None or not r.readable:
            # سببٌ لم يظهر في السجلّ قطّ، أو ظهر دون حدّ النطق
            n = 0 if r is None else r.total
            out.append(Reason(name, r, "لم تُختبر", False))
            continue
        if r.edge < 0 and r.significant:
            strength = "ضدّك"
        elif name in survived:
            strength = "أثبتت"
        elif r.significant and r.edge > 0:
            strength = "مبشّرة"
        else:
            strength = "محايدة"
        out.append(Reason(name, r, strength, name in survived))

    # الأقوى إسناداً أوّلاً، ثمّ الأبعد عن الأساس
    rank = {s: i for i, s in enumerate(STRENGTH)}
    out.sort(key=lambda x: (rank.get(x.strength, 9),
                            -abs(x.rate.edge) if x.rate else 0.0))
    return WhyPack(out, len(tested), len(survived))


__all__ = ["count_ar", "Reason", "WhyPack", "explain", "split_reasons", "reasons_of",
           "benjamini_hochberg", "STRENGTH", "MIN_SAMPLE"]
