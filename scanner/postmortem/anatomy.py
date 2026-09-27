# -*- coding: utf-8 -*-
"""تشريح النتيجة — حسابٌ لا سرد.

═══ لماذا هذا الملفّ ═══

في هذه الحزمة بالفعل فحصان:

    ``single.py``      جودة **القرار** — والنتيجة محجوبة عن الحاكم
    ``separation.py``  ما يفصل الرابح عن الخاسر في **المجموعة**

ولا واحدٌ منهما يقول ما جرى **لهذه الصفقة** ميكانيكياً. وبينهما
فجوةٌ عملية: صفقةٌ بلغت ‎+2.3R‎ ثمّ أُغلقت خاسرة ليست كصفقةٍ لم
تتحرّك لصالحك قطّ. الأولى عطبُ **خروج**، والثانية عطبُ **دخول** —
ونتيجتهما في الجدول واحدة: «خاسرة».

فمن يقرأ نسبة النجاح وحدها يصلح ما ليس مكسوراً.

═══ والأرقام موجودة أصلاً ═══

``best_r`` أقصى ربحٍ غير محقّق، و``worst_r`` أقصى تراجع. وهما
يُسجَّلان لكل صفقة منذ بناء النموذج، ولم يُقرآ إلّا وصفاً.

═══ ولا سرد هنا ═══

لا جملةَ «فشلت لأنّ السوق انعكس». هذا الملفّ يصنّف بالأرقام،
والتفسير اللغوي في ``narrative.py`` خلف حجبٍ للنتيجة. وخلطُهما
هو ما يُنتج «الحكم بالنتيجة» الذي بُنيت هذه الحزمة لتجنّبه.

═══ والسؤال الذي يجيب عنه أخيراً ═══

«هل كان وقفي ضيّقاً؟» لا يُجاب بالرأي. يُجاب بمقارنة ``worst_r``
لهذه الصفقة بتوزيع ``worst_r`` في **الصفقات الرابحة**: إن كان
رابحوك ينزلون إلى ‎−0.8R‎ عادةً ووقفُك عند ‎−1.0R‎، فالوقف ليس
المشكلة. وإن كانوا لا ينزلون دون ‎−0.4R‎ وهذه بلغت ‎−1.0R‎، فالدخول
هو المشكلة لا الوقف.
"""
from __future__ import annotations

from typing import Any

__all__ = ["classify", "anatomy", "stop_context", "KINDS", "KIND_LABELS"]

# ═══ عتبات التصنيف ═══
#
# كلّها بوحدة R — أي نسبةً إلى المخاطرة نفسها. والمطلق (بالدولار
# أو النسبة المئوية) لا يُقارَن بين صفقةٍ وقفُها ٢٪ وأخرى وقفُها ٨٪.

#: دون هذا لم تتحرّك لصالحك أصلاً
DEAD_R = 0.3
#: فوق هذا كانت رابحةً فعلاً في وقتٍ ما
WORKED_R = 1.0
#: تراجعٌ أقلّ من هذا يعني أنّها لم تُختبَر
CALM_R = 0.5
#: ربحٌ أقلّ من هذا تبتلعه الكلفة والانزلاق
SCRAPE_R = 0.5

KINDS = (
    "clean_win", "survived_win", "scraped_win",
    "gave_back", "thesis_dead", "stopped_normal", "near_miss",
    "unknown",
)

KIND_LABELS = {
    "clean_win": "ربحٌ نظيف — بلغت الهدف بلا اختبار",
    "survived_win": "ربحٌ بعد نجاة — كادت تُوقَف ثمّ عملت",
    "scraped_win": "ربحٌ هزيل — تبتلعه الكلفة",
    "gave_back": "رُدّ الربح — عملت ثمّ انعكست",
    "thesis_dead": "الفكرة لم تعمل — لم تتحرّك لصالحك قطّ",
    "stopped_normal": "وقفٌ عاديّ — تحرّكت قليلاً ثمّ عادت",
    "near_miss": "كادت — قاربت الهدف ولم تبلغه",
    "unknown": "غير كافٍ للتصنيف",
}

#: أين يقع الخلل — وهو ما يحدّد ما يُصلَح
BLAME = {
    "gave_back": "exit",
    "near_miss": "exit",
    "thesis_dead": "entry",
    "stopped_normal": "entry",
    "scraped_win": "exit",
    "clean_win": "",
    "survived_win": "",
    "unknown": "",
}


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def classify(trade: dict) -> str:
    """نوعُ ما جرى — من ``best_r`` و``worst_r`` و``r_multiple``.

    ═══ والغائب لا يُصنَّف ═══

    صفقةٌ بلا ``best_r`` لم تُتابَع، ولا يُعرف مسارها. وتصنيفُها
    «الفكرة لم تعمل» لأنّ الحقل فارغ يخترع حكماً من غياب.
    """
    status = str(trade.get("status") or "")
    if status not in ("won", "lost"):
        return "unknown"

    best = _f(trade.get("best_r"))
    worst = _f(trade.get("worst_r"))
    r = _f(trade.get("r_multiple"))
    if best is None or r is None:
        return "unknown"

    if status == "won":
        if r < SCRAPE_R:
            return "scraped_win"
        # ═══ النجاة ليست نظافة ═══
        #
        # صفقةٌ نزلت إلى ‎−0.9R‎ ثمّ بلغت الهدف ربحت — ووقفٌ أضيق
        # بقليل كان سيقتلها. وعدُّها «نظيفة» يُخفي أنّها كانت على
        # حافّة الحظّ.
        if worst is not None and worst <= -(1 - CALM_R):
            return "survived_win"
        return "clean_win"

    # ── الخاسرة ──
    if best >= WORKED_R:
        # عملت فعلاً ثمّ انعكست: الخلل في الخروج لا الدخول
        return "gave_back"
    if best >= 0.7:
        return "near_miss"
    if best < DEAD_R:
        return "thesis_dead"
    return "stopped_normal"


def stop_context(trade: dict, winners: list[dict]) -> dict:
    """هل كان الوقف ضيّقاً؟ — بمقارنة رابحيك لا بالرأي.

    يقارن ``worst_r`` لهذه الصفقة بتوزيع ``worst_r`` في الصفقات
    **الرابحة**: كم منها نجا من تراجعٍ بهذا العمق؟

    ═══ ولماذا الرابحة وحدها ═══

    الخاسرة تُوقَف عند ‎−1R‎ بالتعريف، فتوزيعها مقطوعٌ هناك. أمّا
    الرابحة فقد نزلت ثمّ صعدت — وهي وحدها التي تقول كم يتذبذب
    هذا النظام قبل أن يعمل.
    """
    mine = _f(trade.get("worst_r"))
    depths = sorted(d for d in (_f(w.get("worst_r")) for w in winners)
                    if d is not None)
    if mine is None or len(depths) < 10:
        return {"ok": False,
                "why": (f"يلزم عشر صفقات رابحة بمسارٍ مسجَّل "
                        f"(المتاح {len(depths)})" if mine is not None
                        else "لا مسار مسجَّل لهذه الصفقة")}

    # كم من الرابحات نزلت أعمق من هذه؟
    deeper = sum(1 for d in depths if d <= mine)
    share = deeper / len(depths) * 100.0
    median = depths[len(depths) // 2]

    if share >= 25:
        verdict = ("وقفُك ليس ضيّقاً: "
                   f"{share:.0f}٪ من رابحيك نزلوا إلى هذا العمق أو أعمق "
                   "ثمّ عملوا. فالخلل في الدخول أو التوقيت لا في الوقف.")
        tight = False
    elif share >= 5:
        verdict = (f"{share:.0f}٪ فقط من رابحيك نزلوا إلى هنا. "
                   "وقفٌ أوسع قليلاً كان قد ينقذ بعضها — والثمن خسارةٌ "
                   "أكبر حين لا ينقذ.")
        tight = None
    else:
        verdict = (f"رابحوك نادراً ما ينزلون إلى هذا العمق "
                   f"({share:.0f}٪، والوسيط {median:+.2f}R). "
                   "فبلوغُ هذا التراجع علامةٌ على أنّ الفكرة كانت "
                   "خاطئة — لا أنّ الوقف كان ضيّقاً.")
        tight = False

    return {"ok": True, "worst_r": mine, "winners_n": len(depths),
            "deeper_share_pct": round(share, 1),
            "winners_median_worst_r": round(median, 2),
            "stop_too_tight": tight, "verdict": verdict}


def anatomy(trade: dict, *, winners: list[dict] | None = None) -> dict:
    """التشريح الكامل لصفقةٍ واحدة — أرقامٌ وحكمٌ على موضع الخلل."""
    kind = classify(trade)
    best = _f(trade.get("best_r"))
    worst = _f(trade.get("worst_r"))
    r = _f(trade.get("r_multiple"))
    bars = trade.get("bars_held")

    # ═══ ما رُدّ من الربح ═══
    #
    # الفرق بين أقصى ما بلغت وما أُغلقت عليه. وهو الرقم الذي يقول
    # «كم تركتَ على الطاولة» — ولا يظهر في أيّ عمودٍ آخر.
    given_back = None
    if best is not None and r is not None and best > 0:
        given_back = round(best - r, 2)

    efficiency = None
    if best and best > 0 and r is not None:
        # كم اقتنصتَ من الحركة التي أتاحتها لك
        efficiency = round(max(0.0, r) / best * 100.0, 1)

    out = {
        "kind": kind,
        "label": KIND_LABELS[kind],
        "blame": BLAME.get(kind, ""),
        "best_r": best, "worst_r": worst, "r_multiple": r,
        "bars_held": bars,
        "given_back_r": given_back,
        "capture_pct": efficiency,
        "notes": [],
    }

    if kind == "gave_back":
        out["notes"].append(
            f"بلغت {best:+.2f}R ثمّ أُغلقت على {r:+.2f}R — "
            f"رُدّ {given_back:.2f}R. هذه ليست إشارةً خاطئة: الدخول "
            "عمل، والخروج لم يُحمِ ما كُسب. "
            "والعلاج جزئيٌّ عند ‎+1R‎ أو وقفٌ متحرّك، لا تغيير المرشّح.")
    elif kind == "thesis_dead":
        out["notes"].append(
            f"أقصى ما بلغته {best:+.2f}R — أي أنّها لم تتحرّك لصالحك "
            "أصلاً. المرشّح هو موضع النظر، لا الخروج.")
    elif kind == "near_miss":
        out["notes"].append(
            f"بلغت {best:+.2f}R — قاربت ولم تبلغ. وهدفٌ أقرب كان "
            "سيحوّلها رابحة، وثمنُه أنّ الرابحات الكبيرة تصغر. "
            "لا يُغيَّر الهدف من صفقةٍ واحدة.")
    elif kind == "survived_win":
        out["notes"].append(
            f"نزلت إلى {worst:+.2f}R قبل أن تعمل — ربحت، لكنّها كانت "
            "قريبةً من الوقف. ولا تُعدّ دليلاً على جودة الدخول.")
    elif kind == "scraped_win":
        out["notes"].append(
            f"ربحٌ {r:+.2f}R — العمولة والانزلاق يأكلان أكثره. "
            "وتكرارُه يُنتج منحنىً صاعداً بلا مال.")

    if efficiency is not None and efficiency < 50 and (r or 0) > 0:
        out["notes"].append(
            f"اقتنصتَ {efficiency:.0f}٪ من الحركة المتاحة.")

    if winners:
        out["stop_context"] = stop_context(trade, winners)
    return out
