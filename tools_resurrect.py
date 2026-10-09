# -*- coding: utf-8 -*-
"""المقبرة: من مات فعلاً ومن بدا ميّتاً — ثمّ إحياء الثاني.

    python tools_resurrect.py --market crypto --tf 4h          # تقرير فقط
    python tools_resurrect.py --market crypto --tf 4h --apply  # ويُحيي

═══ ما المشكلة ═══

``dead`` تعني «آخر شمعة أقدم من مئة شمعة». ووُضعت للرمز الذي
**شُطب من المنصّة**: ملفٌّ باقٍ والجلب التراكمي يطلب الناقص فلا
يعود بشيء، إلى الأبد.

لكنّها لا تفرّق بين سببين:

    رمزٌ شُطب        ← لا علاج، وملاحقته هدرٌ محض
    مزامنةٌ تعطّلت    ← علاجُه جلبةٌ واحدة

ومزامنةٌ تتوقّف أكثر من مئة شمعة (‎4h‎ ← سبعة عشر يوماً) تُسقط
السوق كلّه في الخانة الأولى دفعةً واحدة. وبعدها لا شيء يجلب لهم:
``resolve_symbols`` يستبعدهم، وبوّابة المسح تُنعش ``alive`` وحدهم،
والمشطوب ليس منهم. بابٌ يُغلق ولا يُفتح.

═══ والفارق يُسأل من المنصّة ═══

لا يُحزَر من القرص — كلاهما ملفٌّ قديم. يُسأل من كون المنصّة
اليوم: من كان فيه فهو حيّ مهما قدُم ملفّه.

═══ ولا يُحيي إلّا بـ‎--apply‎ ═══

الإحياء يكتب على ملفّات الشموع. فالافتراض تقريرٌ يُقرأ أوّلاً.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--market", default="crypto")
    ap.add_argument("--tf", default="")
    ap.add_argument("--apply", action="store_true",
                    help="نفّذ الإحياء فعلاً (الافتراض: تقرير)")
    ap.add_argument("--max", type=int, default=0, help="سقف الرموز")
    args = ap.parse_args()

    print(__doc__.strip().splitlines()[0])
    print()

    from scanner.market_sync import get_service
    from scanner.market_sync.freshness import assess_freshness

    svc = get_service()
    cfg_dir = ROOT / "config"
    cfg = svc._market_cfg(cfg_dir, args.market)
    tf = args.tf or svc._timeframes_for(cfg)[0]
    syms = svc.resolve_symbols(args.market, config_dir=cfg_dir)
    print(f"السوق {args.market} · الفريم {tf} · {len(syms)} رمزاً")

    # ── ١) الحالة على القرص ──
    counts: Counter[str] = Counter()
    oldest: list[tuple[float, str, str]] = []
    for s in syms:
        info = assess_freshness(args.market, s, tf, config=svc.config)
        counts[info["status"]] += 1
        if info["status"] == "dead":
            oldest.append((float(info.get("bars_behind") or 0), s,
                           str(info.get("latest_candle") or "")[:10]))

    print("\n═══ الحالة ═══")
    label = {"fresh": "طازج", "stale": "متأخّر", "critical": "حرج",
             "dead": "مشطوب", "missing": "بلا ملفّ", "error": "خطأ"}
    for k, n in counts.most_common():
        print(f"  {label.get(k, k):10s} {n:5d}")

    if not counts["dead"]:
        print("\nلا مشطوبين — لا شيء يُحيا.")
        return 0

    # ═══ وتاريخ الشموع يقول القصّة ═══
    #
    # شطبٌ حقيقيّ يتفرّق على شهور: كل رمزٍ وتاريخُه. أمّا توقّفُ
    # مزامنةٍ فيترك **تاريخاً واحداً** يتكرّر عند المئات — وهو
    # التوقيع الذي يفرّق الحالتين قبل أن يُسأل أحد.
    byday = Counter(d for _, _, d in oldest)
    print("\n═══ تاريخ آخر شمعة للمشطوبين ═══")
    for day, n in byday.most_common(5):
        bar = "█" * min(40, n * 40 // max(1, len(oldest)))
        print(f"  {day:12s} {n:5d}  {bar}")
    top, top_n = byday.most_common(1)[0]
    if top_n >= max(10, len(oldest) // 2):
        print(f"\n  ⇒ {top_n} رمزاً توقّفوا في اليوم نفسه ({top}).")
        print("    شطبٌ جماعيّ في يومٍ واحد لا يحدث — هذه مزامنة توقّفت.")
    else:
        print("\n  ⇒ التواريخ متفرّقة — شطبٌ حقيقيّ على الأرجح.")

    # ── ٢) كون المنصّة ──
    universe = svc.live_universe(args.market, config_dir=cfg_dir)
    if universe is None:
        print("\n⚠ تعذّر معرفة كون المنصّة — لا يمكن التمييز بثقة.")
        print("  شغّل ‎tools_doctor_net.py‎ أوّلاً: المحوّل قد يكون لا يصل.")
        return 1
    alive = [s for _, s, _ in oldest if s in universe]
    gone = [s for _, s, _ in oldest if s not in universe]
    print(f"\n═══ كون المنصّة: {len(universe)} رمزاً ═══")
    print(f"  ما زال متداولاً  {len(alive):5d}  ← يُحيا")
    print(f"  غاب عن المنصّة   {len(gone):5d}  ← مشطوبٌ حقاً")
    if gone[:8]:
        print(f"    ({' · '.join(gone[:8])}{' …' if len(gone) > 8 else ''})")

    if not args.apply:
        print(f"\nتقريرٌ فقط. للتنفيذ:")
        print(f"  python tools_resurrect.py --market {args.market} "
              f"--tf {tf} --apply")
        return 0

    # ── ٣) الإحياء ──
    print(f"\n═══ الإحياء ═══")
    res = svc.resurrect(args.market, tf, symbols=syms, config_dir=cfg_dir,
                        max_pairs=args.max or None)
    print(f"  أُعيد بناؤه   {res['rebuilt']:5d}   (الفجوة أوسع من جلبة)")
    print(f"  رُقّع         {res['patched']:5d}")
    print(f"  مشطوبٌ حقاً   {res['buried']:5d}")
    print(f"  فشل          {res['failed']:5d}")
    if res["stopped"]:
        print(f"  توقّف: {res['stopped']} — بقي {res['remaining']}")
    for f in res["failures"][:5]:
        print(f"    ✗ {f['symbol']}: {f['error']}")
    print(f"  الزمن: {res['elapsed']}ث")
    print("\nأعد فتح شاشة الماسح — البوّابة تُقيّم من جديد.")
    return 0


if __name__ == "__main__":
    import django

    django.setup()
    raise SystemExit(main())
