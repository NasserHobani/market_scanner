# -*- coding: utf-8 -*-
"""هل نقاط PES الأعلى تسبق تمدّداً أكثر؟ — بالقياس لا بالثقة.

    python tools_pes_measure.py [crypto] [--limit 60]

يمرّ على التاريخ: يحسب النقاط عند كل شمعة مغلقة، ثمّ ينظر إلى ما
بعدها. ويقارن شرائح النقاط بمعدّل الأساس.

استراتيجيةٌ لا تتجاوز الأساس ليست استراتيجية — وأفضل وقتٍ لمعرفة
ذلك قبل بناء القرارات عليها.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# أفق التمدّد بالشموع (4H) والحدّ بمضاعف ATR
HORIZON = 12
EXPANSION_ATR = 3.0
# شرائح النقاط
BUCKETS = [(0, 40), (40, 55), (55, 65), (65, 75), (75, 101)]


def wilson(k: int, n: int) -> tuple[float, float, float]:
    if not n:
        return (0.0, 0.0, 0.0)
    z = 1.959963985
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * max(0, c - h)),
            round(100 * min(1, c + h)))


def main() -> int:
    import numpy as np

    from scanner import storage
    from scanner.indicators.pine import atr
    from scanner.strategies import pes

    # ‏argparse لا حلقةٌ يدوية: نسختي الأولى قرأت «12» سوقاً
    # فمسحت صفر رمز وطبعت جدولاً فارغاً بلا خطأ.
    import argparse

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("market", nargs="?", default="crypto")
    ap.add_argument("--limit", type=int, default=60)
    # ═══ التمدّد ليس صعوداً ═══
    #
    # ‏PES استراتيجية شراء. وقياس «تمدّد في أيّ اتجاه» يخلط
    # الانفجار لصالحك بالانفجار ضدّك — والرقم يبدو ممتازاً وهو
    # يشمل ما يقتل الصفقة.
    ap.add_argument("--up", action="store_true",
                    help="التمدّد صعوداً فقط")
    args = ap.parse_args()
    market, limit = args.market, args.limit

    params = pes.load_params()
    btc = None
    try:
        btc = pes.btc_regime(storage.load("crypto", "BTCUSDT", "1d"))
    except Exception:  # noqa: BLE001
        pass

    symbols = storage.stored_symbols(market, "4h")[:limit]
    stats = {b: [0, 0] for b in BUCKETS}      # [حالات, تمدّدات]
    base = [0, 0]
    print(f"يقيس {len(symbols)} رمزاً على {market} · أفق {HORIZON} شمعة"
          f" · تمدّد ≥ {EXPANSION_ATR}× ATR\n")

    for sym in symbols:
        try:
            h4 = storage.load(market, sym, "4h")
            d1 = storage.load(market, sym, "1d")
        except Exception:  # noqa: BLE001
            continue
        if h4 is None or d1 is None or len(h4) < 260:
            continue
        a = atr(h4, 14).to_numpy()
        high = h4["high"].astype(float).to_numpy()
        low = h4["low"].astype(float).to_numpy()

        # ═══ خطوةٌ كل ستّ شمعات ═══
        #
        # الشموع المتجاورة تتشارك النافذة نفسها تقريباً، فحسابُ
        # كلٍّ منها يضخّم العيّنة بلا معلومةٍ جديدة — ويضيّق فاصل
        # الثقة كذباً.
        for i in range(200, len(h4) - HORIZON, 6):
            av = a[i]
            if not np.isfinite(av) or av <= 0:
                continue
            hi = np.maximum.accumulate(high[i + 1: i + 1 + HORIZON])
            lo = np.minimum.accumulate(low[i + 1: i + 1 + HORIZON])
            if hi.size == 0:
                continue
            if args.up:
                # صعوداً: القمّة تتجاوز سعر القرار بالمقدار المطلوب
                # **قبل** أن يهبط بالمقدار نفسه.
                c0 = float(h4["close"].iloc[i])
                up_hit = np.argmax(hi >= c0 + EXPANSION_ATR * av) \
                    if (hi >= c0 + EXPANSION_ATR * av).any() else -1
                dn_hit = np.argmax(lo <= c0 - EXPANSION_ATR * av) \
                    if (lo <= c0 - EXPANSION_ATR * av).any() else -1
                hit = up_hit >= 0 and (dn_hit < 0 or up_hit <= dn_hit)
            else:
                hit = bool(((hi - lo) >= EXPANSION_ATR * av).any())
            base[0] += 1
            base[1] += int(hit)

            # التقييم على الشموع حتى ‏i فقط — لا نظر إلى الأمام
            try:
                res = pes.evaluate({"4h": h4.iloc[: i + 1],
                                    "1d": d1}, btc=btc, params=params)
            except Exception:  # noqa: BLE001
                continue
            sc = res["score"]
            for b in BUCKETS:
                if b[0] <= sc < b[1]:
                    stats[b][0] += 1
                    stats[b][1] += int(hit)
                    break

    bp, blo, bhi = wilson(base[1], base[0])
    print(f"{'شريحة النقاط':<16}{'حالات':>8}{'تمدّد':>8}{'النسبة':>10}"
          f"{'الفاصل':>14}{'مقابل الأساس':>14}")
    print("─" * 72)
    for b in BUCKETS:
        n, k = stats[b]
        if not n:
            continue
        p, lo, hi = wilson(k, n)
        mark = "★" if lo > bhi else (" " if p >= bp else "▼")
        print(f"{f'{b[0]}–{b[1] - 1}':<16}{n:>8}{k:>8}{p:>9.1f}٪"
              f"{f'[{lo}–{hi}]':>14}{f'{p - bp:+.1f}':>12} {mark}")
    print("─" * 72)
    print(f"{'الأساس':<16}{base[0]:>8}{base[1]:>8}{bp:>9.1f}٪"
          f"{f'[{blo}–{bhi}]':>14}")
    print("\n★ يتجاوز الأساس بفاصلٍ لا يتقاطع · ▼ دونه")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
