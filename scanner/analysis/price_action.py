"""حركة السعر: هيكل السوق، السيولة، مناطق الأوامر، الفجوات.

الفكرة المركزية: السعر لا يتحرك عشوائياً بين المستويات، بل يقصد السيولة.
القمم والقيعان الواضحة تتجمّع خلفها أوامر وقف، والحركة نحوها ثم الارتداد
منها فوراً ليست فشلاً بل هدفاً محققاً — وهي أقوى إشارة في هذه المدرسة.

كل ما هنا سببي: يعتمد على قمم وقيعان مؤكدة بشموع بعدها، لا على المستقبل.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..indicators.pine import atr
from ..indicators.structure import Pivot, Structure


@dataclass
class Zone:
    kind: str            # demand | supply | fvg_bull | fvg_bear
    arabic: str
    top: float
    bottom: float
    index: int
    strength: float = 0.0
    tested: int = 0
    mitigated: bool = False

    def contains(self, price: float, tol: float = 0.0) -> bool:
        return (self.bottom - tol) <= price <= (self.top + tol)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "arabic": self.arabic, "top": self.top,
                "bottom": self.bottom, "strength": round(self.strength, 2),
                "tested": self.tested}


@dataclass
class PriceAction:
    trend: str = "غير محدد"          # صاعد | هابط | عرضي
    structure_events: list[dict] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    sweeps: list[dict] = field(default_factory=list)
    equal_levels: list[dict] = field(default_factory=list)
    premium_discount: str = ""
    score: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "trend": self.trend,
            "events": self.structure_events[-4:],
            "zones": [z.as_dict() for z in self.zones],
            "sweeps": self.sweeps[-3:],
            "equal_levels": self.equal_levels[-4:],
            "premium_discount": self.premium_discount,
            "score": self.score,
            "notes": self.notes,
        }


def _label_swings(pivots: list[Pivot]) -> list[dict]:
    """تسمية القمم والقيعان: HH / HL / LH / LL — أساس قراءة الهيكل."""
    out = []
    last_high = last_low = None
    for pv in pivots:
        if pv.is_high:
            tag = "HH" if last_high is not None and pv.price > last_high else \
                  "LH" if last_high is not None else "H"
            last_high = pv.price
        else:
            tag = "HL" if last_low is not None and pv.price > last_low else \
                  "LL" if last_low is not None else "L"
            last_low = pv.price
        out.append({"index": pv.index, "price": pv.price,
                    "is_high": pv.is_high, "tag": tag})
    return out


def _trend_from_swings(swings: list[dict]) -> str:
    recent = [s["tag"] for s in swings[-4:]]
    ups = sum(1 for t in recent if t in ("HH", "HL"))
    downs = sum(1 for t in recent if t in ("LH", "LL"))
    if ups >= 3:
        return "صاعد"
    if downs >= 3:
        return "هابط"
    return "عرضي"


def _structure_events(swings: list[dict], trend: str) -> list[dict]:
    """كسر الهيكل (BOS) وتغيّر الطابع (CHoCH)."""
    events = []
    for i in range(2, len(swings)):
        cur, prev = swings[i], swings[i - 2]
        if cur["is_high"] != prev["is_high"]:
            continue
        if cur["is_high"] and cur["price"] > prev["price"]:
            kind = "BOS ⇧" if cur["tag"] == "HH" else "CHoCH ⇧"
            events.append({"index": cur["index"], "price": cur["price"],
                           "kind": kind, "direction": 1})
        elif not cur["is_high"] and cur["price"] < prev["price"]:
            kind = "BOS ⇩" if cur["tag"] == "LL" else "CHoCH ⇩"
            events.append({"index": cur["index"], "price": cur["price"],
                           "kind": kind, "direction": -1})
    return events


def _liquidity_sweeps(df: pd.DataFrame, swings: list[dict], a: float,
                      lookback: int = 60) -> list[dict]:
    """اصطياد السيولة: اختراق قمة/قاع سابق ثم الإغلاق داخل النطاق.

    هذه أقوى إشارة في مدرسة حركة السعر: الاختراق أخذ أوامر الوقف
    المتجمّعة، والإغلاق العائد يعني أن الاختراق لم يكن حقيقياً.
    """
    out = []
    n = len(df)
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    closes = df["close"].to_numpy()

    for sw in swings[-12:]:
        level = sw["price"]
        start = sw["index"] + 1
        if start >= n:
            continue
        for i in range(start, min(n, start + lookback)):
            if sw["is_high"]:
                if highs[i] > level + a * 0.05 and closes[i] < level:
                    out.append({"index": int(i), "level": float(level),
                                "kind": "اصطياد سيولة علوية", "direction": -1,
                                "time": int(df.index[i].timestamp())})
                    break
            else:
                if lows[i] < level - a * 0.05 and closes[i] > level:
                    out.append({"index": int(i), "level": float(level),
                                "kind": "اصطياد سيولة سفلية", "direction": 1,
                                "time": int(df.index[i].timestamp())})
                    break
    return out


def _equal_levels(swings: list[dict], a: float, tol_atr: float = 0.15) -> list[dict]:
    """قمم أو قيعان متساوية — تجمّع سيولة صريح."""
    out = []
    tol = a * tol_atr
    highs = [s for s in swings if s["is_high"]][-6:]
    lows = [s for s in swings if not s["is_high"]][-6:]
    for group, label, direction in ((highs, "قمم متساوية", -1),
                                    (lows, "قيعان متساوية", 1)):
        for i in range(1, len(group)):
            if abs(group[i]["price"] - group[i - 1]["price"]) <= tol:
                out.append({"price": float((group[i]["price"] + group[i-1]["price"]) / 2),
                            "kind": label, "direction": direction,
                            "index": group[i]["index"]})
    return out


def _order_blocks(df: pd.DataFrame, events: list[dict], a: float,
                  min_impulse: float = 1.2, max_zones: int = 2) -> list[Zone]:
    """آخر شمعة معاكسة قبل حركة اندفاعية كسرت الهيكل."""
    zones: list[Zone] = []
    o, c = df["open"].to_numpy(), df["close"].to_numpy()
    h, l = df["high"].to_numpy(), df["low"].to_numpy()

    for ev in reversed(events[-6:]):
        idx = ev["index"]
        if idx >= len(df):
            continue
        bullish_move = ev["direction"] == 1
        found = None
        for j in range(idx, max(0, idx - 25), -1):
            is_down = c[j] < o[j]
            if (bullish_move and is_down) or (not bullish_move and not is_down):
                found = j
                break
        if found is None:
            continue

        impulse = abs(c[idx] - c[found])
        if impulse < a * min_impulse:
            continue

        zones.append(Zone(
            kind="demand" if bullish_move else "supply",
            arabic="منطقة طلب" if bullish_move else "منطقة عرض",
            top=float(max(h[found], o[found], c[found])),
            bottom=float(min(l[found], o[found], c[found])),
            index=int(found),
            strength=float(impulse / a),
        ))
        if len(zones) >= max_zones:
            break
    return zones


def _fair_value_gaps(df: pd.DataFrame, a: float, min_size: float = 0.5,
                     max_gaps: int = 2) -> list[Zone]:
    """فجوة بين ظل الشمعة الأولى والثالثة — عدم توازن يميل السعر لملئه."""
    zones: list[Zone] = []
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)

    for i in range(n - 3, max(1, n - 120), -1):
        up_gap = l[i + 1] - h[i - 1] if i + 1 < n else -1
        down_gap = l[i - 1] - h[i + 1] if i + 1 < n else -1
        if up_gap > a * min_size and c[-1] > l[i + 1]:
            zones.append(Zone("fvg_bull", "فجوة صاعدة", float(l[i + 1]),
                              float(h[i - 1]), int(i), float(up_gap / a)))
        elif down_gap > a * min_size and c[-1] < h[i + 1]:
            zones.append(Zone("fvg_bear", "فجوة هابطة", float(l[i - 1]),
                              float(h[i + 1]), int(i), float(down_gap / a)))
        if len(zones) >= max_gaps:
            break
    return zones


def analyze(df: pd.DataFrame, structure: Structure, atr_len: int = 14) -> PriceAction:
    a = float(atr(df, atr_len).iloc[-1])
    close = float(df["close"].iloc[-1])
    pa = PriceAction()
    if not np.isfinite(a) or a <= 0 or len(structure.pivots) < 4:
        return pa

    swings = _label_swings(structure.pivots)
    pa.trend = _trend_from_swings(swings)
    pa.structure_events = _structure_events(swings, pa.trend)
    pa.sweeps = _liquidity_sweeps(df, swings, a)
    pa.equal_levels = _equal_levels(swings, a)
    pa.zones = _order_blocks(df, pa.structure_events, a) + _fair_value_gaps(df, a)

    # موقع السعر من الموجة: الخصم أفضل للشراء
    hi, lo = structure.structure_high, structure.structure_low
    if hi > lo:
        mid = (hi + lo) / 2
        pa.premium_discount = "خصم" if close < mid else "علاوة"

    # ── التقييم ──
    votes = 0
    if pa.trend == "صاعد":
        votes += 1
        pa.notes.append("هيكل صاعد: قمم وقيعان أعلى")
    elif pa.trend == "هابط":
        votes -= 1
        pa.notes.append("هيكل هابط: قمم وقيعان أدنى")

    if pa.structure_events:
        last = pa.structure_events[-1]
        votes += 1 if last["direction"] == 1 else -1
        pa.notes.append(f"آخر حدث هيكلي: {last['kind']}")

    recent_sweeps = [s for s in pa.sweeps if s["index"] >= len(df) - 20]
    for sw in recent_sweeps:
        votes += sw["direction"]
        pa.notes.append(sw["kind"] + " حديث")

    tol = a * 0.4
    for z in pa.zones:
        if z.contains(close, tol):
            if z.kind in ("demand", "fvg_bull"):
                votes += 1
                pa.notes.append(f"السعر داخل {z.arabic}")
            else:
                votes -= 1
                pa.notes.append(f"السعر داخل {z.arabic}")

    if pa.premium_discount == "خصم":
        votes += 1
    elif pa.premium_discount == "علاوة":
        votes -= 1

    pa.score = 1 if votes >= 2 else -1 if votes <= -2 else 0
    return pa
