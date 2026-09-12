# -*- coding: utf-8 -*-
"""فحص صفقة واحدة — جودة القرار لا جودة النتيجة.

═══ المسألة ═══

«لماذا خسرت هذه الصفقة؟» سؤال يبدو بريئاً وهو أخطر أسئلة التداول.
لأن السائل يعرف الجواب سلفاً (خسرت)، والمجيب — إنساناً كان أو نموذجاً —
سيبني سرداً يقود إليه. وتخرج بقاعدة جديدة مستنبطة من صفقة واحدة.

وهذا ما يسمّيه أهل القرار **الحكم بالنتيجة** (resulting): تقييم قرارٍ
بما آل إليه لا بما كان معلوماً حين اتُّخذ. ولاعب الورق الذي يراهن
براجحة ويخسر لم يخطئ؛ خسر فقط.

═══ الصياغة الصادقة ═══

فالسؤال هنا معكوس، وفي خطوتين:

    ١. **يُحجَب** عن النموذج كل ما جرى بعد الدخول — النتيجة، و R،
       وأقصى ربح، ومدّة الاحتفاظ. ويُسأل: هل كان هذا قراراً سليماً
       بما كان معلوماً؟
    ٢. ثمّ تُكشَف النتيجة **للمستخدم وحده**، مع مقارنتها بما تقوله
       إحصاءات المجموعة عن صفقة بهذه الخصائص.

فتحصل على تمييز لا يُنتجه السؤال المباشر:

    قرار سليم · نتيجة رابحة   →  كما ينبغي
    قرار سليم · نتيجة خاسرة   →  خسارة طبيعية؛ لا تغيّر شيئاً
    قرار ضعيف · نتيجة رابحة   →  **الأخطر**: نجاح يعزّز عادة سيّئة
    قرار ضعيف · نتيجة خاسرة   →  هنا يُستفاد

والحالة الثالثة هي التي لا يراها أحد بلا هذا الفصل.

═══ ما يُسنِد الحكم ═══

النموذج لا يحكم من فراغ: يرى وسوم الصفقة **مع نسب نجاحها في مجموعتك**
وفواصلها ودرجة صمودها. فقولُه «هذا الدخول ضعيف» يستند إلى أن وسمه
نسبته 27٪ على 74 صفقة، لا إلى انطباع.
"""
from __future__ import annotations

from typing import Any

from .separation import PostmortemReport, extract_tags

__all__ = ["TradeCard", "build_card", "build_single_prompt",
           "render_card", "SYSTEM_AR", "OUTCOME_KEYS"]

# كل ما لا يُعرَف إلّا بعد الدخول. يُحجَب عن النموذج حجباً تامّاً.
OUTCOME_KEYS = frozenset({
    "status", "r_multiple", "best_r", "worst_r", "bars_held", "exit_price",
    "closed_at", "opened_at", "resolution_note", "last_price", "checked_at",
    "entry_price",
})

SYSTEM_AR = """\
أنت محلّل كمّي في منصّة CS Edge. أمامك صفقة **لم تُحسم بعد** من وجهة
نظرك: نتيجتها محجوبة عنك عمداً.
مهمّتك تقييم **جودة القرار** بما كان معلوماً لحظة الدخول، مستنداً إلى
إحصاءات المجموعة المرفقة لكل وسم.
لا تخمّن النتيجة ولا تلمّح إليها. حكمك على القرار لا على ما آل إليه.
تكتب بالعربية المهنية وتُخرج JSON صالحاً فقط."""

_SCHEMA = """\
أعِد JSON بهذه الحقول:
decision_quality: "سليم" | "مقبول" | "ضعيف" | "غير كافٍ للحكم"
confidence: 0-100
supporting: [نصوص — ما يدعم سلامة الدخول، مع نسب المجموعة]
concerns: [نصوص — ما يُضعفه]
missing_checks: [نصوص — ما كان ينبغي فحصه قبل الدخول ولم يُفحص]
expected_win_rate: رقم أو null — من إحصاءات الوسوم وحدها، لا تخمينك
would_take_again: true | false | null
summary: فقرة عربية واحدة"""


class TradeCard:
    """بطاقة صفقة: ما كان معلوماً، وما تقوله المجموعة عنه."""

    def __init__(self) -> None:
        self.symbol = ""
        self.market = ""
        self.timeframe = ""
        self.side = ""
        self.entry_facts: dict[str, Any] = {}
        self.tags: list[dict[str, Any]] = []
        self.expected_win_rate: float | None = None
        self.baseline: float = 0.0
        self.n_population: int = 0
        self.notes: list[str] = []
        # النتيجة تُحفَظ هنا **للمستخدم**، ولا تدخل الموجّه أبداً
        self.outcome: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "market": self.market,
            "timeframe": self.timeframe, "side": self.side,
            "entry_facts": self.entry_facts, "tags": self.tags,
            "expected_win_rate": self.expected_win_rate,
            "baseline": self.baseline, "n_population": self.n_population,
            "notes": list(self.notes), "outcome": self.outcome,
        }


def build_card(trade: dict, rep: PostmortemReport) -> TradeCard:
    """يبني البطاقة من صفقة وتقرير المجموعة."""
    card = TradeCard()
    card.symbol = str(trade.get("symbol") or "")
    card.market = str(trade.get("market") or "")
    card.timeframe = str(trade.get("timeframe") or "")
    card.side = str(trade.get("side") or "")
    card.baseline = rep.baseline_win_rate
    card.n_population = rep.n_total

    for key in ("score", "confidence", "rr", "grade", "entry", "stop",
                "target1", "action", "source"):
        val = trade.get(key)
        if val not in (None, "", [], {}):
            card.entry_facts[key] = val

    by_tag = {t.tag: t for t in rep.tags}
    seen: set[str] = set()
    rates: list[tuple[float, int]] = []
    for src in ("reasons", "factors"):
        for tag in extract_tags(trade.get(src)):
            if tag in seen:
                continue
            seen.add(tag)
            stat = by_tag.get(tag)
            if stat is None:
                # لم يبلغ عتبة الحكم — لكن عدده معروف. عرضه بعدده
                # ونسبته موسوماً بأن العيّنة لا تكفي أنفع من «مجهول»:
                # الأوّل يقول «ضعيف الدلالة»، والثاني يقول «لا أعرف»
                # وهما ليسا سواء.
                raw = (rep.all_tag_counts or {}).get(tag) or {}
                n_raw = int(raw.get("n") or 0)
                item = {"tag": tag, "known": False, "n": n_raw}
                if n_raw:
                    item["win_rate"] = round(int(raw.get("wins") or 0) / n_raw, 4)
                card.tags.append(item)
                continue
            card.tags.append({
                "tag": tag, "known": True, "n": stat.n,
                "win_rate": round(stat.win_rate, 4),
                "ci": [round(stat.ci_low, 3), round(stat.ci_high, 3)],
                "strength": stat.strength, "direction": stat.direction,
                "p_value": round(stat.p_value, 5),
            })
            rates.append((stat.win_rate, stat.n))

    # التوقّع من الوسوم: متوسّط موزون بحجم عيّنة كل وسم.
    #
    # هذا تقدير خشن لا نموذج: الوسوم متداخلة وغير مستقلّة، فالمتوسّط
    # الموزون لا يجمعها جمعاً صحيحاً احتمالياً. ويُذكر بوصفه إشارة
    # تقريبية — والبديل (نموذج مشترك) يحتاج عيّنة أكبر بكثير.
    if rates:
        total = sum(n for _, n in rates)
        card.expected_win_rate = round(
            sum(r * n for r, n in rates) / total, 4) if total else None
        card.notes.append(
            "التوقّع متوسّط موزون بأحجام العيّنات — تقدير خشن، "
            "فالوسوم متداخلة ولا تُجمَع جمعاً احتمالياً صحيحاً.")

    # النتيجة — للعرض على المستخدم، خارج الموجّه
    card.outcome = {
        k: trade.get(k) for k in ("status", "r_multiple", "best_r",
                                  "worst_r", "bars_held")
        if trade.get(k) is not None
    }
    return card


def render_card(card: TradeCard) -> str:
    """البطاقة كنصّ للنموذج — **بلا النتيجة**."""
    out: list[str] = [
        f"## الصفقة\n{card.symbol} · {card.market} · {card.timeframe} · "
        f"اتجاه {card.side or '—'}"
    ]

    facts = " · ".join(f"{k}: {v}" for k, v in card.entry_facts.items())
    if facts:
        out.append("## ما كان معلوماً لحظة الدخول\n" + facts)

    known = [t for t in card.tags if t.get("known")]
    if known:
        rows = []
        for t in known:
            mark = {"قوي": "★", "مرجَّح": "☆"}.get(t["strength"], "?")
            rows.append(
                f"{mark} {t['tag']}: {t['win_rate']:.0%} على {t['n']} صفقة "
                f"(فاصل [{t['ci'][0]:.2f}, {t['ci'][1]:.2f}] · {t['strength']})"
            )
        out.append(
            f"## وسوم هذه الصفقة في مجموعتك (الأساس {card.baseline:.0%} على "
            f"{card.n_population} صفقة)\n" + "\n".join(rows)
            + "\n★ ثبت · ☆ مرجَّح · ? لم يثبت — لا تبنِ حكماً على «?»."
        )

    unknown = [t for t in card.tags if not t.get("known")]
    if unknown:
        rows = []
        for t in unknown:
            if t.get("n"):
                rows.append(f"{t['tag']}: {t.get('win_rate', 0):.0%} على "
                            f"{t['n']} صفقة فقط")
            else:
                rows.append(f"{t['tag']}: لم يظهر في المجموعة")
        out.append(
            "## وسوم عيّنتها لا تكفي للحكم\n" + "\n".join(rows)
            + "\nالنسب أعلاه **إشارات لا أحكام** — لا تبنِ عليها وحدها."
        )

    if card.expected_win_rate is not None:
        out.append(
            f"## التوقّع من الوسوم\n{card.expected_win_rate:.0%} "
            f"مقابل أساس {card.baseline:.0%}"
        )

    if card.notes:
        out.append("## تحفّظات\n" + "\n".join(f"- {n}" for n in card.notes))

    out.append(
        "## قيد ملزِم\n"
        "نتيجة هذه الصفقة **محجوبة عنك عمداً**. لا تخمّنها ولا تلمّح "
        "إليها. قيّم القرار بما كان معلوماً، فقرارٌ سليم قد يخسر وقرارٌ "
        "ضعيف قد يربح."
    )
    return "\n\n".join(out)


def build_single_prompt(card: TradeCard) -> dict[str, str]:
    return {
        "system_prompt": SYSTEM_AR,
        "user_prompt": f"{render_card(card)}\n\n{_SCHEMA}",
    }


def verdict_vs_outcome(quality: str, status: str) -> dict[str, str]:
    """يقابل حكم القرار بالنتيجة الفعلية — بعد أن يُدلي النموذج بحكمه.

    هذه المقابلة هي حاصل الميزة كلّها. والحالة التي لا يراها أحد بلا
    هذا الفصل هي «قرار ضعيف · نتيجة رابحة»: نجاحٌ يعزّز عادة سيّئة،
    ولا شيء في السجلّ ينبّهك إليه لأن السجلّ يعدّ الأرباح لا القرارات.
    """
    good = quality in ("سليم", "مقبول")
    won = str(status) == "won"
    if good and won:
        return {"label": "قرار سليم · ربح", "tone": "up",
                "note": "كما ينبغي — كرّر هذا النمط."}
    if good and not won:
        return {"label": "قرار سليم · خسارة", "tone": "dim",
                "note": "خسارة طبيعية ضمن التوقّع. لا تغيّر القاعدة "
                        "لأجل نتيجة واحدة."}
    if not good and won:
        return {"label": "قرار ضعيف · ربح", "tone": "warn",
                "note": "أخطر حالة: نجاح يعزّز عادة سيّئة. الربح هنا "
                        "لا يبرّر الدخول."}
    return {"label": "قرار ضعيف · خسارة", "tone": "down",
            "note": "هنا يُستفاد — راجع ما فات فحصه قبل الدخول."}
