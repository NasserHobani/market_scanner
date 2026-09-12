# -*- coding: utf-8 -*-
"""هل يفرّق ‏StochRSI و MACD بين صفقةٍ رابحة وخاسرة؟ — قياسٌ لا رأي.

    python tools_osc_measure.py
    python tools_osc_measure.py --market crypto --min 25

═══ لماذا هذه الأداة قبل أيّ استعمالٍ للمؤشّرين ═══

المؤشّران معروضان في شاشة الرمز، وخارج التقييم عمداً. والسبب
مقيس: من ٢١ سبباً تُصدره الاستراتيجية اختُبرت كلّها على صفقاتك
المحسومة، فبدا ٦ منها ذا دلالةٍ فردية — ولم ينجُ **ولا واحد** من
تصحيح بنياميني–هوخبرغ.

فالسؤال هنا ليس «هل المؤشّر جيّد؟» بل «هل حالته **عند الدخول**
تفرّق بين ما ربح وما خسر في صفقاتك أنت؟».

═══ وكيف يُمنع النظر إلى المستقبل ═══

لكل صفقة تُقرأ الشموع **حتى شمعة الإشارة فقط** ثمّ يُحسب
المؤشّر. وحسابُه على السلسلة كاملة ثمّ أخذ القيمة عند ذلك التاريخ
يعطي الرقم نفسه هنا (المؤشّران سببيّان)، لكنّ القصّ يجعل الضمان
بنيوياً لا اعتماداً على خاصّيةٍ قد تتغيّر.

وتُسقَط الشمعة الأخيرة قبل الحساب: القرار على المغلق وحده.

═══ وما يُطبع ═══

نسبة الفوز في كل حالة مع فترة ثقة ‏Wilson، ثمّ اختبارٌ ثنائي دقيق
مقابل نسبة الفوز العامّة. والفترة المتداخلة مع الأساس تعني «لا
فرق مقيس» — وهذه نتيجةٌ لا فشل.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("AUTO_SCAN", "0")
os.environ.setdefault("SCHEDULER_ENGINE", "off")


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """فترة ثقة للنسبة.

    ‏Wilson لا ‏Wald: عند ٥ صفقات ونسبة ١٠٠٪ تعطي Wald فترةً
    عرضها صفر — «يقينٌ» من خمس ملاحظات.
    """
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def binom_p(wins: int, n: int, p0: float) -> float:
    """اختبار ثنائي دقيق، ذو طرفين — بلا scipy."""
    if n == 0:
        return 1.0
    from math import comb

    def pmf(k):
        return comb(n, k) * (p0 ** k) * ((1 - p0) ** (n - k))

    obs = pmf(wins)
    return min(1.0, sum(pmf(k) for k in range(n + 1)
                        if pmf(k) <= obs + 1e-12))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", default="", help="سوق واحد بدل الكلّ")
    ap.add_argument("--min", type=int, default=20,
                    help="أقلّ عدد صفقات لعرض حالة (افتراضي ٢٠)")
    args = ap.parse_args()

    import django

    django.setup()

    import pandas as pd

    from dashboard.models import Trade
    from scanner import storage
    from scanner.indicators.momentum import macd_state, stoch_rsi, stoch_rsi_state
    from scanner.indicators.trend import macd

    qs = Trade.objects.filter(status__in=("won", "lost"))
    if args.market:
        qs = qs.filter(market=args.market)
    trades = list(qs.values("symbol", "market", "timeframe", "candle_time",
                            "status", "r_multiple"))

    print(f"الصفقات المحسومة: {len(trades)}")
    if not trades:
        print("لا شيء يُقاس.")
        return 0

    # ═══ الشموع تُحمَّل مرّة لكل (رمز، فريم) ═══
    #
    # صفقات كثيرة تتشارك الرمز والفريم، وتحميلُها لكل صفقة يقرأ
    # الملفّ نفسه مئات المرّات.
    cache: dict[tuple, object] = {}

    def candles(market, symbol, tf):
        key = (market, symbol, tf)
        if key not in cache:
            try:
                cache[key] = storage.load(market, symbol, tf)
            except Exception:  # noqa: BLE001
                cache[key] = None
        return cache[key]

    buckets: dict[str, dict[str, list]] = defaultdict(
        lambda: defaultdict(list))
    skipped = defaultdict(int)

    for t in trades:
        df = candles(t["market"], t["symbol"], t["timeframe"])
        if df is None or len(df) < 60:
            skipped["لا شموع"] += 1
            continue

        # ═══ القصّ عند شمعة الإشارة ═══
        #
        # ``<=`` ثمّ إسقاط الأخيرة: شمعة الإشارة نفسها كانت جارية
        # لحظة القرار.
        ct = t["candle_time"]
        if ct is None:
            skipped["بلا وقت شمعة"] += 1
            continue
        try:
            past = df[df.index <= pd.Timestamp(ct).tz_convert(df.index.tz)]
        except (TypeError, ValueError):
            past = df[df.index <= pd.Timestamp(ct)]
        if len(past) < 40:
            skipped["تاريخ قصير"] += 1
            continue

        won = t["status"] == "won"
        r = t.get("r_multiple")

        s = stoch_rsi_state(stoch_rsi(past["close"]))
        m = macd_state(macd(past["close"]))

        if s.get("k") is not None:
            buckets["StochRSI · المنطقة"][{
                "overbought": "تشبّع شرائي (≥80)",
                "oversold": "تشبّع بيعي (≤20)",
                "middle": "المنطقة الوسطى",
            }.get(s["zone"], s["zone"])].append((won, r))
            buckets["StochRSI · التقاطع"][{
                "up": "تقاطع صعودي", "down": "تقاطع هبوطي",
                "none": "بلا تقاطع",
            }[s["cross"]]].append((won, r))
        else:
            skipped["StochRSI غير محسوب"] += 1

        if m.get("hist") is not None:
            buckets["MACD · جانب الصفر"][
                "فوق الصفر" if m["macd"] > 0 else "تحت الصفر"].append((won, r))
            buckets["MACD · المدرّج"][
                "موجب" if m["hist"] > 0 else "سالب"].append((won, r))
            buckets["MACD · التقاطع"][{
                "up": "تقاطع صعودي", "down": "تقاطع هبوطي",
                "none": "بلا تقاطع",
            }[m["cross"]]].append((won, r))
        else:
            skipped["MACD غير محسوب"] += 1

    total = [x for g in buckets.values() for v in g.values() for x in v]
    if not total:
        print("\n✗ لم تُقَس صفقةٌ واحدة.")
        for k, v in skipped.items():
            print(f"   {k}: {v}")
        return 1

    # الأساس من الصفقات المقيسة نفسها لا من كل الصفقات — وإلّا
    # قُورن مجتمعٌ بمجتمعٍ آخر
    measured = buckets["MACD · جانب الصفر"]
    base_rows = [x for v in measured.values() for x in v]
    base_n = len(base_rows)
    base_w = sum(1 for w, _ in base_rows if w)
    base_p = base_w / base_n if base_n else 0.0

    print(f"المقيسة: {base_n} · نسبة الفوز الأساس: {base_p*100:.1f}٪")
    if skipped:
        print("المتخطّاة: " + " · ".join(f"{k} {v}" for k, v in skipped.items()))

    pvals: list[tuple[float, str]] = []

    for group, states in buckets.items():
        print(f"\n═══ {group} ═══")
        print(f"{'الحالة':<22}{'ن':>6}{'فوز':>8}"
              f"{'فترة الثقة':>18}{'وسيط R':>9}   الحكم")
        print("─" * 76)
        for name, rows in sorted(states.items(),
                                 key=lambda kv: -len(kv[1])):
            n = len(rows)
            w = sum(1 for won, _ in rows if won)
            lo, hi = wilson(w, n)
            rs = sorted(r for _, r in rows if r is not None)
            # الوسيط لا المتوسّط: توزيع R ملتوٍ، وصفقةٌ بـ ‎+8R‎
            # ترفع المتوسّط فيبدو المؤشّر رابحاً وأغلب صفقاته خاسرة
            med = rs[len(rs) // 2] if rs else None
            if n < args.min:
                verdict = f"عيّنة صغيرة (<{args.min})"
            elif lo > base_p:
                verdict = "أعلى من الأساس"
            elif hi < base_p:
                verdict = "أدنى من الأساس"
            else:
                verdict = "لا فرق مقيس"
            if n >= args.min:
                pvals.append((binom_p(w, n, base_p), f"{group} → {name}"))
            print(f"{name:<22}{n:>6}{w/n*100:>7.1f}٪"
                  f"{lo*100:>8.0f}–{hi*100:<8.0f}"
                  f"{(f'{med:+.2f}' if med is not None else '—'):>9}   {verdict}")

    # ═══ تصحيح الاختبارات المتعدّدة ═══
    #
    # اختبرنا ١٣ حالة. وعند ‎α=0.05‎ تُنتج الصدفة وحدها نتيجةً
    # «ذات دلالة» كل عشرين اختباراً. فبلا تصحيحٍ يُكتشف «مؤشّر
    # ناجح» في كل جولة.
    print("\n═══ بعد تصحيح بنياميني–هوخبرغ (α=0.05) ═══")
    if not pvals:
        print("لا حالة بلغت الحدّ الأدنى للعيّنة.")
        return 0
    pvals.sort()
    m_tests = len(pvals)
    survivors = []
    for rank, (p, label) in enumerate(pvals, 1):
        if p <= 0.05 * rank / m_tests:
            survivors = [lbl for _, lbl in pvals[:rank]]
    for p, label in pvals[:6]:
        mark = "✓" if label in survivors else "·"
        print(f" {mark} {label:<46} p={p:.4f}")
    print()
    if survivors:
        print(f"نجا {len(survivors)} من {m_tests}: "
              + " · ".join(survivors))
        print("\nهذه وحدها تصلح أساساً لإدخال المؤشّر في التقييم.")
    else:
        print(f"لم تنجُ حالةٌ من {m_tests}.")
        print("\nأي أنّ المؤشّرين — بهذه البيانات — لا يفرّقان بين")
        print("الرابح والخاسر بفارقٍ يتجاوز الصدفة. ويبقيان عرضاً.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
