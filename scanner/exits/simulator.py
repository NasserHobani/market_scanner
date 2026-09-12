# -*- coding: utf-8 -*-
"""محاكاة قواعد الخروج — شمعة بشمعة، على البيانات الحقيقية.

═══ المسألة ═══

صفقة تدخل عند 1، هدفها 4، ووقفها 0.5. ترتفع إلى 3 — أي ‎+4R — ثمّ
تعود فتضرب الوقف عند ‎−1R. النتيجة في السجلّ: خسارة. والواقع أن الخطّة
كانت رابحة ثمّ أُعيد ما كسبته كلّه.

وقياسٌ على صفقاتك يقول إن هذا ليس استثناءً:

    71٪ من الصفقات الخاسرة بلغت ‎+0.5R قبل أن تنقلب
    39٪ منها بلغت ‎+1.0R
    ووسيط ما أُعيد في الخاسرة: 1.70R

═══ لماذا لا يكفي best_r ═══

الحقلان ``best_r`` و``worst_r`` يحفظان أقصى ربح وأقصى خسارة، لكنّهما
**لا يحفظان ترتيبهما**. وقاعدة «انقل الوقف إلى التعادل بعد ‎+1R» يتوقّف
حكمها على السؤال: هل بلغ السعر ‎+1R قبل أن يهبط إلى ‎−0.4R أم بعده؟

فصفقةٌ ذهبت ‎+1.2R ثمّ ‎−0.3R ثمّ ‎+2R ثمّ ضربت الوقف: قاعدة التعادل
تُخرجها عند صفر. وصفقة ذهبت ‎−0.3R ثمّ ‎+1.2R ثمّ ضربت الوقف: القاعدة
تُخرجها عند صفر أيضاً لكن بعد رحلة مختلفة. و``best_r``/``worst_r``
متطابقان في الحالتين.

ولهذا تُعاد المحاكاة **من الشموع** لا من الملخّصين. وأي تقدير من
الملخّصين وحدهما يميل إلى التفاؤل، لأنه يفترض أن الذروة سبقت القاع.

═══ التحفّظ الأهمّ ═══

هذه محاكاة على **الشموع** لا على التِّك. والشمعة تخبرنا أن السعر بلغ
قمّتها وقاعها، ولا تخبرنا أيّهما أوّلاً. فحين يلامس الوقف والهدف في
شمعة واحدة يُحتسب **الوقف** — لأن افتراض الأسوأ يمنع تقديراً متفائلاً
لا يتحقّق في التنفيذ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

__all__ = ["ExitRule", "TradeResult", "RULES", "simulate", "compare_rules"]


@dataclass
class TradeResult:
    r_multiple: float
    bars_held: int
    exit_reason: str
    legs: int = 2          # عدد سيقان التنفيذ — الجني الجزئي يزيدها
    peak_r: float = 0.0
    trough_r: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"r": round(self.r_multiple, 4), "bars": self.bars_held,
                "reason": self.exit_reason, "legs": self.legs,
                "peak_r": round(self.peak_r, 3),
                "trough_r": round(self.trough_r, 3)}


@dataclass
class ExitRule:
    """قاعدة خروج قابلة للمحاكاة."""

    name: str
    label: str
    breakeven_at: float | None = None   # انقل الوقف للتعادل بعد هذا الـR
    trail_at: float | None = None       # ابدأ التتبّع بعد هذا الـR
    trail_by: float | None = None       # مسافة التتبّع عن الذروة، بالـR
    partial_at: float | None = None     # اجنِ نصف المركز عند هذا الـR
    partial_size: float = 0.5
    time_stop: int | None = None        # أغلق بالسوق بعد هذا العدد من الشموع
    description: str = ""


# قواعد تُقاس، لا تُفترَض. وأرقامها من ملاحظة القياس أعلاه:
# ذروة الخاسرة غالباً بين 0.5R و1.5R، فالعتبات تحيط بهذا المدى.
RULES: tuple[ExitRule, ...] = (
    ExitRule("fixed", "الحالي: وقف ثابت وهدف ثابت",
             description="خطّ الأساس — ما يفعله النظام اليوم."),
    ExitRule("be_1r", "تعادل بعد +1R", breakeven_at=1.0,
             description="ينقل الوقف إلى الدخول بعد بلوغ +1R."),
    ExitRule("be_075", "تعادل بعد +0.75R", breakeven_at=0.75),
    ExitRule("be_15", "تعادل بعد +1.5R", breakeven_at=1.5),
    ExitRule("trail_1r_1r", "تتبّع بمسافة 1R بعد +1R",
             trail_at=1.0, trail_by=1.0),
    ExitRule("trail_1r_05", "تتبّع بمسافة 0.5R بعد +1R",
             trail_at=1.0, trail_by=0.5),
    ExitRule("partial_1r", "جني نصف عند +1R ثمّ تعادل",
             partial_at=1.0, breakeven_at=1.0,
             description="يقلّل التقلّب لكنه يضيف ساق تنفيذ — تُحتسب كلفتها."),
    ExitRule("partial_15", "جني نصف عند +1.5R ثمّ تعادل",
             partial_at=1.5, breakeven_at=1.5),
    ExitRule("time_20", "وقف زمني بعد 20 شمعة", time_stop=20),
)


def _bar_low_high(bar: dict) -> tuple[float, float]:
    return float(bar.get("low")), float(bar.get("high"))


def simulate(bars: Sequence[dict], *, side: str, entry: float, stop: float,
             target: float, rule: ExitRule,
             max_bars: int | None = None) -> TradeResult | None:
    """يحاكي صفقة واحدة تحت قاعدة خروج واحدة.

    يُفترَض أن الصفقة **دخلت** عند ``entry``؛ الغرض مقارنة قواعد الخروج
    لا إعادة فحص الدخول.
    """
    risk = abs(entry - stop)
    if risk <= 0 or not bars:
        return None
    buy = str(side).lower() != "sell"

    def r_of(price: float) -> float:
        return ((price - entry) if buy else (entry - price)) / risk

    live_stop = stop
    peak_r = trough_r = 0.0
    banked = 0.0                    # ما جُني جزئياً، بالـR الموزون
    remaining = 1.0                 # حصّة المركز الباقية
    legs = 2

    for i, bar in enumerate(bars, start=1):
        if max_bars and i > max_bars:
            break
        low, high = _bar_low_high(bar)
        bar_best = r_of(high if buy else low)
        bar_worst = r_of(low if buy else high)
        peak_r = max(peak_r, bar_best)
        trough_r = min(trough_r, bar_worst)

        stop_r = r_of(live_stop)

        # ── الوقف أوّلاً: الشمعة لا تخبرنا بترتيب قمّتها وقاعها،
        # فيُفترَض الأسوأ. الافتراض المتفائل هنا يُنتج نتائج لا تتحقّق.
        if bar_worst <= stop_r:
            return TradeResult(banked + remaining * stop_r, i,
                               "وقف" if stop_r < 0 else "تعادل",
                               legs, peak_r, trough_r)

        # ── الهدف
        target_r = r_of(target)
        if bar_best >= target_r:
            return TradeResult(banked + remaining * target_r, i, "هدف",
                               legs, peak_r, trough_r)

        # ── الجني الجزئي
        if (rule.partial_at is not None and remaining >= 1.0
                and bar_best >= rule.partial_at):
            banked += rule.partial_size * rule.partial_at
            remaining -= rule.partial_size
            legs += 1               # ساق تنفيذ إضافية — لها كلفتها

        # ── نقل الوقف إلى التعادل
        if (rule.breakeven_at is not None and bar_best >= rule.breakeven_at
                and r_of(live_stop) < 0.0):
            live_stop = entry

        # ── التتبّع
        if (rule.trail_at is not None and rule.trail_by is not None
                and peak_r >= rule.trail_at):
            want_r = peak_r - rule.trail_by
            want = entry + (want_r * risk if buy else -want_r * risk)
            if (buy and want > live_stop) or (not buy and want < live_stop):
                live_stop = want

        # ── الوقف الزمني: إغلاق بالسوق على الإغلاق
        if rule.time_stop is not None and i >= rule.time_stop:
            close_r = r_of(float(bar.get("close")))
            return TradeResult(banked + remaining * close_r, i, "وقف زمني",
                               legs, peak_r, trough_r)

    # لم تُحسم ضمن الشموع المتاحة — تُقيَّم على آخر إغلاق
    last_r = r_of(float(bars[-1].get("close")))
    return TradeResult(banked + remaining * last_r, len(bars), "مفتوحة",
                       legs, peak_r, trough_r)


@dataclass
class RuleStats:
    rule: str
    label: str
    n: int = 0
    wins: int = 0
    expectancy: float = 0.0
    gross_expectancy: float = 0.0
    cost_r: float = 0.0
    avg_bars: float = 0.0
    reasons: dict[str, int] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "label": self.label, "n": self.n,
                "win_rate": round(self.win_rate, 4),
                "expectancy": round(self.expectancy, 4),
                "gross_expectancy": round(self.gross_expectancy, 4),
                "cost_r": round(self.cost_r, 4),
                "avg_bars": round(self.avg_bars, 1),
                "reasons": dict(self.reasons)}


def compare_rules(trades: Sequence[dict], *,
                  bars_for: Callable[[dict], Sequence[dict]],
                  rules: Sequence[ExitRule] = RULES,
                  cost_per_leg_r: float = 0.0) -> dict[str, RuleStats]:
    """يقارن القواعد على مجموعة صفقات.

    Parameters
    ----------
    cost_per_leg_r:
        كلفة ساق التنفيذ الواحدة بالـR. **ليست تفصيلاً**: الجني الجزئي
        يضيف ساقاً، وقياسٌ سابق في هذا المشروع أظهر أن أثر الجني
        الجزئي المُقاس على أرقام **إجمالية** يتبخّر حين تُحتسب الكلفة.
        فتركُها صفراً يُنتج توصية تبدو رابحة وتخسر في التنفيذ.
    """
    out = {r.name: RuleStats(r.name, r.label) for r in rules}
    for tr in trades:
        bars = bars_for(tr)
        if not bars:
            continue
        # سعر التنفيذ الفعلي حين يوجد: الخطة تُكتب بسعر مخطَّط، والأمر
        # قد يُملأ عند غيره. والمقارنة بالسعر المخطَّط تُنتج فروقاً لا
        # علاقة لها بقاعدة الخروج.
        entry = tr.get("entry_price") or tr.get("entry")
        stop = tr.get("stop")
        target = tr.get("target1")
        if None in (entry, stop, target):
            continue
        for rule in rules:
            res = simulate(bars, side=tr.get("side", "buy"),
                           entry=float(entry), stop=float(stop),
                           target=float(target), rule=rule)
            if res is None:
                continue
            st = out[rule.name]
            st.n += 1
            st.wins += int(res.r_multiple > 0)
            st.gross_expectancy += res.r_multiple
            st.cost_r += cost_per_leg_r * res.legs
            st.avg_bars += res.bars_held
            st.reasons[res.exit_reason] = st.reasons.get(res.exit_reason, 0) + 1

    for st in out.values():
        if st.n:
            st.gross_expectancy /= st.n
            st.cost_r /= st.n
            st.avg_bars /= st.n
            st.expectancy = st.gross_expectancy - st.cost_r
    return out
