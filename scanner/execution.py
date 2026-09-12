# -*- coding: utf-8 -*-
"""نموذج التنفيذ — كلفة الوصول إلى السوق، مستقلّة عن أي استراتيجية.

═══ لماذا هذا الملف يسبق كل شيء آخر ═══

قِيس على تسعين صفقة محسومة: الوقف الوسيط **1.19%** من السعر، أي أن
‏1R = حركة 1.19%. والتوقّع الإجمالي ‎+0.200R‎.

يترتّب على ذلك أن التكلفة التي تُصفّر الأفضلية كاملةً هي **0.238%**
ذهاباً وإياباً. وهذا رقم عادي تماماً: عمولة آخذ على بينانس وحدها
0.2% للرحلة، قبل أي فارق سعر أو انزلاق. وثلاث وسبعون من التسعين كانت
على سيولة «دقيقة» أو «منخفضة» — حيث الانزلاق أسوأ ما يكون.

فالنتيجة أن كل رقم أنتجه هذا المشروع حتى اليوم **إجمالي لا صافٍ**،
والفرق بينهما هو الفرق بين نظام له أفضلية ونظام ليس له.

═══ لماذا مستقلّ عن الاستراتيجية ═══

الكلفة خاصية **سوق ومنصّة وحجم**، لا خاصية إشارة. خلطها داخل محرّك
التوصية يعني أن تحسين الاستراتيجية وتغيير المنصّة يصيران تعديلاً في
المكان نفسه، فلا يُعرف أيّهما حرّك النتيجة. وهنا تُحقَن عند الحسم
وحده: ``tracking.resolve`` يُنتج R إجمالياً، وهذه الوحدة تحوّله صافياً.

═══ ما هو مقدَّر وما هو معلوم ═══

العمولة **معلومة** — رقم منشور من المنصّة.

الفارق السعري والانزلاق **مقدَّران**، ولا سبيل لمعرفتهما من شموع OHLC
لأنها لا تحفظ دفتر الأوامر. فالافتراضات هنا مُعلَنة بأسمائها ولا
تُدفن في ثوابت، والوحدة تُنتج **جدول حساسية** لا رقماً واحداً: القرار
السليم ليس «التوقّع كذا بعد التكلفة» بل «التوقّع يبقى موجباً حتى
تكلفة كذا». الأول يوهم بدقّة لا نملكها، والثاني قرار قابل للدفاع.

═══ تأخير التنفيذ ═══

القرار يُتَّخذ على شمعة **مغلقة**، فلا يمكن التنفيذ بسعر إغلاقها —
ذلك السعر مضى حين رأيته. التنفيذ الواقعي عند **افتتاح الشمعة
التالية**، والفجوة بينهما كلفة حقيقية لا تظهر في أي عمولة.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

# ───────────────────────────── فئات السيولة

# نقطة أساس = 0.01%. الأرقام أدناه **تقديرات معلنة** لا قياسات:
# دفتر الأوامر غير محفوظ عندنا، فالانزلاق لا يُشتقّ من OHLC. غرضها
# أن تكون نقطة انطلاق معقولة لجدول الحساسية، لا أن تُعامل كحقيقة.
#
# التدرّج نفسه هو الجزء المدافَع عنه: زوج بحجم مئتي ألف دولار يومياً
# يتحرّك بأمر واحد، وزوج بمئات الملايين لا. أمّا المقادير فتُعاير
# بمقارنة سعر التنفيذ الفعلي بسعر الإشارة حين تتوفّر صفقات حقيقية.
SLIPPAGE_BPS = {
    "high": 1.0,        # > 50 مليون$ يومياً
    "mid": 3.0,         # 5–50 مليون$
    "low": 8.0,         # 1–5 مليون$
    "micro": 20.0,      # < 1 مليون$
    "unknown": 20.0,    # المجهول يُعامل كالأسوأ — لا نُجمّل ما نجهله
}

HALF_SPREAD_BPS = {
    "high": 1.0, "mid": 2.0, "low": 5.0, "micro": 15.0, "unknown": 15.0,
}

TIERS = ("high", "mid", "low", "micro", "unknown")


@dataclass(frozen=True)
class CostModel:
    """كلفة الوصول إلى السوق. ثابتة بعد الإنشاء لتكون قابلة للأرشفة.

    ``maker`` أمر محدَّد ينتظر في الدفتر: لا انزلاق ولا فارق مدفوع —
    بل يُقبضان. ``taker`` أمر سوق يعبر الدفتر فيدفعهما معاً.

    وهذا التمييز ليس تنميقاً: خطة «شراء عند الارتداد» أمرٌ محدَّد،
    وضربُ الوقف أمرُ سوق. فالدخول أرخص من الخروج بنيوياً، وأي نموذج
    يطبّق كلفة واحدة على الطرفين يخطئ في الاتجاهين معاً.
    """

    maker_bps: float = 10.0     # بينانس سبوت VIP0 = 0.1%
    taker_bps: float = 10.0     # مع خصم BNB ≈ 7.5 نقطة أساس
    slippage_scale: float = 1.0     # مضاعف على جدول SLIPPAGE_BPS
    spread_scale: float = 1.0       # مضاعف على جدول HALF_SPREAD_BPS
    stop_slippage_mult: float = 2.0
    # الوقف يُضرب في حركة سريعة أحادية الاتجاه، فانزلاقه أسوأ من
    # انزلاق أمر سوق عادي. المضاعف تقدير مُعلن كغيره.

    def leg_bps(self, kind: str, tier: str = "unknown") -> float:
        """كلفة ساق واحدة بنقاط الأساس.

        ``kind``: ``maker`` · ``taker`` · ``stop``
        """
        tier = tier if tier in SLIPPAGE_BPS else "unknown"
        if kind == "maker":
            return self.maker_bps
        slip = SLIPPAGE_BPS[tier] * self.slippage_scale
        spread = HALF_SPREAD_BPS[tier] * self.spread_scale
        if kind == "stop":
            slip *= self.stop_slippage_mult
        return self.taker_bps + slip + spread

    def round_trip_bps(self, tier: str = "unknown", *,
                       entry_kind: str = "maker",
                       exit_kind: str = "taker") -> float:
        return self.leg_bps(entry_kind, tier) + self.leg_bps(exit_kind, tier)

    def cost_in_r(self, risk_pct: float, tier: str = "unknown", *,
                  entry_kind: str = "maker", exit_kind: str = "taker",
                  legs: int = 2) -> float:
        """الكلفة معبَّراً عنها بمضاعفات المخاطرة.

        ``risk_pct`` = |الدخول − الوقف| ÷ الدخول × 100.

        القسمة هي بيت القصيد: كلفة ثابتة بالنسبة المئوية تصير أثقل
        كلما ضاق الوقف. صفقة بوقف 5% تبتلع كلفة 0.2% بلا أثر يُذكر
        (‏0.04R‎)، وصفقة بوقف 0.5% تفقد بها **0.4R** — أي أن نفس
        المنصّة ونفس الرسوم تعني شيئين مختلفين تماماً حسب الخطة.

        وهذا يفسّر لماذا كان فريم 15m هو الأسوأ في سجلّنا: وقفه أضيق،
        فحصّة الكلفة من مخاطرته أكبر.
        """
        if risk_pct <= 0:
            return 0.0
        bps = self.round_trip_bps(tier, entry_kind=entry_kind,
                                  exit_kind=exit_kind)
        if legs > 2:
            # كل خروج جزئي إضافي ساقُ خروج كاملة
            bps += (legs - 2) * self.leg_bps(exit_kind, tier)
        return (bps / 100.0) / risk_pct

    def net_r(self, gross_r: float, risk_pct: float,
              tier: str = "unknown", **kw) -> float:
        return gross_r - self.cost_in_r(risk_pct, tier, **kw)

    def scaled(self, factor: float) -> "CostModel":
        """نسخة بكل التقديرات مضروبة — لبناء جدول الحساسية."""
        return replace(self, slippage_scale=self.slippage_scale * factor,
                       spread_scale=self.spread_scale * factor)


# النموذج الافتراضي: بينانس سبوت VIP0 بلا خصم BNB
DEFAULT = CostModel()

# نموذج بلا كلفة — لإظهار الفرق صراحةً لا لإخفائه
FREE = CostModel(maker_bps=0.0, taker_bps=0.0, slippage_scale=0.0,
                 spread_scale=0.0)


# ───────────────────────────── تأخير التنفيذ

def delayed_fill(bars: Iterable[dict], decided_at_close: float,
                 index: int = 0) -> float | None:
    """سعر التنفيذ الواقعي لقرار اتُّخذ على إغلاق شمعة مغلقة.

    القرار يُرى بعد الإغلاق، وذلك السعر مضى. التنفيذ عند **افتتاح
    الشمعة التالية**، والفرق بين الاثنين كلفة حقيقية لا تظهر في أي
    جدول رسوم — وقد تكون أكبر منها جميعاً في سوق يفتح بفجوة.

    ``None`` إن لم تكن هناك شمعة تالية: قرار بلا تنفيذ ممكن.
    """
    rows = list(bars)
    if index >= len(rows):
        return None
    nxt = rows[index]
    price = nxt.get("open")
    return float(price) if price is not None else float(decided_at_close)


def gap_cost_r(fill: float, decided: float, risk: float, side: str) -> float:
    """كلفة فجوة التنفيذ بمضاعفات المخاطرة (موجبة = خسارة)."""
    if risk <= 0:
        return 0.0
    diff = (fill - decided) if side == "buy" else (decided - fill)
    return diff / risk


# ───────────────────────────── جدول الحساسية

def sensitivity(gross_rows: Iterable[dict], model: CostModel = DEFAULT,
                factors: Iterable[float] = (0.0, 0.5, 1.0, 2.0, 3.0),
                ) -> list[dict]:
    """التوقّع الصافي عبر شبكة تقديرات — لا رقم واحد.

    كل صف يحتاج: ``r_multiple`` و ``risk_pct`` و ``liquidity``،
    واختيارياً ``entry_kind`` و ``exit_kind`` و ``legs``.

    السبب أن الانزلاق مجهول لا معلوم. عرض رقم واحد بعد التكلفة يوهم
    بدقّة لا نملكها؛ وعرض المنحنى يجيب السؤال القابل للدفاع: **عند أي
    مستوى تكلفة تنقلب النتيجة؟** فإن انقلبت عند تقدير متحفّظ، فالحكم
    أن الأفضلية غير مثبتة — لا أنها معدومة.
    """
    rows = [r for r in gross_rows if r.get("r_multiple") is not None]
    out: list[dict] = []
    for f in factors:
        m = model.scaled(f)
        if f == 0.0:
            m = replace(m, maker_bps=0.0, taker_bps=0.0)
        nets = []
        for r in rows:
            nets.append(m.net_r(
                float(r["r_multiple"]), float(r.get("risk_pct") or 0.0),
                r.get("liquidity") or "unknown",
                entry_kind=r.get("entry_kind", "maker"),
                exit_kind=r.get("exit_kind", "taker"),
                legs=int(r.get("legs", 2))))
        n = len(nets) or 1
        out.append({
            "factor": f,
            "label": ("بلا تكلفة" if f == 0 else
                      f"×{f:g} من التقدير الأساسي"),
            "trades": len(nets),
            "expectancy": sum(nets) / n,
            "total_r": sum(nets),
            "win_rate": sum(1 for x in nets if x > 0) / n * 100,
        })
    return out


def breakeven_bps(expectancy_r: float, risk_pct: float) -> float:
    """كم نقطة أساس (ذهاباً وإياباً) تُصفّر توقّعاً معلوماً."""
    return max(0.0, expectancy_r * risk_pct * 100.0)


# ───────────────────────────── بوّابة الجدوى الاقتصادية

MAX_COST_RATIO = 0.25       # الكلفة كنسبة من المخاطرة


def viability(risk_pct: float, tier: str = "unknown",
              model: CostModel = DEFAULT, *, entry_kind: str = "maker",
              exit_kind: str = "stop", max_ratio: float = MAX_COST_RATIO
              ) -> dict:
    """هل تستطيع هذه الخطة دفع كلفتها؟

    ليست فلتراً استراتيجياً بل **حساباً**: الكلفة نسبة ثابتة من السعر،
    والمخاطرة هي عرض الوقف. فحصّة الكلفة من المخاطرة = الكلفة ÷ الوقف،
    وهي تنفجر كلما ضاق الوقف. ولا علاقة لهذا بجودة الإشارة: خطة بوقف
    0.1% على زوج ضعيف السيولة تخسر المال حتى لو أصابت الاتجاه دائماً.

    القياس على 96 صفقة محسومة يُظهر التدرّج صريحاً:

        عرض الوقف     إجمالي     بعد التكلفة
        دون 0.5%      +0.36R       −3.75R
        0.5–1%        −0.11R       −0.74R
        1–2%          +0.19R       −0.16R
        2–4%          +0.10R       −0.03R
        فوق 4%        +0.35R       +0.29R

    وباستبعاد ما تتجاوز كلفته ربع مخاطرته يبقى 47 من 96، وتوقّعها
    الصافي **+0.45R** بعد التكلفة الكاملة. أي أن المحرّك ليس عاجزاً —
    بل يصدر نصف خططه بخسارة مضمونة حسابياً قبل أن يتحرّك السعر.

    الحدّ 0.25 اختيار معلن لا مشتقّ: عند ربع المخاطرة تبتلع الكلفة
    ربع كل خسارة وتقتطع من كل ربح. رفعُه يوسّع التغطية ويقرّبنا من
    الحافة، وخفضُه يشدّد ويقلّل الفرص.
    """
    cost = cost_in_r_for(risk_pct, tier, model,
                         entry_kind=entry_kind, exit_kind=exit_kind)
    return {
        "cost_r": cost,
        "risk_pct": risk_pct,
        "ok": cost <= max_ratio,
        "ratio": cost,
        "reason": ("" if cost <= max_ratio else
                   f"الكلفة {cost:.2f}R من مخاطرة {risk_pct:.2f}% — "
                   f"تتجاوز الحدّ {max_ratio:.0%}"),
    }


def cost_in_r_for(risk_pct: float, tier: str, model: CostModel = DEFAULT,
                  **kw) -> float:
    return model.cost_in_r(risk_pct, tier, **kw)


def min_risk_pct(tier: str = "unknown", model: CostModel = DEFAULT, *,
                 entry_kind: str = "maker", exit_kind: str = "stop",
                 max_ratio: float = MAX_COST_RATIO) -> float:
    """أضيق وقف تبقى معه الخطة اقتصادية، بالنسبة المئوية من السعر."""
    bps = model.round_trip_bps(tier, entry_kind=entry_kind,
                               exit_kind=exit_kind)
    return (bps / 100.0) / max_ratio if max_ratio > 0 else float("inf")
