# -*- coding: utf-8 -*-
"""كم رمزاً ينقص كل سوق — وملؤه إن أردت.

    python tools_fill_markets.py              # تقريرٌ فقط، بلا شبكة تقريباً
    python tools_fill_markets.py --fill       # املأ الناقص
    python tools_fill_markets.py --fill --market crypto
    python tools_fill_markets.py --fill --tf 4h,1d   # فريمان بدل أربعة

═══ لماذا يسبق التقريرُ الملءَ ═══

«اجلب كل الرموز» جملةٌ قصيرة وكلفتها ساعات. والرقم يختلف بين
سوقٍ وآخر اختلافاً كبيراً، ولا يظهر إلّا بالسؤال:

    كريبتو   ``top_n: null``   ← كل زوجٍ فوق ٢٠٠ ألف دولار حجماً
    أمريكي   ``top_n: 400``    ← سقفٌ صريح
    سعودي    ``top_n: null``   ← السوق كلّه

× أربعة فريمات (‎15m, 1h, 4h, 1d‎) = آلاف الطلبات.

فهذه الأداة تقول العدد **قبل** أن تبدأ، ثمّ تملأ إن أمرتَها. وهي
تقرأ القرص وتسأل المنصّة عن قائمة الرموز وحدها — لا عن شموعها.

═══ والملء تزايديّ ═══

ما هو على القرص لا يُعاد تنزيله. فقطعُ الأداة وإعادةُ تشغيلها
تُكمل من حيث وقفت، ولا تبدأ من الصفر.

═══ ولا يُستبدَل بها المجدول ═══

هذه للملء **الأوّل** على جهازٍ أو خادمٍ جديد. وبعدها تتكفّل مهمّة
``market_sync`` بالتحديث الدوريّ — وتشغيلُ هذه دورياً يضاعف
الطلبات بلا فائدة.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))


def main() -> int:
    ap = argparse.ArgumentParser(description="تقرير الرموز الناقصة وملؤها")
    ap.add_argument("--market", default="", help="سوق واحد بدل الكلّ")
    ap.add_argument("--fill", action="store_true", help="املأ الناقص فعلاً")
    ap.add_argument("--tf", default="",
                    help="فريمات مفصولة بفواصل (افتراضي: ما يضبطه النظام)")
    ap.add_argument("--limit", type=int, default=0,
                    help="اقتصر على أوّل N رمزٍ ناقص (تجربة)")
    args = ap.parse_args()

    from scanner import storage
    from scanner.market_sync import get_service

    svc = get_service()
    markets = ([args.market] if args.market
               else ["crypto", "us", "saudi"])
    tfs = [t.strip() for t in args.tf.split(",") if t.strip()] or None

    print("═══ التغطية الآن ═══")
    plan: list[tuple[str, list[str]]] = []
    for m in markets:
        try:
            universe = list(svc.resolve_symbols(m))
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {m:7s} تعذّر الاكتشاف — {str(exc)[:90]}")
            continue
        have = set(storage.stored_symbols(m, "4h"))
        missing = [s for s in universe if s not in have]
        if args.limit:
            missing = missing[:args.limit]
        pct = (len(have & set(universe)) / len(universe) * 100) if universe else 0
        mark = "✓" if not missing else "·"
        print(f"  {mark} {m:7s} مكتشَف {len(universe):>4} · على القرص "
              f"{len(have & set(universe)):>4} ({pct:.0f}٪) · ناقص "
              f"{len(missing):>4}")
        if missing:
            plan.append((m, missing))
            print(f"      أمثلة: {' · '.join(missing[:6])}"
                  + (" …" if len(missing) > 6 else ""))

    if not plan:
        print("\n✓ لا ينقص شيء — كل رمزٍ مكتشَف له شموع.")
        return 0

    # ═══ الكلفة قبل الأمر ═══
    #
    # عددُ الطلبات = رموزٌ ناقصة × فريمات. وطبعُه هنا يجعل القرار
    # واعياً: من رأى «٣٬٨٠٠ طلب» قد يختار فريمين بدل أربعة.
    n_tf = len(tfs) if tfs else 4
    total = sum(len(v) for _, v in plan)
    print(f"\n═══ الكلفة ═══")
    print(f"  {total} رمزاً × {n_tf} فريمات ≈ {total * n_tf:,} طلب")
    print(f"  وبعشرة طلباتٍ في الثانية ≈ "
          f"{total * n_tf / 10 / 60:,.0f} دقيقة")

    if not args.fill:
        print("\n(تقريرٌ فقط — أضف ‎--fill‎ للملء)")
        return 0

    print("\n═══ الملء ═══")
    grand_ok = grand_fail = 0
    for m, missing in plan:
        t0 = time.time()
        print(f"  {m}: {len(missing)} رمزاً…", flush=True)
        try:
            out = svc.sync_market(m, symbols=missing, timeframes=tfs)
        except Exception as exc:  # noqa: BLE001
            print(f"    ✗ تعذّر: {str(exc)[:120]}")
            continue
        ok = int(out.get("successful") or 0)
        bad = int(out.get("failed") or 0)
        grand_ok += ok
        grand_fail += bad
        print(f"    نجح {ok} · فشل {bad} · {time.time()-t0:,.0f}ث")
        # ═══ أسباب الفشل مجمّعة ═══
        #
        # «فشل ٤٠٦» بلا سبب لا يُفعَل به شيء. وثلاثة أسبابٍ
        # بأعدادها تقول أهو مفتاحٌ ناقص أم رمزٌ مشطوب أم حدّ طلبات.
        if bad:
            why: dict[str, int] = {}
            for r in (out.get("results") or []):
                if not r.get("ok"):
                    k = str(r.get("reason") or "?")[:70]
                    why[k] = why.get(k, 0) + 1
            for k, v in sorted(why.items(), key=lambda kv: -kv[1])[:4]:
                print(f"      {v:>4} × {k}")

    print(f"\n═══ الخلاصة: نجح {grand_ok} · فشل {grand_fail} ═══")
    print("والآن شغّل التحليل:")
    print("  python web\\manage.py run_jobs")
    return 0 if grand_ok else 1


if __name__ == "__main__":
    sys.exit(main())
