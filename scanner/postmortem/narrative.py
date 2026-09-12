# -*- coding: utf-8 -*-
"""تفسير التشريح — النموذج يشرح ما ثبت، ولا يخترع ما لم يثبت.

═══ القاعدة ═══

النموذج **لا يرى صفقة واحدة بنتيجتها**. يرى جدول فروق مقيسة على
المجموعتين، مع بيان أيّ فرق اجتاز الدلالة وأيّ لم يجتز.

والفرق بين المدخلين ليس تفصيلاً: نموذج يرى «صفقة BTCUSDT خسرت −1R»
سيؤلّف لها سبباً — لا لأنه يكذب بل لأن هذا ما تفعله النماذج اللغوية:
تُكمل النمط. وأثره أنك تقرأ تفسيراً بليغاً لنمطٍ لا وجود له، ثمّ تبني
عليه قراراً.

أما جدول الفروق فيقيّد الجواب: «العامل الفلاني نسبته 27٪ مقابل أساس
43٪ على 74 صفقة، فاصله [0.18, 0.38]». هنا للنموذج عمل حقيقي — أن
يقترح **آلية** لهذا الفرق المقيس، ويقول ما الذي يختبرها.

═══ ماذا يُطلَب منه بالضبط ═══

    • آلية محتملة لكل فرق ثبت — لا إعادة صياغة للرقم
    • تجربة تفصل بين تفسيرين متنافسين
    • وصراحةً: «لا سبب واضح» حين لا يفصل شيء

والأخيرة أهمّها. تقريرٌ لا يجد شيئاً نتيجةٌ صالحة، وإجباره على إيجاد
شيء هو بالضبط ما يحوّل القياس إلى خرافة.
"""
from __future__ import annotations

from typing import Any

from .separation import PostmortemReport

__all__ = ["build_prompt", "SYSTEM_AR", "render_report"]

SYSTEM_AR = """\
أنت محلّل كمّي في منصّة CS Edge. أمامك نتائج **قياس** أُجري على صفقات
محسومة، لا الصفقات نفسها.
مهمّتك اقتراح آلية سوقية لكل فرق **ثبت إحصائياً**، واقتراح تجربة تفصل
بين التفسيرات المتنافسة.
لا تشرح فرقاً لم يجتز الدلالة، ولا تُعد صياغة الأرقام كأنها تفسير.
إن لم يثبت شيء فقل ذلك صراحةً — «لا عامل يفصل» نتيجة صالحة.
تكتب بالعربية المهنية وتُخرج JSON صالحاً فقط."""

_SCHEMA = """\
أعِد JSON بهذه الحقول:
verdict: "توجد فروق مفسَّرة" | "لا فروق تتجاوز الضجيج"
success_drivers: [{factor, mechanism, confidence: 0-100}]
failure_drivers: [{factor, mechanism, confidence: 0-100}]
competing_explanations: [نصوص]
suggested_experiments: [{hypothesis, method, expected_outcome}]
what_not_to_conclude: [نصوص — استنتاجات تبدو مغرية ولا تسندها هذه البيانات]
summary: فقرة عربية واحدة"""


def render_report(rep: PostmortemReport) -> str:
    """جدول الفروق كنصّ عربي مضغوط — هذا ما يصل النموذج."""
    out: list[str] = []
    out.append(
        f"## العيّنة\n"
        f"محسومة: {rep.n_total} · رابحة: {rep.n_won} · خاسرة: {rep.n_lost}\n"
        f"نسبة النجاح الأساس: {rep.baseline_win_rate:.1%} · "
        f"التوقّع: {rep.expectancy_r:+.3f}R"
    )

    out.append(
        f"## منهج القياس\n"
        f"فُحص {rep.tests_run} عاملاً. الحكم بضبط معدّل الاكتشاف الكاذب "
        f"(بنجاميني-هوشبرج عند 5٪)، و«قوي» يعني نجا حتى من بونفيروني "
        f"({rep.corrected_alpha:.4f}). ★ ثبت · ? مرشَّح لم يثبت."
    )

    # حقول ما قبل الدخول — وهي وحدها القابلة لأن تكون سبباً
    lines = []
    for f in rep.factors:
        mark = "★" if f.significant else "—"
        lines.append(
            f"{mark} {f.field_name}: رابحة {f.mean_won:.3g} · "
            f"خاسرة {f.mean_lost:.3g} · حجم الأثر {f.effect_size:+.2f}"
            + (f" ({f.note})" if f.note else "")
        )
    if lines:
        out.append("## فروق ما كان معلوماً قبل الدخول\n" + "\n".join(lines))

    sig = [t for t in rep.tags if t.significant]
    if sig:
        rows = [
            f"★ {t.tag} — {t.direction}: {t.win_rate:.1%} على {t.n} صفقة "
            f"(فاصل [{t.ci_low:.2f}, {t.ci_high:.2f}] مقابل أساس "
            f"{t.baseline:.1%})"
            for t in sig
        ]
        out.append("## عوامل ثبت فصلها\n" + "\n".join(rows))
    elif rep.global_signal:
        # لا شيء ينجو منفرداً، لكنّ المجموعة ليست ضجيجاً. فالمرشَّحون
        # يُعرَضون **موسومين بأنهم مرشَّحون** — إخفاؤهم يضيّع الدليل،
        # وعرضهم كثوابت يصنع خرافة.
        cands = [t for t in rep.tags if t.p_value <= 0.05][:6]
        rows = [
            f"? {t.tag} — {t.direction}: {t.win_rate:.1%} على {t.n} صفقة "
            f"(p={t.p_value:.4f}، لم ينجُ من التصحيح)"
            for t in cands
        ]
        out.append(
            "## مرشَّحون — لم يثبت أيّهم منفرداً\n"
            + "\n".join(rows)
            + f"\n\nلكنّ ظهور {len(cands)} منها بينما المتوقَّع بالصدفة "
              f"{len(rep.tags) * 0.05:.1f} مستبعَد (p={rep.global_p:.4f}) — "
              "فالمجموعة تحمل إشارة والعيّنة أصغر من أن تحدّدها."
        )
    else:
        out.append("## عوامل ثبت فصلها\nلا شيء، ولا المجموعة ككلّ "
                   "تتجاوز الضجيج.")

    # ما فُحص ولم يثبت يُذكر أيضاً: غيابه يوهم أنه لم يُفحص، فيُعاد
    # اقتراحه في كل تقرير
    nulls = [t for t in rep.tags if not t.significant][:8]
    if nulls:
        out.append("## عوامل فُحصت ولم تفصل\n"
                   + "، ".join(f"{t.tag} ({t.n})" for t in nulls))

    if rep.outcome_description:
        desc = " · ".join(
            f"{k}: رابحة {v['won']} مقابل خاسرة {v['lost']}"
            for k, v in rep.outcome_description.items()
        )
        out.append(
            "## وصف النتيجة (ليست أسباباً)\n" + desc + "\n"
            "هذه الفروق مضمونة بالتعريف — الرابحة رابحة لأنها بلغت R "
            "عالياً. لا تُقدّمها تفسيراً."
        )

    if rep.warnings:
        out.append("## تحذيرات\n" + "\n".join(f"- {w}" for w in rep.warnings))

    return "\n\n".join(out)


def build_prompt(rep: PostmortemReport) -> dict[str, Any]:
    """موجّه التفسير — ``{system_prompt, user_prompt}``."""
    guard = (
        "قيود ملزِمة:\n"
        "- العوامل المعلَّمة بـ★ ثابتة: اشرح آليتها.\n"
        "- والمعلَّمة بـ? مرشَّحة لم تثبت: لا تُسند إليها سبباً، بل "
        "اقترح تجربة تحسمها. ذكرها في success_drivers أو "
        "failure_drivers خطأ.\n"
        "- لا تستعمل حقول النتيجة (best_r · worst_r · مدّة الاحتفاظ) "
        "تفسيراً.\n"
        "- إن لم يوجد عامل ★ فاجعل verdict = «لا فروق تتجاوز الضجيج» "
        "واترك قائمتي الأسباب فارغتين، وضع المرشَّحين في "
        "suggested_experiments وحدها.\n"
        "- الآلية يجب أن تكون سببية مقترحة، لا إعادة صياغة للرقم."
    )
    user = f"{guard}\n\n{render_report(rep)}\n\n{_SCHEMA}"
    return {"system_prompt": SYSTEM_AR, "user_prompt": user}
