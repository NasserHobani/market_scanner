# -*- coding: utf-8 -*-
"""هل «راكب التشبّع» يربح فعلاً؟ — على صفقاتك المحسومة لا على الذاكرة.

    docker exec <web> python tools_stoch_measure.py

═══ لماذا هذه الأداة ═══

«أغلب صفقاتي الناجحة كان الاستوكاستك فيها في التشبّع الشرائي»
ملاحظةٌ من الذاكرة. والذاكرة تحتفظ بالرابحات: الصفقة التي ربحت
تُراجَع ويُبحث عن سببها، والتي خسرت تُنسى. فتصير أيّ خاصّةٍ
شائعة — وهذه شائعة في الأسواق الصاعدة — «سبب النجاح».

والسؤال الصحيح ليس «كم من الرابحات كانت هكذا؟» بل:

    نسبة الربح **داخل** الحالة  مقابل  نسبة الربح خارجها

فلو كانت ٦٠٪ من صفقاتك في هذه الحالة و٦٠٪ من خسائرك كذلك، فهي
تصف سوقك لا تنبّئ بشيء.

═══ ولا نظرَ إلى المستقبل ═══

الحالة تُقاس على الشموع المغلقة **قبل** وقت الدخول — لا على
الشمعة التي دخلتَ فيها ولا بعدها.

═══ وحدُّ هذه الأداة ═══

تقرأ الشموع المخزَّنة. فرمزٌ حُذفت شموعه أو سوقٌ لم يُزامَن لا
يدخل العدّ — ويُعلَن عدده بدل أن يُبتلع.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

MIN_PER_GROUP = 15


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


def two_prop_z(k1: int, n1: int, k2: int, n2: int) -> float:
    """‏z لفرق نسبتين — بلا scipy."""
    if not n1 or not n2:
        return 0.0
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0
    return (k1 / n1 - k2 / n2) / se


def main() -> int:
    import django

    django.setup()

    import pandas as pd

    from dashboard.models import Trade
    from scanner import storage
    from scanner.analysis import stoch_watch
    from scanner.indicators.momentum import stoch_rsi, stoch_rsi_state

    print(__doc__.strip().splitlines()[0])
    print()

    # ═══ المحسومة وحدها ═══
    #
    # ``pending`` و``open`` و``expired`` نتيجتها لم تُعرف بعد.
    # وإدخالها يخلط «لم يُحسم» بـ«خسر» — فتبدو كل حالةٍ أسوأ.
    rows = list(Trade.objects.filter(status__in=["won", "lost"])
                .order_by("opened_at"))
    if not rows:
        print("✗ لا صفقات محسومة بعد (رابحة أو خاسرة).")
        return 1

    groups: dict[str, list[int]] = {}
    skipped = 0

    for t in rows:
        tf = t.timeframe or "4h"
        df = storage.load(t.market, t.symbol, tf)
        # ``signal_at`` احتياطاً: لحظة القرار، وهي غير فارغة دائماً
        opened = t.opened_at or t.signal_at
        if df is None or len(df) < 60 or opened is None:
            skipped += 1
            continue
        # ═══ قبل الدخول لا عنده ═══
        #
        # القصّ عند وقت الفتح، ثمّ ``stoch_rsi_state`` يقرأ ‎-2‎.
        # فالحالة من شمعةٍ أغلقت قبل الدخول يقيناً.
        try:
            idx = pd.to_datetime(df.index, utc=True)
            cut = df[idx < pd.Timestamp(opened).tz_convert("UTC")]
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        if len(cut) < 60:
            skipped += 1
            continue

        try:
            frame = stoch_rsi(cut["close"].astype(float))
            st = stoch_rsi_state(frame)
            up = stoch_watch._uptrend(cut["close"])
            state = stoch_watch.classify(st.get("zone", "unknown"), up)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue

        groups.setdefault(state, []).append(1 if t.status == "won" else 0)

    total = sum(len(v) for v in groups.values())
    if not total:
        print(f"✗ لم تُقَس صفقة واحدة ({skipped} بلا شموع كافية).")
        return 1

    print(f"صفقات محسومة: {len(rows)} · مقيسة: {total} · "
          f"متعذّرة: {skipped}")
    print()
    print(f"{'الحالة':<30}{'عدد':>6}{'ربح':>7}{'فاصل الثقة':>16}")
    print("─" * 62)

    for state in ("riding", "exhausted", "oversold", "middle", "unknown"):
        v = groups.get(state)
        if not v:
            continue
        p, lo, hi = wilson(sum(v), len(v))
        label = stoch_watch.STATE_LABELS[state][:28]
        print(f"{label:<30}{len(v):>6}{p:>6.1f}%{f'[{lo}–{hi}]':>16}")

    # ═══ المقارنة هي الجواب ═══
    inside = groups.get("riding", [])
    outside = [w for s, v in groups.items() if s != "riding" for w in v]
    print()
    if len(inside) < MIN_PER_GROUP or len(outside) < MIN_PER_GROUP:
        print(f"⇒ العيّنة أقصر من أن تُقارَن (داخل {len(inside)} · "
              f"خارج {len(outside)}؛ يلزم {MIN_PER_GROUP} لكلٍّ).")
        print("  لا حكم — وهذا جواب، لا فشل.")
        return 0

    k1, n1 = sum(inside), len(inside)
    k2, n2 = sum(outside), len(outside)
    p1, lo1, hi1 = wilson(k1, n1)
    p2, lo2, hi2 = wilson(k2, n2)
    z = two_prop_z(k1, n1, k2, n2)

    print(f"  راكب التشبّع : {p1:.1f}% [{lo1}–{hi1}]  (n={n1})")
    print(f"  ما عداه      : {p2:.1f}% [{lo2}–{hi2}]  (n={n2})")
    print(f"  الفارق {p1 - p2:+.1f} نقطة · z={z:+.2f}")
    print()

    # ═══ والنسبة العكسية تُقال أيضاً ═══
    #
    # «كم من الرابحات كانت راكبة؟» هو السؤال الذي تجيب عنه
    # الذاكرة — ويبدو حاسماً وهو لا يعني شيئاً وحده. فيُعرَض
    # بجانب السؤال الصحيح كي يُرى الفرق.
    wins = [s for s, v in groups.items() for w in v if w]
    if wins:
        share = 100.0 * sum(1 for s in wins if s == "riding") / len(wins)
        losses = [s for s, v in groups.items() for w in v if not w]
        lshare = (100.0 * sum(1 for s in losses if s == "riding") / len(losses)
                  if losses else 0.0)
        print(f"  للمقارنة: {share:.0f}٪ من رابحاتك كانت «راكبة» — "
              f"و{lshare:.0f}٪ من خاسراتك أيضاً.")
        print("  والرقمان المتقاربان يعنيان أنّ الحالة تصف سوقك "
              "لا تنبّئ به.")
        print()

    if abs(z) < 2.0:
        print("⇒ الفارق داخل الضجيج. الفلتر يُعرَض ولا يُبنى عليه قرار.")
    elif z > 0:
        print("⇒ الحالة تسبق ربحاً أكثر بفارقٍ يتجاوز الضجيج.")
        print("   تصلح شرطاً في «بناء الاستراتيجيات» — لا قاعدةً وحيدة.")
    else:
        print("⇒ الحالة تسبق ربحاً **أقلّ**. عكس ما تذكر — وهذا بالضبط")
        print("   ما تفعله الذاكرة: تحتفظ بالرابحات وتنسى البقيّة.")

    print()
    print("ملاحظة: عيّنةٌ واحدة على سجلٍّ واحد. والنتيجة تصف ما مضى")
    print("في هذه الأسواق — لا قانوناً عامّاً.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
