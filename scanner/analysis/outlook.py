"""توقّع الأسبوع: أين قد يصل السعر، وما الفرصة عند كل مستوى.

ما تفعله هذه الوحدة وما لا تفعله — يجب أن يكون واضحاً:

تفعل: تقيس التذبذب التاريخي، وتحسب المدى المتوقع خلال أسبوع، وتقدّر
احتمال ملامسة كل مستوى مهم، وتجهّز خطة مشروطة لكل سيناريو.

لا تفعل: التنبؤ بالاتجاه. الاحتمالات هنا مشتقّة من التذبذب وحده بافتراض
مشية عشوائية بلا انحياز — أي أنها تجيب «ما احتمال أن يلمس السعر هذا
المستوى خلال أسبوع؟» لا «هل سيصعد أم يهبط؟».

الأساس الرياضي: مبدأ الانعكاس. لمشية عشوائية بانحراف معياري σ خلال المدة،
احتمال ملامسة مستوى يبعد d ≈ 2 × Φ(−d/σ). تقريب معقول لا قانون.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import MarketConfig
from ..formatting import price as fmt_price
from ..indicators.pine import atr
from ..indicators.structure import build_structure, detect_channel, fib_levels
from . import price_action as pa_mod

BARS_PER_DAY = {"15m": 96, "1h": 24, "4h": 6, "1d": 1, "1w": 1 / 7}


@dataclass
class Level:
    price: float
    source: str
    direction: int          # 1 فوق السعر · -1 تحته
    distance_pct: float
    touch_probability: float
    plan: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "price": self.price, "source": self.source, "direction": self.direction,
            "distance_pct": round(self.distance_pct, 2),
            "probability": round(self.touch_probability * 100),
            "plan": self.plan,
        }


@dataclass
class WeeklyOutlook:
    horizon_days: int = 7
    expected_move_pct: float = 0.0
    range_low: float = 0.0
    range_high: float = 0.0
    levels: list[Level] = field(default_factory=list)
    bias: str = ""
    summary: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "horizon_days": self.horizon_days,
            "expected_move_pct": round(self.expected_move_pct, 2),
            "range_low": self.range_low, "range_high": self.range_high,
            "levels": [x.as_dict() for x in self.levels],
            "bias": self.bias, "summary": self.summary, "notes": self.notes,
        }


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def touch_probability(distance: float, sigma: float) -> float:
    """احتمال ملامسة مستوى يبعد `distance` خلال المدة ذات الانحراف `sigma`."""
    if sigma <= 0 or distance <= 0:
        return 1.0 if distance <= 0 else 0.0
    return min(1.0, 2.0 * _norm_cdf(-distance / sigma))


def _sigma_for_horizon(df: pd.DataFrame, timeframe: str, days: int) -> float:
    """الانحراف المعياري المتوقع للسعر خلال المدة، من عوائد الشموع."""
    returns = np.log(df["close"] / df["close"].shift(1)).dropna()
    if len(returns) < 30:
        return 0.0
    per_bar = float(returns.tail(200).std())
    bars = BARS_PER_DAY.get(timeframe, 6) * days
    return per_bar * math.sqrt(max(bars, 1))


def build(df: pd.DataFrame, cfg: MarketConfig, timeframe: str,
          days: int = 7, market_context: dict | None = None) -> WeeklyOutlook:
    p = cfg.params
    close = float(df["close"].iloc[-1])
    a = float(atr(df, p.atr_len).iloc[-1])
    out = WeeklyOutlook(horizon_days=days)

    sigma_log = _sigma_for_horizon(df, timeframe, days)
    if sigma_log <= 0 or not np.isfinite(a) or a <= 0:
        out.summary = "بيانات غير كافية لتقدير المدى"
        return out

    sigma_price = close * sigma_log
    out.expected_move_pct = sigma_log * 100
    out.range_low = close * math.exp(-sigma_log)
    out.range_high = close * math.exp(sigma_log)

    structure = build_structure(df, p.zigzag_len, p.min_swing_atr, p.atr_len)
    action = pa_mod.analyze(df, structure, p.atr_len)
    channel = detect_channel(df, structure, a, flat_atr=p.ch_flat_atr,
                             tol_atr=p.ch_tol_atr, min_bars=p.ch_min_bars,
                             min_touches=p.ch_min_touches, min_contain=p.ch_min_contain)

    # ── جمع المستويات المهمة من كل المصادر ──
    candidates: list[tuple[float, str]] = []
    if structure.structure_high > structure.structure_low:
        for ratio, lvl in fib_levels(structure.structure_high,
                                     structure.structure_low).items():
            candidates.append((float(lvl), f"فيبو {ratio * 100:.1f}%".replace(".0", "")))
    candidates.append((float(structure.structure_high), "القمة الهيكلية"))
    candidates.append((float(structure.structure_low), "القاع الهيكلي"))

    if channel is not None:
        lo, hi = channel.bounds_at(len(df) - 1)
        candidates.append((float(lo), "قاع القناة"))
        candidates.append((float(hi), "سقف القناة"))

    for z in action.zones:
        edge = z.top if z.top < close else z.bottom
        candidates.append((float(edge), z.arabic))
    for lvl in action.equal_levels:
        candidates.append((float(lvl["price"]), lvl["kind"]))

    # ── ترشيح وحساب الاحتمال ──
    seen: set[int] = set()
    levels: list[Level] = []
    for value, source in candidates:
        if not np.isfinite(value) or value <= 0:
            continue
        key = int(value / max(a * 0.3, 1e-12))       # دمج المستويات المتقاربة
        if key in seen:
            continue
        seen.add(key)

        distance = abs(value - close)
        prob = touch_probability(distance, sigma_price)
        if prob < 0.05:
            continue
        levels.append(Level(
            price=float(value), source=source,
            direction=1 if value > close else -1,
            distance_pct=(value - close) / close * 100,
            touch_probability=prob,
        ))

    levels.sort(key=lambda x: -x.touch_probability)
    out.levels = levels[:8]

    # ── خطة لكل مستوى تحت السعر (فرصة شراء محتملة) ──
    for lvl in out.levels:
        if lvl.direction != -1:
            continue
        stop = min(structure.structure_low, lvl.price - a * 1.2) - a * 0.25
        risk = lvl.price - stop
        if risk <= 0:
            continue
        target = lvl.price + risk * cfg.rr_ratio
        lvl.plan = {
            "entry": lvl.price, "stop": stop, "target": target,
            "rr": round(cfg.rr_ratio, 2),
            "condition": f"ارتداد صاعد من {fmt_price(lvl.price)} بشمعة تأكيد",
        }

    # ── الميل العام ──
    trend = action.trend
    htf_note = (market_context or {}).get("regime", "")
    if trend == "صاعد":
        out.bias = "الأرجح استمرار الصعود مع تصحيحات"
    elif trend == "هابط":
        out.bias = "الأرجح استمرار الهبوط — الشراء ضده مخاطرة"
    else:
        out.bias = "نطاق عرضي — التداول بين الحدين"

    best_buy = next((x for x in out.levels if x.direction == -1 and x.plan), None)
    if best_buy:
        out.summary = (
            f"خلال {days} أيام، المدى المتوقع ±{out.expected_move_pct:.1f}%. "
            f"أقرب فرصة شراء محتملة عند {fmt_price(best_buy.price)} "
            f"({best_buy.source}) باحتمال وصول {best_buy.touch_probability * 100:.0f}%."
        )
    else:
        out.summary = (f"خلال {days} أيام، المدى المتوقع ±{out.expected_move_pct:.1f}%. "
                       f"لا مستوى شراء واضح ضمن المدى.")

    out.notes = [
        "الاحتمالات مشتقّة من التذبذب وحده بافتراض مشية عشوائية — لا تتنبأ بالاتجاه.",
        f"الهيكل الحالي: {trend}",
    ]
    if htf_note:
        out.notes.append(htf_note)
    return out
