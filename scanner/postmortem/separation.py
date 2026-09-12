# -*- coding: utf-8 -*-
"""ما يفصل الصفقة الرابحة عن الخاسرة — قياساً لا سرداً.

═══ الفخّ الذي تتجنّبه هذه الوحدة ═══

أن تُعطي نموذجاً لغويّاً صفقةً خاسرة وتسأله «لماذا خسرت» هو أضمن طريق
إلى جواب **مقنع وخاطئ**. النموذج يعرف النتيجة، وسيجد لها سبباً دائماً؛
هذا ما تفعله النماذج اللغوية بطبيعتها. وستقرأ تفسيراً بليغاً لنمطٍ لا
وجود له، ثمّ تبني عليه قراراً.

فالترتيب هنا معكوس عن البديهي:

    ١. المنصّة **تقيس** الفروق بين المجموعتين
    ٢. تحكم أيّ فرق يتجاوز الضجيج
    ٣. والنموذج يفسّر ما ثبت فقط — ويُمنع من إسناد سبب لما لم يثبت

═══ التمييز الحاسم: ما يُعرَف قبل الدخول ═══

قياسٌ على هذه الصفقات يعطي:

    best_r    ناجحة 2.35 · خاسرة 0.88 · حجم أثر 1.83
    worst_r   ناجحة −0.35 · خاسرة −1.33 · حجم أثر 1.12

وهذا **دائري لا مفيد**: الصفقة الرابحة رابحة *لأنها* بلغت ‏R عالياً.
والاستدلال به كمن يقول «الفائزون فازوا لأنهم سجّلوا نقاطاً أكثر».

والحقول التي كانت معلومة **لحظة الدخول** لا تكاد تفصل:

    الدرجة        حجم أثر 0.19
    الثقة         حجم أثر 0.17
    عائد/مخاطرة   حجم أثر −0.01

وهذه حقيقة ثقيلة لكنها الحقيقة: درجة المنصّة نفسها لا تميّز الرابح من
الخاسر عند الدخول. وإخفاؤها خلف سرد جميل أسوأ من قولها.

═══ المقارنات المتعدّدة ═══

فحص اثني عشر وسماً عند ثقة 95٪ يعني أن نصف اكتشاف واحد متوقَّع
**بالصدفة وحدها**. فتُصحَّح العتبة بعدد الفحوص (بونفيروني)، ويُعلَن
عدد ما فُحص — وإلّا صار كل تقرير يجد «أنماطاً».
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "FactorSeparation", "TagSeparation", "PostmortemReport",
    "analyze", "wilson_interval", "OUTCOME_FIELDS", "ENTRY_FIELDS",
]

# ── حقول النتيجة: تُوصَف ولا تُفسَّر ──────────────────────────────────
#
# لا يجوز أن تظهر أيٌّ منها كـ«سبب». الفرق فيها بين المجموعتين مضمون
# بالتعريف، فقياسه لا يضيف معرفة.
OUTCOME_FIELDS = frozenset({
    "r_multiple", "best_r", "worst_r", "exit_price", "closed_at",
    "bars_held", "resolution_note", "status", "last_price", "checked_at",
})

# ── حقول معلومة لحظة الدخول: هذه وحدها قابلة لأن تكون سبباً ──────────
ENTRY_FIELDS = ("score", "confidence", "rr", "grade", "entry", "stop",
                "target1", "side", "timeframe", "market", "source", "action")

MIN_GROUP = 15          # أقلّ عدد في كل مجموعة قبل مقارنة رقمية
# أقلّ ظهور للوسم قبل الحكم عليه.
#
# كانت 20، فأخفت اكتشافاً حقيقياً: ستّ عشرة صفقة اختراق **خسرت
# كلّها** (‏p=0.00015، تصمد لبونفيروني). ووظيفة العتبة تقليل عدد
# الفحوص لا حجب الأطراف — والاختبار ذو الحدّين الدقيق يتعامل مع
# العيّنات الصغيرة تعاملاً صحيحاً، فلا حاجة لحمايته منها.
MIN_TAG_COUNT = 12
Z95 = 1.959963985


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """فاصل ويلسون — أصدق من الفاصل العادي على العيّنات الصغيرة.

    ثلاث نجاحات من أربع ليست «75٪»؛ فاصلها [0.30, 0.95]. والفاصل
    العادي يعطي حدوداً خارج [0,1] ويوهم بدقّة غير موجودة.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def binom_two_sided_p(k: int, n: int, p0: float) -> float:
    """‏p الدقيقة لاختبار ذي الحدّين ثنائي الطرف — بلا scipy.

    الطريقة: مجموع احتمالات كل النتائج التي احتمالها ≤ احتمال المرصود.
    وهي الصيغة الدقيقة، لا تقريب طبيعي — والعيّنات هنا عشرات لا آلاف،
    والتقريب الطبيعي يخطئ عند الأطراف حيث تقع الاكتشافات المهمّة.
    """
    if n <= 0 or not (0.0 < p0 < 1.0):
        return 1.0
    from math import comb

    def pmf(i: int) -> float:
        return comb(n, i) * (p0 ** i) * ((1 - p0) ** (n - i))

    observed = pmf(k)
    # هامش عائم صغير: نتيجتان متساويتا الاحتمال رياضياً قد تختلفان
    # في البتّ الأخير، فتُستبعد إحداهما ظلماً
    tol = observed * 1e-9
    total = sum(pmf(i) for i in range(n + 1) if pmf(i) <= observed + tol)
    return min(1.0, total)


def benjamini_hochberg(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """أيّ الفحوص ينجو بضبط معدّل الاكتشاف الكاذب.

    ═══ لماذا لا بونفيروني ═══

    بونفيروني يضبط احتمال **أي** إيجابية كاذبة، وهو المناسب حين تكلفة
    الخطأ الواحد فادحة. وقياسٌ على هذه الصفقات بعشرين فحصاً يجعل العتبة
    0.0025، فتُمحى فروق حقيقية — منها وسم نسبته 27٪ مقابل أساس 43٪ على
    أربع وسبعين صفقة.

    وهذا **فرز استكشافي**: غرضه توليد فرضيات تُختبر لاحقاً على بيانات
    جديدة، لا إصدار أحكام نهائية. والمناسب له ضبط نسبة الكاذب بين
    المكتشَف (‏FDR): يسمح ببعض الكاذب مقابل ألّا يضيع الصادق.

    والنتيجة تبقى فرضية لا حقيقة — ولهذا يُعرَض معها مستوى صمودها.
    """
    n = len(pvalues)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvalues[i])
    keep = [False] * n
    largest = -1
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= alpha * rank / n:
            largest = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= largest:
            keep[idx] = True
    return keep


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pstdev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """حجم الأثر — الفرق مقيساً بالتشتّت، لا بالوحدات.

    الفرق بالوحدات لا يُقارَن بين حقلين مختلفَي المقياس؛ وحجم الأثر
    يُقارَن. والعرف: 0.2 صغير · 0.5 متوسّط · 0.8 كبير.
    """
    sa, sb = _pstdev(a), _pstdev(b)
    pooled = math.sqrt((sa * sa + sb * sb) / 2) or 1e-9
    return (_mean(a) - _mean(b)) / pooled


@dataclass
class FactorSeparation:
    """فرق رقمي في حقل معلوم قبل الدخول."""

    field_name: str
    n_won: int
    n_lost: int
    mean_won: float
    mean_lost: float
    effect_size: float
    significant: bool
    note: str = ""

    @property
    def direction(self) -> str:
        return "أعلى في الرابحة" if self.effect_size > 0 else "أعلى في الخاسرة"

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field_name, "n_won": self.n_won,
            "n_lost": self.n_lost, "mean_won": round(self.mean_won, 4),
            "mean_lost": round(self.mean_lost, 4),
            "effect_size": round(self.effect_size, 3),
            "significant": self.significant, "note": self.note,
        }


@dataclass
class TagSeparation:
    """نسبة نجاح وسم نصّي مقارنةً بالأساس."""

    tag: str
    n: int
    wins: int
    win_rate: float
    ci_low: float
    ci_high: float
    baseline: float
    significant: bool
    direction: str          # "أفضل" | "أسوأ" | "لا فرق"
    p_value: float = 1.0
    # وسوم تظهر على **نفس** الصفقات بالضبط. أربعة أسماء لحقيقة واحدة.
    cluster: tuple = ()
    # درجة الصمود: كم يصمد هذا الفرق أمام تشدّد التصحيح.
    #   "قوي"      نجا حتى من بونفيروني — فرق يُعتمد عليه
    #   "مرجَّح"   نجا من ضبط معدّل الاكتشاف الكاذب — فرضية تستحقّ اختباراً
    #   "ضعيف"     ظهر عند 5٪ خام فقط — الأرجح أنه صدفة بين عشرين فحصاً
    strength: str = "لا شيء"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag, "n": self.n, "wins": self.wins,
            "win_rate": round(self.win_rate, 4),
            "ci": [round(self.ci_low, 3), round(self.ci_high, 3)],
            "baseline": round(self.baseline, 4),
            "significant": self.significant, "direction": self.direction,
            "p_value": round(self.p_value, 5), "strength": self.strength,
            "cluster": list(self.cluster),
        }


@dataclass
class PostmortemReport:
    n_total: int = 0
    n_won: int = 0
    n_lost: int = 0
    baseline_win_rate: float = 0.0
    expectancy_r: float = 0.0
    factors: list[FactorSeparation] = field(default_factory=list)
    tags: list[TagSeparation] = field(default_factory=list)
    outcome_description: dict[str, Any] = field(default_factory=dict)
    tests_run: int = 0
    corrected_alpha: float = 0.05
    # الاختبار الشامل: هل مجموعة الفحوص كلّها ضجيج؟
    global_p: float = 1.0
    global_signal: bool = False
    # كل وسم بعدده ونجاحه، بلا عتبة. للبطاقة المفردة: وسمٌ ظهر ثماني
    # مرّات بنسبة 25٪ معلومة أنفع من «مجهول الأثر»، ما دام موسوماً
    # بأن عيّنته لا تكفي للحكم.
    all_tag_counts: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return any(f.significant for f in self.factors) or any(
            t.significant for t in self.tags)

    def significant_tags(self) -> list[TagSeparation]:
        return [t for t in self.tags if t.significant]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_total": self.n_total, "n_won": self.n_won, "n_lost": self.n_lost,
            "baseline_win_rate": round(self.baseline_win_rate, 4),
            "expectancy_r": round(self.expectancy_r, 4),
            "factors": [f.to_dict() for f in self.factors],
            "tags": [t.to_dict() for t in self.tags],
            "outcome_description": self.outcome_description,
            "tests_run": self.tests_run,
            "corrected_alpha": round(self.corrected_alpha, 5),
            "global_p": round(self.global_p, 5),
            "global_signal": self.global_signal,
            "has_findings": self.has_findings,
            "warnings": list(self.warnings),
        }


# ── استخراج الوسوم ──────────────────────────────────────────────────
#
# نصّ الأسباب مثل: «حجم ×11 من المعتاد · اختراق قمة 20 شمعة».
# فالوسم هو الجزء الوصفي بلا الأرقام: «حجم من المعتاد» و«اختراق قمة
# شمعة». والأرقام تُجرَّد لأنها تجعل كل صفقة وسماً فريداً، فلا تتجمّع
# عيّنة يُحكَم عليها.
_NUM = re.compile(r"[\d٠-٩][\d٠-٩.,%×]*")


def extract_tags(text: Any) -> list[str]:
    # ‏``factors`` يُخزَّن أحياناً JSON (``["breakout"]``). تركه نصّاً
    # يجعل الأقواس والاقتباسات جزءاً من الوسم، فلا يتجمّع مع نظيره.
    if isinstance(text, str) and text.strip().startswith(("[", "{")):
        import json as _json

        try:
            parsed = _json.loads(text)
            if isinstance(parsed, list):
                text = " · ".join(str(x) for x in parsed)
            elif isinstance(parsed, dict):
                text = " · ".join(str(k) for k in parsed)
        except Exception:  # noqa: BLE001
            pass
    elif isinstance(text, (list, tuple)):
        text = " · ".join(str(x) for x in text)

    out: list[str] = []
    for part in re.split(r"\s*[·،|]\s*", str(text or "")):
        tag = _NUM.sub(" ", part)
        tag = re.sub(r"[×%]+", " ", tag)
        tag = " ".join(tag.split()).strip(" :-—")
        if len(tag) >= 4:
            out.append(tag)
    return out


def _numeric(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None      # NaN يُرفض


def analyze(trades: Iterable[dict], *,
            entry_fields: Sequence[str] = ENTRY_FIELDS,
            min_group: int = MIN_GROUP,
            min_tag: int = MIN_TAG_COUNT,
            alpha: float = 0.05) -> PostmortemReport:
    """يقيس ما يفصل الرابح عن الخاسر بين الصفقات المحسومة.

    Parameters
    ----------
    trades:
        قواميس فيها ``status`` إمّا ``won`` أو ``lost``.
    """
    rows = [t for t in trades if str(t.get("status")) in ("won", "lost")]
    rep = PostmortemReport(n_total=len(rows))
    if not rows:
        rep.warnings.append("لا صفقات محسومة — لا شيء يُقاس.")
        return rep

    won = [t for t in rows if t["status"] == "won"]
    lost = [t for t in rows if t["status"] == "lost"]
    rep.n_won, rep.n_lost = len(won), len(lost)
    rep.baseline_win_rate = rep.n_won / rep.n_total

    rs = [_numeric(t.get("r_multiple")) for t in rows]
    rs = [r for r in rs if r is not None]
    rep.expectancy_r = _mean(rs)

    # ── وصف النتيجة: يُعرض ولا يُفسَّر ──
    #
    # الفرق هنا مضمون بالتعريف. يُعرض لأنه يصف **كيف** ربحت وخسرت
    # (هل الخاسرة تُضرب فوراً أم تتأرجح؟) لا **لماذا**.
    for name in ("best_r", "worst_r", "bars_held"):
        w = [v for v in (_numeric(t.get(name)) for t in won) if v is not None]
        l = [v for v in (_numeric(t.get(name)) for t in lost) if v is not None]
        if w and l:
            rep.outcome_description[name] = {
                "won": round(_mean(w), 3), "lost": round(_mean(l), 3),
                "kind": "نتيجة — وصف لا سبب",
            }

    # ── الفروق الرقمية فيما يُعرَف قبل الدخول ──
    numeric_tests: list[FactorSeparation] = []
    for name in entry_fields:
        if name in OUTCOME_FIELDS:
            # حارس صريح: حقل نتيجة لا يُقاس كسبب مهما مرّ في القائمة
            continue
        w = [v for v in (_numeric(t.get(name)) for t in won) if v is not None]
        l = [v for v in (_numeric(t.get(name)) for t in lost) if v is not None]
        if len(w) < min_group or len(l) < min_group:
            continue
        numeric_tests.append(FactorSeparation(
            field_name=name, n_won=len(w), n_lost=len(l),
            mean_won=_mean(w), mean_lost=_mean(l),
            effect_size=_cohens_d(w, l), significant=False,
        ))

    # ── الوسوم النصّية ──
    counts: dict[str, list[int]] = {}
    members: dict[str, set[int]] = {}
    for idx, t in enumerate(rows):
        seen = set()
        for src in ("reasons", "factors"):
            for tag in extract_tags(t.get(src)):
                if tag in seen:
                    continue
                seen.add(tag)
                slot = counts.setdefault(tag, [0, 0])
                slot[0] += 1
                slot[1] += int(t["status"] == "won")
                members.setdefault(tag, set()).add(idx)

    # ── العناقيد: وسوم على نفس الصفقات بالضبط ──
    #
    # صفقات الاختراق تحمل «حجم من المعتاد» و«اختراق قمة شمعة» و«جسم من
    # المدى» و«breakout» معاً دائماً. فهي أربعة أسماء لحقيقة واحدة.
    #
    # وعدّها أربعة اكتشافات يضخّم عدد الفحوص فيقسو التصحيح بلا سبب، ثمّ
    # يقرأ المستخدم «أربعة عوامل» وهو عامل واحد — وهذا خطأ من صنف
    # المقارنات المتعدّدة نفسه.
    clusters: dict[frozenset, list[str]] = {}
    for tag, mem in members.items():
        clusters.setdefault(frozenset(mem), []).append(tag)
    tag_cluster = {tag: tuple(sorted(group))
                   for group in clusters.values() for tag in group
                   if len(group) > 1}

    rep.all_tag_counts = {tag: {"n": n, "wins": w} for tag, (n, w) in counts.items()}

    # يُفحَص ممثّل واحد لكل عنقود — الأطول اسماً لأنه غالباً الأوصف
    seen_clusters: set[tuple] = set()
    tag_tests = []
    for tag, (n, w) in counts.items():
        if n < min_tag:
            continue
        group = tag_cluster.get(tag)
        if group:
            if group in seen_clusters:
                continue
            seen_clusters.add(group)
            tag = max(group, key=len)
            n, w = counts[tag]
        tag_tests.append((tag, n, w))

    # ── تصحيح المقارنات المتعدّدة ──
    #
    # اثنا عشر فحصاً عند 5٪ تعني أن نصف اكتشاف متوقَّع بالصدفة. وبلا
    # تصحيح يجد كل تقرير «أنماطاً»، ثمّ تُبنى عليها قرارات.
    rep.tests_run = len(numeric_tests) + len(tag_tests)
    rep.corrected_alpha = alpha / max(1, rep.tests_run)
    z_corr = _z_for(rep.corrected_alpha)

    for fs in numeric_tests:
        # حجم أثر 0.35 عتبة عملية: أصغر منه لا يُترجَم إلى قرار حتى لو
        # اجتاز الدلالة على عيّنة كبيرة
        fs.significant = abs(fs.effect_size) >= 0.35
        if not fs.significant:
            fs.note = "لا يفصل — الفرق داخل الضجيج"
    rep.factors = sorted(numeric_tests, key=lambda f: -abs(f.effect_size))

    base = rep.baseline_win_rate
    pvals = [binom_two_sided_p(w, n, base) for _, n, w in tag_tests]
    survives_fdr = benjamini_hochberg(pvals, alpha=alpha)

    for (tag, n, wins), pv, fdr_ok in zip(tag_tests, pvals, survives_fdr):
        lo, hi = wilson_interval(wins, n)            # فاصل 95٪ للعرض
        rate = wins / n
        direction = ("أفضل" if rate > base else
                     "أسوأ" if rate < base else "لا فرق")
        if pv <= rep.corrected_alpha:
            strength = "قوي"
        elif fdr_ok:
            strength = "مرجَّح"
        elif pv <= alpha:
            strength = "ضعيف"
        else:
            strength = "لا شيء"
            direction = "لا فرق"
        rep.tags.append(TagSeparation(
            tag=tag, n=n, wins=wins, win_rate=rate, ci_low=lo, ci_high=hi,
            baseline=base, significant=bool(fdr_ok), direction=direction,
            p_value=pv, strength=strength,
            cluster=tag_cluster.get(tag, ()),
        ))
    rep.tags.sort(key=lambda t: (t.p_value, -t.n))

    # ── تحذيرات صريحة ──
    if rep.n_total < 100:
        rep.warnings.append(
            f"العيّنة {rep.n_total} صفقة — صغيرة؛ اقرأ الفواصل لا النسب.")
    # ── الاختبار الشامل ──
    #
    # سؤال مختلف عن «أيّ عامل يفصل؟»: هل **المجموعة** كلّها ضجيج؟
    #
    # لأن أربعة عشر فحصاً عند 5٪ يُتوقَّع منها 0.7 إشارة بالصدفة. فرصدُ
    # خمس إشارات لا ينجو أيّها منفرداً من التصحيح — لكنّ العدد نفسه
    # مستبعَد بالصدفة. والخلاصة حينها ليست «لا شيء هنا» بل «هنا شيء
    # والعيّنة أصغر من أن تقول أيّه».
    #
    # والفرق عملي: الأولى تقول «غيّر الاستراتيجية»، والثانية تقول
    # «اجمع بيانات أكثر على هذه العوامل بالذات».
    weak_hits = sum(1 for t in rep.tags if t.p_value <= alpha)
    if rep.tags:
        rep.global_p = binom_two_sided_p(weak_hits, len(rep.tags), alpha)
        expected = len(rep.tags) * alpha
        rep.global_signal = bool(weak_hits > expected and rep.global_p <= alpha)

    effective_tags = sum(1 for t in rep.tags if t.significant)
    weak = sum(1 for t in rep.tags if t.strength == "ضعيف")
    if not rep.has_findings and not rep.global_signal:
        rep.warnings.append(
            "لا عامل يفصل الرابح عن الخاسر، ولا المجموعة ككلّ تتجاوز "
            "الضجيج. هذه نتيجة صالحة لا فشل: ما يُقاس اليوم لا يحمل "
            "الحافّة، والبحث عن سبب في هذه الحقول سيكون سرداً.")
    elif rep.global_signal and not effective_tags:
        rep.warnings.append(
            f"لا عامل ينجو منفرداً، لكنّ {weak_hits} عاملاً ظهر عند 5٪ "
            f"بينما المتوقَّع بالصدفة {expected:.1f} فقط "
            f"(p={rep.global_p:.4f}). أي أن المجموعة ليست ضجيجاً: هنا "
            "شيء، والعيّنة أصغر من أن تحدّده. الخطوة الصحيحة جمع صفقات "
            "أكثر على هذه العوامل بالذات — لا تغيير الاستراتيجية ولا "
            "تفسير الفروق كأنها ثابتة.")
    if effective_tags:
        rep.warnings.append(
            f"فُحص {rep.tests_run} عاملاً. الناجي من ضبط معدّل الاكتشاف "
            f"الكاذب: {effective_tags}. وهذه **فرضيات** تستحقّ اختباراً "
            "على بيانات جديدة، لا حقائق مثبتة.")
    if weak and not rep.global_signal:
        rep.warnings.append(
            f"و{weak} عاملاً ظهر عند 5٪ خام ولم ينجُ من التصحيح — "
            "الأرجح أنه صدفة بين هذا العدد من الفحوص، فلا يُبنى عليه.")
    elif weak:
        rep.warnings.append(
            f"العوامل الخمسة الأضعف احتمالاً هي المرشَّحة للاختبار، "
            f"لا للتنفيذ. أقواها {rep.tags[0].tag} "
            f"({rep.tags[0].win_rate:.0%} على {rep.tags[0].n} صفقة، "
            f"p={rep.tags[0].p_value:.4f}).")
    return rep


def _z_for(alpha: float) -> float:
    """‏z لمستوى ثقة ثنائي الطرف — تقريب بلا scipy.

    ``scanner`` مستقلّة عن مكتبات ثقيلة عمداً، فيُستعمل تقريب
    Beasley–Springer–Moro العملي؛ خطؤه أقلّ من 0.0005 في المدى المهمّ.
    """
    p = 1 - alpha / 2
    if p <= 0 or p >= 1:
        return Z95
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
