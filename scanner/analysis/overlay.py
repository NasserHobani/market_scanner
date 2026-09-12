"""تحويل التحليل إلى إحداثيات قابلة للرسم.

الشارت المدمج من TradingView لا يقبل رسماً برمجياً، فنرسم شارتنا
بمكتبة lightweight-charts ونضع عليها ما حسبناه: الموجات، فيبوناتشي،
القناة، أعناق النماذج، مستويات التوصية، وعلامات الشموع.

كل الإحداثيات بالثواني (توقيت يونكس) لأن المكتبة تتوقعها هكذا.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import MarketConfig
from ..indicators.pine import atr
from ..indicators.structure import build_structure, detect_channel, fib_levels
from . import candles as candle_mod
from . import elliott as elliott_mod
from . import patterns as pattern_mod
from . import price_action as pa_mod

WAVE_LABELS = ["0", "1", "2", "3", "4", "5"]


def _ts(index: pd.DatetimeIndex, i: int) -> int:
    i = max(0, min(int(i), len(index) - 1))
    return int(index[i].timestamp())


def build(df: pd.DataFrame, cfg: MarketConfig, max_bars: int = 400,
          reco: dict | None = None, max_markers: int = 8,
          marker_bars: int = 60, strong_only: bool = True,
          show_all_fib: bool = False) -> dict:
    """يعيد كل ما يلزم لرسم الشارت والتحليل فوقه."""
    p = cfg.params
    full = df
    idx = full.index
    a = float(atr(full, p.atr_len).iloc[-1])
    close = float(full["close"].iloc[-1])
    last_i = len(full) - 1

    # نحسب الهيكل والعدّ أولاً، لأن نافذة العرض قد تحتاج التوسّع
    # لتشمل بداية الموجة — وإلا رُسم جزء منها خارج الشاشة
    structure = None
    wave = None
    if np.isfinite(a) and a > 0:
        structure = build_structure(full, p.zigzag_len, p.min_swing_atr, p.atr_len)
        wave = elliott_mod.count(structure, close)

    bars = max_bars
    if wave is not None and wave.bar_indices:
        needed = last_i - min(wave.bar_indices) + 20
        bars = min(len(full), max(max_bars, needed))

    view = full.tail(bars)
    first_visible = len(full) - len(view)

    out: dict = {
        "candles": [
            {"time": int(t.timestamp()), "open": float(o), "high": float(h),
             "low": float(l), "close": float(c)}
            for t, o, h, l, c in zip(view.index, view["open"], view["high"],
                                     view["low"], view["close"])
        ],
        "volume": [
            {"time": int(t.timestamp()), "value": float(v),
             "color": "rgba(61,220,151,.35)" if c >= o else "rgba(255,107,107,.35)"}
            for t, v, o, c in zip(view.index, view["volume"], view["open"], view["close"])
        ],
        "lines": [], "markers": [], "waves": None, "levels": [],
        "meta": {"atr": a, "close": close, "bars": len(view),
                 "extended": bars > max_bars},
    }

    if structure is None:
        return out

    # ── الزيجزاج: العمود الفقري لكل ما بعده ──
    zig = [{"time": _ts(idx, pt.index), "value": float(pt.price)}
           for pt in structure.pivots if pt.index >= first_visible]
    if len(zig) >= 2:
        out["lines"].append({
            "id": "zigzag", "layer": "structure", "title": "هيكل السوق", "color": "#8b93a7",
            "width": 1, "style": "dotted", "points": zig,
        })

    # ── موجات إليوت ──
    if wave is not None and wave.bar_indices:
        # نرسم النقاط التي عُدّت فعلاً، لا آخر ست نقاط.
        # الخلط بينهما يرسم أرقاماً على شكل يخالف القواعد المتحقَّق منها.
        wave_points, labels = [], []
        for n, (bar_i, price, is_high) in enumerate(
                zip(wave.bar_indices, wave.waves, wave.is_high)):
            wave_points.append({"time": _ts(idx, bar_i), "value": float(price)})
            labels.append({
                "time": _ts(idx, bar_i), "price": float(price),
                "text": WAVE_LABELS[n],
                # aboveBar/belowBar تدفع النقطة خارج الشمعة، فتبدو القمم
                # أعلى والقيعان أدنى مما هي — ويظهر تداخل وهمي بين 4 و1
                "position": "inBar",
                "side": "high" if is_high else "low",
                "color": "#c9a227",
            })
        # هامش القاعدة الثالثة: كم تبعد النقطة 4 عن نطاق الموجة الأولى.
        # رقم صغير يعني عدّاً صحيحاً لكنه على حافة الإبطال — وهو ما يجعل
        # الرسم يبدو مخالفاً للعين وهو سليم حسابياً.
        p0v, p1v, p4v = wave.waves[0], wave.waves[1], wave.waves[4]
        span = abs(p0v - p1v)
        margin = abs(p4v - p1v) / span * 100 if span else 0.0

        out["waves"] = {
            "points": wave_points, "labels": labels,
            "label": wave.label, "confidence": wave.confidence,
            "notes": wave.notes, "invalidation": wave.invalidation,
            "next_target": wave.next_target,
            "offset": wave.offset,
            "rule3_margin": round(margin, 1),
            "p1": float(p1v), "p4": float(p4v),
        }
        out["lines"].append({
            "id": "elliott", "layer": "waves", "title": "موجات إليوت", "color": "#c9a227",
            "width": 2, "style": "solid", "points": wave_points,
        })
        if wave.invalidation:
            out["levels"].append({
                "price": float(wave.invalidation), "layer": "waves", "title": "إلغاء العدّ",
                "color": "#c9a227", "style": "dashed",
            })

    # ── فيبوناتشي من الموجة الهيكلية ──
    if structure.structure_high > structure.structure_low:
        for ratio, price in fib_levels(structure.structure_high,
                                       structure.structure_low).items():
            key = ratio in (0.382, 0.5, 0.618)
            if not key and not show_all_fib:
                continue          # الثانوية تزيد الخطوط بلا فائدة تُذكر
            out["levels"].append({
                "price": float(price), "layer": "fib",
                "title": f"{ratio * 100:.1f}%".replace(".0", ""),
                "color": "#e0b341" if key else "rgba(224,179,65,.35)",
                "style": "dotted",
            })

    # ── القناة السعرية ──
    channel = detect_channel(full, structure, a, flat_atr=p.ch_flat_atr,
                             tol_atr=p.ch_tol_atr, min_bars=p.ch_min_bars,
                             min_touches=p.ch_min_touches, min_contain=p.ch_min_contain)
    if channel is not None:
        left = max(channel.anchor_index, first_visible)
        color = {"rising": "#3ddc97", "falling": "#ff6b6b"}.get(channel.kind, "#7e57c2")
        for name, offset in (("قاع القناة", 0.0), ("سقف القناة", 1.0)):
            lo_l, up_l = channel.bounds_at(left)
            lo_r, up_r = channel.bounds_at(last_i)
            out["lines"].append({
                "id": f"channel-{name}", "layer": "channel", "title": name, "color": color,
                "width": 2, "style": "solid",
                "points": [
                    {"time": _ts(idx, left), "value": lo_l + (up_l - lo_l) * offset},
                    {"time": _ts(idx, last_i), "value": lo_r + (up_r - lo_r) * offset},
                ],
            })
        mid_l, mid_r = channel.bounds_at(left)[0], channel.bounds_at(last_i)[0]
        out["lines"].append({
            "id": "channel-mid", "layer": "channel", "title": "خط الوسط", "color": color,
            "width": 1, "style": "dashed",
            "points": [
                {"time": _ts(idx, left), "value": mid_l + channel.height / 2},
                {"time": _ts(idx, last_i), "value": mid_r + channel.height / 2},
            ],
        })

    # ── النماذج السعرية: خط العنق والهدف ──
    for pat in pattern_mod.detect(structure, full, a)[:2]:
        col = "#3ddc97" if pat.direction == 1 else "#ff6b6b" if pat.direction == -1 else "#7e57c2"
        if pat.neckline:
            out["levels"].append({
                "price": float(pat.neckline), "layer": "patterns", "title": f"عنق {pat.arabic}",
                "color": col, "style": "dashed",
            })
        if pat.target:
            out["levels"].append({
                "price": float(pat.target), "layer": "patterns", "title": f"هدف {pat.arabic}",
                "color": col, "style": "dotted",
            })

    # ── علامات نماذج الشموع ──
    # الإفراط هنا يقتل الفائدة: 14 نموذجاً × عدة إصابات = عشرات الملصقات
    # فوق بعضها فلا يُقرأ السعر ولا العلامات. القواعد:
    #   • النافذة الأخيرة فقط — النموذج القديم لا يفيد قراراً اليوم
    #   • علامة واحدة لكل شمعة، الأقوى تفوز
    #   • النص لأحدث ثلاث علامات فقط، والباقي أسهم صامتة
    STRONG = {"bull_engulfing", "bear_engulfing", "morning_star", "evening_star",
              "hammer", "shooting_star", "piercing", "dark_cloud"}
    PRIORITY = {name: i for i, name in enumerate(
        ["morning_star", "evening_star", "bull_engulfing", "bear_engulfing",
         "hammer", "shooting_star", "piercing", "dark_cloud",
         "tweezer_bottom", "tweezer_top", "bull_harami", "bear_harami",
         "marubozu_bull", "marubozu_bear"])}

    flags = candle_mod.detect(full, atr_len=p.atr_len)
    window = flags.tail(min(len(view), marker_bars))

    per_bar: dict = {}
    for col in flags.columns:
        if col == "doji" or col not in PRIORITY:
            continue
        if strong_only and col not in STRONG:
            continue
        for t in window.index[window[col]]:
            rank = PRIORITY[col]
            if t not in per_bar or rank < per_bar[t][0]:
                per_bar[t] = (rank, col)

    chosen = sorted(per_bar.items())[-max_markers:]
    for n, (t, (_, col)) in enumerate(chosen):
        bullish = col in candle_mod.BULLISH
        show_text = n >= len(chosen) - 3          # النص لأحدث ثلاث فقط
        out["markers"].append({
            "time": int(t.timestamp()),
            "position": "belowBar" if bullish else "aboveBar",
            "color": "#3ddc97" if bullish else "#ff6b6b",
            "shape": "arrowUp" if bullish else "arrowDown",
            "layer": "candles",
            "text": candle_mod.ARABIC.get(col, col) if show_text else "",
            "full_text": candle_mod.ARABIC.get(col, col),
        })

    # ── حركة السعر: مناطق وأحداث وسيولة ──
    action = pa_mod.analyze(full, structure, p.atr_len)
    out["price_action"] = action.as_dict()

    for z in action.zones:
        col = "#3ddc97" if z.kind in ("demand", "fvg_bull") else "#ff6b6b"
        out["levels"].append({
            "price": float(z.top), "layer": "pa",
            "title": f"{z.arabic} ↑", "color": col, "style": "dashed",
        })
        out["levels"].append({
            "price": float(z.bottom), "layer": "pa",
            "title": f"{z.arabic} ↓", "color": col, "style": "dashed",
        })

    for lvl in action.equal_levels[-2:]:
        out["levels"].append({
            "price": float(lvl["price"]), "layer": "pa",
            "title": lvl["kind"], "color": "#d16bd1", "style": "dotted",
        })

    for ev in action.structure_events[-3:]:
        if ev["index"] < first_visible:
            continue
        out["markers"].append({
            "time": _ts(idx, ev["index"]), "layer": "pa",
            "position": "aboveBar" if ev["direction"] == -1 else "belowBar",
            "color": "#6aa9ff", "shape": "square", "text": ev["kind"],
            "full_text": ev["kind"],
        })

    for sw in action.sweeps[-3:]:
        if sw["index"] < first_visible:
            continue
        out["markers"].append({
            "time": _ts(idx, sw["index"]), "layer": "pa",
            "position": "belowBar" if sw["direction"] == 1 else "aboveBar",
            "color": "#d16bd1", "shape": "circle", "text": "سيولة",
            "full_text": sw["kind"],
        })

    # ── مستويات التوصية ──
    if reco and reco.get("entry"):
        out["levels"].append({"price": float(reco["entry"]), "layer": "trade", "title": "الدخول",
                              "color": "#6aa9ff", "style": "solid"})
        if reco.get("stop"):
            out["levels"].append({"price": float(reco["stop"]), "layer": "trade", "title": "الوقف",
                                  "color": "#ff6b6b", "style": "solid"})
        for n, t in enumerate(reco.get("targets") or [], 1):
            out["levels"].append({"price": float(t), "layer": "trade", "title": f"هدف {n}",
                                  "color": "#3ddc97", "style": "dashed"})

    out["markers"].sort(key=lambda m: m["time"])
    return out
