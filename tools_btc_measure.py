# -*- coding: utf-8 -*-
"""هل التموضع المزدحم يسبق أداءً أسوأ فعلاً؟ — بالقياس لا بالمعقولية.

    python tools_btc_measure.py [--symbol BTCUSDT] [--tf 4h] [--horizon 12]

═══ لماذا هذه الأداة قبل أيّ ربطٍ بالدرجة ═══

قراءةُ التموضع **معقولة**: رافعةٌ مكلفة تُصفّى، والتصفية تضخّم
الهبوط. والمعقول ليس مقيساً. وكلّ ما دخل درجة هذه المنصّة دخلها
بعد قياس، وهذه ليست استثناءً.

═══ ما يُقاس بالضبط ═══

عند كل دفعة تمويل: ما مئينها بين الدفعات **السابقة لها وحدها**؟
ثمّ ما عائد البيتكوين بعدها بأفقٍ محدَّد؟

ويُقارَن العشير الأعلى بالباقي: بمعدّل العائد، وبنسبة المرّات
التي كان فيها موجباً، وبفاصل ثقة ويلسون، واختبار دلالة.

═══ ولا نظرَ إلى المستقبل ═══

ثلاثة مواضع يتسرّب منها المستقبل، وكلّها مسدودة هنا:

    ١. المئين من السابق فقط — لا من السلسلة كاملة
    ٢. الدخول عند إغلاق أوّل شمعة **بعد** وقت الدفعة، لا عندها
    ٣. الأفق يبدأ من ذلك الإغلاق

والأوّل هو الأخطر: مئينٌ محسوبٌ على السلسلة كلّها يعرف مستقبل
كل نقطة، فيُنتج نتيجةً ممتازة لا تتكرّر مرّةً واحدة في التطبيق.

═══ وحدُّ البيانات ═══

المراكز المفتوحة **ثلاثون يوماً فقط** على Binance. فلا تُقاس هنا:
عيّنةٌ بهذا القصر تعطي رقماً يبدو نتيجةً وهو ضجيج. والمقيس هو
التمويل وحده، وتاريخه طويل.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

#: أقلّ سابقةٍ يُبنى عليها مئين
WARMUP = 90
#: عشير الازدحام
HOT_PCTILE = 90.0


def wilson(k: int, n: int) -> tuple[float, float, float]:
    if not n:
        return (0.0, 0.0, 0.0)
    z = 1.959963985
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * max(0.0, c - h), 1),
            round(100 * min(1.0, c + h), 1))


def welch(a: list[float], b: list[float]) -> tuple[float, float]:
    """‏t ودرجات حرّية تقريبية — بلا scipy.

    و‏Welch لا Student: التبايُن في العشير المزدحم أكبر بطبيعته،
    وافتراض تساويهما يضخّم الدلالة.
    """
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return (0.0, 0.0)
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return (0.0, 0.0)
    t = (ma - mb) / se
    num = (va / na + vb / nb) ** 2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    return (t, num / den if den else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--horizon", type=int, default=12,
                    help="عدد الشموع بعد الدخول")
    ap.add_argument("--market", default="crypto")
    args = ap.parse_args()

    from scanner import storage
    from scanner.adapters import binance_futures as bf

    df = storage.load(args.market, args.symbol, args.tf)
    if df is None or len(df) < 200:
        print(f"✗ شموع غير كافية لـ {args.symbol} {args.tf} — "
              f"{0 if df is None else len(df)}")
        return 1

    fund = bf.funding_history(args.symbol, limit=1000)
    if len(fund) < WARMUP + 30:
        print(f"✗ سجلّ التمويل قصير: {len(fund)} دفعة — "
              f"يلزم {WARMUP + 30} على الأقلّ")
        return 1

    # ═══ مواءمة الأزمنة ═══
    #
    # شموع القرص بفهرسٍ زمنيّ، والدفعات بميلي ثانية. والدخول عند
    # إغلاق أوّل شمعة **بعد** الدفعة: الدخول عندها يعني معرفة
    # سعرٍ لم يُغلق بعد.
    import numpy as np
    import pandas as pd

    idx = pd.to_datetime(df.index, utc=True)
    close = df["close"].astype(float).to_numpy()

    hot: list[float] = []
    rest: list[float] = []
    rows: list[tuple] = []

    for i in range(WARMUP, len(fund)):
        prior = [f["rate"] for f in fund[:i]]
        now = fund[i]["rate"]
        below = sum(1 for v in prior if v < now)
        pct = below / len(prior) * 100.0

        when = pd.to_datetime(fund[i]["time"], unit="ms", utc=True)
        pos = int(np.searchsorted(idx.values, when.to_datetime64(), "right"))
        # ‏pos هو أوّل شمعة بعد الدفعة؛ ونحتاج أفقاً كاملاً بعدها
        if pos <= 0 or pos + args.horizon >= len(close):
            continue
        entry = close[pos]
        exit_ = close[pos + args.horizon]
        if entry <= 0:
            continue
        ret = (exit_ - entry) / entry * 100.0

        (hot if pct >= HOT_PCTILE else rest).append(ret)
        rows.append((when.date().isoformat(), round(pct, 1),
                     round(now * 100, 4), round(ret, 2)))

    if len(hot) < 20:
        print(f"✗ العشير المزدحم فيه {len(hot)} حالة فقط — "
              "أقصر من أن يُقاس")
        return 1

    def block(name: str, xs: list[float]) -> None:
        n = len(xs)
        k = sum(1 for x in xs if x > 0)
        p, lo, hi = wilson(k, n)
        mean = sum(xs) / n
        med = sorted(xs)[n // 2]
        worst = min(xs)
        print(f"  {name:<22} n={n:<5} موجب {p:>5}% "
              f"[{lo}–{hi}]  متوسّط {mean:+.2f}%  وسيط {med:+.2f}%  "
              f"أسوأ {worst:+.2f}%")

    print(__doc__.strip().splitlines()[0])
    print()
    print(f"الرمز {args.symbol} · الفريم {args.tf} · "
          f"الأفق {args.horizon} شمعة · الدفعات {len(fund)}")
    print(f"نافذة التمويل: {rows[0][0]} ← {rows[-1][0]}")
    print()
    block(f"التمويل ≥ مئين {HOT_PCTILE:g}", hot)
    block("الباقي", rest)

    t, dof = welch(hot, rest)
    diff = (sum(hot) / len(hot)) - (sum(rest) / len(rest))
    print()
    print(f"  الفارق في المتوسّط: {diff:+.2f}%   t={t:+.2f}  dof≈{dof:.0f}")

    # ═══ والحكم يُقال صراحةً ═══
    #
    # «الفارق سالب» وحدها تُقرأ نجاحاً. والسؤال هو: أكبر من
    # الضجيج أم لا؟ و|t| < 2 تقريباً = لا.
    if abs(t) < 2.0:
        print("  ⇒ الفارق داخل الضجيج. لا يُربط بالدرجة.")
        verdict = 0
    elif diff < 0:
        print("  ⇒ الازدحام يسبق أداءً أسوأ بفارقٍ يتجاوز الضجيج.")
        print("     يصلح **خافضَ ثقة** — لا مانعاً مطلقاً.")
        verdict = 1
    else:
        print("  ⇒ الازدحام يسبق أداءً **أفضل** — عكس المتوقَّع.")
        print("     لا يُربط بالدرجة بأيّ إشارة حتى يُفهم السبب.")
        verdict = 2

    print()
    print("ملاحظة: المراكز المفتوحة لم تُقَس — سجلّها "
          f"{bf.OI_HISTORY_DAYS} يوماً فقط، وهو أقصر من أن يُعطي نتيجة.")
    print("وعيّنةٌ واحدة على رمزٍ واحد ليست دليلاً عامّاً: هذا قياسٌ "
          "على البيتكوين وحده.")
    return 0 if verdict != 2 else 0


if __name__ == "__main__":
    raise SystemExit(main())
