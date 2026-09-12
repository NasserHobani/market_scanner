# -*- coding: utf-8 -*-
"""اختبارات رصد الاختراق — بلا Django ولا شبكة.

    python tests_breakout.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scanner.breakout import detect

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


def frame(n=120, base=100.0, drift=0.05, vol=1000.0):
    """سوق هادئ صاعد قليلاً — أرضية لكل الحالات."""
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    close = base + np.arange(n) * drift
    return pd.DataFrame({
        "open": close - 0.05, "high": close + 0.2, "low": close - 0.2,
        "close": close, "volume": np.full(n, vol),
    }, index=idx)


def spike(df, *, rvol=20, jump=4.0, body=0.9):
    """يستبدل الشمعة الأخيرة بشمعة اختراق مضبوطة.

    ملاحظة: المتوسط يشمل الشمعة الحالية، فمضاعف 20 على نافذة 20 يعطي
    RVOL ≈ 10 لا 20 — وهذا مقصود ومطابق لتعريف المشروع.
    """
    d = df.copy()
    i = len(d) - 1
    prev = d["close"].iloc[i - 1]
    c = prev + jump
    span = jump * 1.2
    o = c - span * body
    d.loc[d.index[i], ["open", "high", "low", "close", "volume"]] = [
        o, c + span * 0.05, min(o, prev) - span * 0.05, c, d["volume"].iloc[0] * rvol]
    return d


# ── الحالة الموجبة ──
b = detect(spike(frame()), "TESTUSDT", "1h")
check("اختراق كامل الشروط يُرصد", b is not None)
if b:
    check("الدخول عند الإغلاق", b.entry == b.close)
    check("الوقف تحت الدخول والهدف فوقه",
          b.stop < b.entry < b.target, f"{b.stop:.2f} < {b.entry:.2f} < {b.target:.2f}")
    d = b.as_dict()
    # كان هنا «R:R = 3÷1.5 = 2» — وهو ما جعل العائد ثابتاً بالتعريف
    # مهما كان الوقف. الوقف الآن يتبع شمعة الاختراق، فنسبة العائد صارت
    # نتيجة تُقاس لا رقماً مضموناً. اشتراط 2 هنا كان سيثبّت العطب.
    src = spike(frame())
    last = src.iloc[-1]
    check("الوقف ليس أضيق من قاع شمعة الاختراق",
          b.stop <= float(last["low"]),
          f"وقف {b.stop:.2f} · قاع {float(last['low']):.2f}")
    # السماحية 0.005 لا 1e-6: ‏as_dict تقرّب لخانتين، والتقريب مقصود
    # للعرض. المطلوب أن الرقم المعلَن مشتقّ من الوقف الفعلي لا مثبّت.
    check("والعائد المعلَن يطابق الوقف الفعلي",
          abs(d["rr"] - (b.target - b.entry) / (b.entry - b.stop)) <= 0.005,
          d["rr"])
    check("الأسباب مذكورة", len(b.reasons) == 3, b.reasons)

# ── العطب الذي كلّف خمس خسائر متتالية ──
# ATR14 متوسط، فشمعة تنفجر إلى عشرة أضعاف مداها يبتلعها المتوسط
# ويقسّمها على أربعة عشر، فيخرج وقف داخل مدى الشمعة نفسها.
violent = spike(frame(), jump=8.0, rvol=40)
bv = detect(violent, "V", "1h")
check("انفجار عنيف: الوقف يخرج عن مدى الشمعة", bv is not None
      and bv.stop < float(violent["low"].iloc[-1]),
      f"وقف {bv.stop:.2f} · قاع {float(violent['low'].iloc[-1]):.2f}" if bv else "")
if bv:
    old_stop = bv.close - 1.5 * bv.atr        # القاعدة القديمة
    check("وأوسع مما كانت تعطيه قاعدة ATR وحدها", bv.stop < old_stop,
          f"{bv.stop:.2f} مقابل {old_stop:.2f}")
    check("ولا يزال دون الدخول", bv.stop < bv.entry)

zero_buf = detect(spike(frame()), "Z", "1h", low_buffer=0.0)
if zero_buf:
    check("هامش صفر يضع الوقف عند القاع بالضبط أو تحته",
          zero_buf.stop <= float(spike(frame())["low"].iloc[-1]) + 1e-9)

# ── كل شرط يُسقط الرصد وحده ──
check("حجم دون العتبة ← لا رصد", detect(spike(frame(), rvol=4), "S", "1h") is None)
check("جسم صغير (فتيل اصطياد) ← لا رصد",
      detect(spike(frame(), body=0.15), "S", "1h") is None)

flat = spike(frame(), jump=-0.5)          # حجم عالٍ بلا اختراق
check("حجم عالٍ بلا اختراق قمة ← لا رصد", detect(flat, "S", "1h") is None)

# تحت EMA50: سوق هابط ثم قفزة لا تكفي لتجاوز المتوسط
down = frame(drift=-0.6)
check("اختراق تحت EMA50 ← لا رصد (لا نشتري في هبوط)",
      detect(spike(down, jump=1.0), "S", "1h") is None)

# ── حالات حدّية ──
check("بيانات قصيرة ← لا رصد", detect(frame(n=30), "S", "1h") is None)
check("None ← لا رصد", detect(None, "S", "1h") is None)
check("أعمدة ناقصة ← لا رصد",
      detect(frame().drop(columns=["volume"]), "S", "1h") is None)

zero = frame(vol=0.0)
check("حجم صفري في كل التاريخ ← لا رصد بلا قسمة على صفر",
      detect(zero, "S", "1h") is None)

flatline = frame(drift=0.0)
flatline.loc[:, ["open", "high", "low", "close"]] = 100.0
check("سعر ثابت تماماً (ATR صفر) ← لا رصد",
      detect(flatline, "S", "1h") is None)

# ── القمة تُحسب من السابق لا من الشمعة نفسها ──
d = spike(frame())
b = detect(d, "S", "1h")
check("القمة المخترَقة أقل من الإغلاق",
      b is not None and b.broke < b.close, f"{b.broke:.2f} vs {b.close:.2f}" if b else "")

# ── الشمعة الأخيرة وحدها تُفحص ──
d = spike(frame())
d = pd.concat([d, d.iloc[[-1]].assign(volume=d["volume"].iloc[0])])
d.index = pd.date_range("2026-01-01", periods=len(d), freq="h", tz="UTC")
check("اختراق قديم بشمعة أخيرة عادية ← لا رصد",
      detect(d, "S", "1h") is None)

# ── العتبات قابلة للضبط ──
soft = detect(spike(frame(), rvol=4), "S", "1h", min_rvol=3)
check("خفض عتبة الحجم يسمح بالرصد", soft is not None)

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
