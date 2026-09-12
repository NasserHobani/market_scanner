# -*- coding: utf-8 -*-
"""حسم نتائج الصفقات وتلخيص الأداء — مستقلّ عن Django تماماً.

لماذا الحسم بالشموع لا بالسعر اللحظي:

المراقب يفحص كل خمس دقائق. لو اعتمدنا عليه وحده، فحركة تلمس الوقف ثم
ترتدّ للهدف خلال دقيقتين ستُسجَّل ربحاً — والصفقة الحقيقية كانت خسارة.
الشموع تحفظ القمة والقاع فلا تضيع أي لمسة. لذلك المراقب هنا يعرض السعر
فقط، والحسم النهائي من الشموع.

والقاعدة التي تحكم الغموض: إذا لمست شمعة واحدة الوقف والهدف معاً فلا
سبيل لمعرفة أيّهما أولاً من بيانات OHLC، فنحسبها **خسارة**. أي افتراض
آخر يجمّل النتائج، وغرض هذا الملف قياس الأداء لا تحسين مظهره.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

# حالات الصفقة
PENDING = "pending"     # الخطة صدرت والسعر لم يبلغ الدخول بعد
OPEN = "open"           # دخلت ولم تُحسم
WON = "won"             # الهدف الأول قبل الوقف
LOST = "lost"           # الوقف قبل الهدف
EXPIRED = "expired"     # انقضت المهلة بلا دخول

ARABIC = {PENDING: "تنتظر الدخول", OPEN: "مفتوحة", WON: "رابحة",
          LOST: "خاسرة", EXPIRED: "لم تُفعَّل"}


@dataclass
class Plan:
    """خطة الصفقة كما صدرت — لا تتغيّر بعد الإصدار."""

    side: str           # buy / sell
    entry: float
    stop: float
    target: float

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    def valid(self) -> bool:
        if self.risk <= 0:
            return False
        if self.side == "buy":
            return self.stop < self.entry < self.target
        return self.target < self.entry < self.stop


@dataclass
class Resolution:
    status: str
    entry_price: float | None = None
    exit_price: float | None = None
    r_multiple: float | None = None
    entry_bar: int | None = None
    exit_bar: int | None = None
    note: str = ""
    bars_held: int = 0
    excursion: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "entry_price": self.entry_price,
            "exit_price": self.exit_price, "r_multiple": self.r_multiple,
            "entry_bar": self.entry_bar, "exit_bar": self.exit_bar,
            "note": self.note, "bars_held": self.bars_held,
            "excursion": dict(self.excursion),
        }


def _favourable(side: str, a: float, b: float) -> bool:
    """هل a أفضل من b لصاحب الصفقة؟"""
    return a >= b if side == "buy" else a <= b


def resolve(bars: Sequence[dict], plan: Plan, *,
            already_entered: bool = False,
            entry_price: float | None = None,
            max_bars: int | None = None) -> Resolution:
    """يحسم الصفقة من شموع ما بعد الإشارة.

    ``bars`` قائمة قواميس فيها open/high/low/close مرتّبة زمنياً، تبدأ من
    الشمعة التالية للإشارة. ``max_bars`` مهلة الدخول: بعدها تُعدّ الخطة
    لم تُفعَّل.
    """
    if not plan.valid():
        return Resolution(status=EXPIRED, note="خطة غير صالحة")

    buy = plan.side == "buy"
    entered = already_entered
    fill = entry_price if already_entered else None
    entry_bar = 0 if already_entered else None
    # الصفقة المستأنَفة تبدأ رحلتها من سعر تنفيذها، وإلا بقيت None
    # فانهار حساب أقصى ربح/خسارة عند أول شمعة
    best = worst = fill

    for i, bar in enumerate(bars):
        try:
            o = float(bar["open"]); h = float(bar["high"])
            lo = float(bar["low"]); c = float(bar["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (lo <= h):
            continue

        # ── الدخول ──
        if not entered:
            if max_bars is not None and i >= max_bars:
                return Resolution(status=EXPIRED, entry_bar=None,
                                  note=f"لم يبلغ الدخول خلال {max_bars} شمعة")
            touched = lo <= plan.entry if buy else h >= plan.entry
            if not touched:
                continue
            # فجوة تتجاوز الدخول: التنفيذ عند الافتتاح لا عند السعر المطلوب
            gapped = o <= plan.entry if buy else o >= plan.entry
            fill = o if gapped else plan.entry
            # لكن إن فتحت الشمعة بعد الوقف نفسه، فالخطة انتهت قبل أن
            # تبدأ: لا أحد يشتري وقفُه مخترَق سلفاً. تسجيلها صفقة يعني
            # حشو الإحصاءات بصفقات لم تُنفَّذ قطّ — وكان المحرّك يسجّلها
            # بـ 0R لأنه ينفّذ ويخرج عند السعر ذاته.
            if (fill <= plan.stop) if buy else (fill >= plan.stop):
                return Resolution(
                    status=EXPIRED, entry_bar=None,
                    note="فجوة تخطّت الوقف قبل الدخول — الخطة لاغية")
            entered, entry_bar = True, i
            best = worst = fill

        # ── بعد الدخول ──
        best = max(best, h) if buy else min(best, lo)
        worst = min(worst, lo) if buy else max(worst, h)

        risk = abs(fill - plan.stop)
        if risk <= 0:
            return Resolution(status=EXPIRED, note="مخاطرة صفرية بعد التنفيذ")

        def out(price: float, status: str, note: str = "") -> Resolution:
            r = (price - fill) / risk * (1 if buy else -1)
            return Resolution(
                status=status, entry_price=fill, exit_price=price,
                r_multiple=round(r, 3), entry_bar=entry_bar, exit_bar=i,
                note=note, bars_held=i - entry_bar + 1,
                excursion={"best_r": round(abs(best - fill) / risk, 2)
                                      * (1 if _favourable(plan.side, best, fill) else -1),
                           "worst_r": -round(abs(worst - fill) / risk, 2)},
            )

        # فجوة تتخطّى الوقف: الخروج عند الافتتاح، والخسارة أكبر من 1R
        if (o <= plan.stop) if buy else (o >= plan.stop):
            return out(o, LOST, "فجوة تخطّت الوقف")
        # فجوة تتخطّى الهدف لصالحنا
        if (o >= plan.target) if buy else (o <= plan.target):
            return out(o, WON, "فجوة تخطّت الهدف")

        hit_stop = lo <= plan.stop if buy else h >= plan.stop
        hit_target = h >= plan.target if buy else lo <= plan.target

        if hit_stop and hit_target:
            # الترتيب داخل الشمعة مجهول — نأخذ الأسوأ حتى لا نجمّل النتيجة
            return out(plan.stop, LOST, "الشمعة لمست الوقف والهدف — احتُسبت خسارة")
        if hit_stop:
            return out(plan.stop, LOST)
        if hit_target:
            return out(plan.target, WON)

    if not entered:
        return Resolution(status=PENDING, note="لم يبلغ الدخول بعد")

    risk = abs(fill - plan.stop)
    last = float(bars[-1]["close"]) if bars else fill
    r = (last - fill) / risk * (1 if buy else -1) if risk else 0.0
    return Resolution(
        status=OPEN, entry_price=fill, r_multiple=round(r, 3),
        entry_bar=entry_bar, bars_held=len(bars) - (entry_bar or 0),
        excursion={"best_r": round((abs(best - fill) / risk), 2)
                              * (1 if _favourable(plan.side, best, fill) else -1),
                   "worst_r": -round(abs(worst - fill) / risk, 2)} if risk else {},
    )


# ───────────────────────────────────────────── الإحصاءات

def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """مجال ثقة ويلسون لنسبة النجاح.

    ضروري لا تجميلي: 3 من 4 تعني نسبة 75% لكن مجالها الحقيقي 30%–95%.
    عرض 75% وحدها من أربع صفقات يوهم بيقين لا وجود له.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(max(0.0, (centre - spread) / d) * 100, 1),
            round(min(1.0, (centre + spread) / d) * 100, 1))


def summarize(rows: Iterable[dict]) -> dict:
    """ملخّص أداء لمجموعة صفقات محسومة.

    كل صف: {"status": won/lost/..., "r_multiple": float|None}
    الصفقات غير المحسومة تُستثنى من النسب وتُعدّ منفصلة — إدخالها يفسد
    كل رقم لأن نتيجتها غير معروفة بعد.
    """
    rows = list(rows)
    closed = [r for r in rows if r.get("status") in (WON, LOST)]
    wins = [r for r in closed if r["status"] == WON]
    losses = [r for r in closed if r["status"] == LOST]

    def rs(items):
        return [float(x["r_multiple"]) for x in items
                if x.get("r_multiple") is not None]

    won_r, lost_r = rs(wins), rs(losses)
    all_r = won_r + lost_r
    gross_win = sum(x for x in won_r if x > 0)
    gross_loss = abs(sum(x for x in lost_r if x < 0))
    n = len(closed)
    equity = []
    cur = 0.0
    for x in all_r:
        cur += x
        equity.append(cur)
    peak = -10**9
    max_dd = 0.0
    for x in equity:
        peak = max(peak, x)
        max_dd = max(max_dd, peak - x)
    stdev = math.sqrt(sum((x - (sum(all_r) / len(all_r))) ** 2 for x in all_r) / len(all_r)) if all_r else 0.0
    sharpe = ((sum(all_r) / len(all_r)) / stdev * math.sqrt(len(all_r))
              if all_r and stdev > 0 else None)
    recovery = ((sum(all_r) / max_dd) if max_dd > 0 else None)
    # الاتساق = نسبة النوافذ المتحركة (5 صفقات) ذات متوسط موجب
    windows = []
    if len(all_r) >= 5:
        for i in range(0, len(all_r) - 4):
            windows.append(sum(all_r[i:i + 5]) / 5)
    consistency = (sum(1 for w in windows if w > 0) / len(windows) * 100
                   if windows else (round(len(wins) / n * 100, 1) if n else None))

    lo, hi = wilson(len(wins), n)
    return {
        "total": len(rows),
        "closed": n,
        "open": sum(1 for r in rows if r.get("status") == OPEN),
        "pending": sum(1 for r in rows if r.get("status") == PENDING),
        "expired": sum(1 for r in rows if r.get("status") == EXPIRED),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n * 100, 1) if n else None,
        "win_rate_low": lo if n else None,
        "win_rate_high": hi if n else None,
        "avg_r": round(sum(all_r) / len(all_r), 2) if all_r else None,
        "total_r": round(sum(all_r), 2) if all_r else 0.0,
        "avg_win_r": round(sum(won_r) / len(won_r), 2) if won_r else None,
        "avg_loss_r": round(sum(lost_r) / len(lost_r), 2) if lost_r else None,
        # عامل الربح: لا نعيد لانهاية عند غياب الخسائر — نعيد None ونترك
        # العرض يقول «لا خسائر بعد» بدل رقم يوحي بكمال
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "expectancy": round(sum(all_r) / n, 2) if n else None,
        "max_drawdown_r": round(max_dd, 2) if all_r else None,
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "recovery_factor": round(recovery, 2) if recovery is not None else None,
        "consistency_score": round(consistency, 1) if consistency is not None else None,
        "stdev_r": round(stdev, 3) if all_r else None,
        "reliable": n >= 20,     # دون ذلك النسبة ضجيج أكثر منها إشارة
    }


def split(rows: Iterable[dict], key: str, *,
          min_n: int = 1) -> list[dict]:
    """تقسيم الأداء حسب حقل واحد، مرتّباً بالأفضل أداءً.

    الترتيب بالتوقّع (expectancy) لا بنسبة النجاح: شريحة تربح 80% بمكاسب
    ضئيلة وخسائر كبيرة أسوأ من شريحة تربح 40% بمكاسب واسعة.
    """
    buckets: dict[Any, list[dict]] = {}
    for row in rows:
        buckets.setdefault(row.get(key) or "—", []).append(row)

    out = []
    for value, group in buckets.items():
        s = summarize(group)
        if s["closed"] < min_n:
            continue
        s["value"] = value
        out.append(s)
    out.sort(key=lambda s: (s["expectancy"] is None, -(s["expectancy"] or 0)))
    return out


def split_multi(rows: Iterable[dict], key: str, *, min_n: int = 1) -> list[dict]:
    """كالسابق لكن القيمة قائمة — صفقة واحدة تُحسب في كل عامل من عواملها.

    لهذا لا تجمع الأعداد إلى مجموع الصفقات، وهو متوقّع: السؤال هنا
    «كيف تؤدّي الصفقات التي تحمل هذا العامل؟» لا «كم صفقة لكل عامل؟».
    """
    rows = list(rows)
    buckets: dict[Any, list[dict]] = {}
    for row in rows:
        for value in (row.get(key) or []) or ["—"]:
            buckets.setdefault(value, []).append(row)

    out = []
    for value, group in buckets.items():
        s = summarize(group)
        if s["closed"] < min_n:
            continue
        s["value"] = value
        out.append(s)
    out.sort(key=lambda s: (s["expectancy"] is None, -(s["expectancy"] or 0)))
    return out
