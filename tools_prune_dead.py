# -*- coding: utf-8 -*-
"""الرموز المشطوبة — تُعرَض، ثمّ تُؤرشَف إن أردت.

═══ لماذا وُجدت ═══

توقّف المسح التلقائي للكريبتو من ٢٠ أغسطس: لا دورة، لا مراقبة، لا
صفقة. والسبب لم يكن في المسح ولا في الشبكة:

    crypto 4h · ٥٣٤ زوجاً · منها ١٣٨ آخر شمعة لها من **٢٠٢٢**

‏POLYUSDT و HNTUSDT و SRMUSDT — رموزٌ شُطبت من بينانس وبقيت ملفّاتها
على القرص. والجلب التراكمي يطلب الناقص لها في كل دورة فلا يعود
بشيء، إلى الأبد.

وكانت تُعدّ «حرجة»، فبلغ الحرج ٥٤٫٩٪ — فوق النصف — فأعلنت بوابة
الحداثة السوق متأخّراً وأجهضت المسح قبل أن يبدأ.

أي أنّ **مقبرةً على القرص كانت تحجب سوقاً حيّاً**، وكلّما طال
الزمن ازدادت المقبرة ورسخ الحجب.

═══ ولماذا الأرشفة لا الحذف ═══

الملف تاريخٌ صحيح لسهمٍ كان يُتداول، وقد تحتاجه لاختبارٍ خلفي أو
لتشريح صفقةٍ قديمة. فيُنقَل إلى ``data/_archive/`` لا يُمحى.

    python tools_prune_dead.py                 # عرض فقط
    python tools_prune_dead.py --archive       # نقل إلى الأرشيف
    python tools_prune_dead.py --market crypto --bars 200
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

OK, BAD, DOT, WARN = "✓", "✗", "·", "!"


def main() -> int:
    ap = argparse.ArgumentParser(description="الرموز المشطوبة")
    ap.add_argument("--market", default="", help="سوق واحد، أو الكل")
    ap.add_argument("--bars", type=float, default=0.0,
                    help="حدّ الشموع (الافتراضي من الإعدادات)")
    ap.add_argument("--archive", action="store_true",
                    help="انقل الملفّات إلى data/_archive/")
    a = ap.parse_args()

    from scanner import storage
    from scanner.market_sync.config import DEFAULT_SYNC_CONFIG as CFG

    limit = a.bars or CFG.dead_max_bars
    root = Path(storage.DATA_DIR)
    markets = ([a.market] if a.market
               else [p.name for p in sorted(root.iterdir())
                     if p.is_dir() and not p.name.startswith("_")
                     and p.name != "market_sync" and p.name != "universe"])

    print("=" * 64)
    print(f"الرموز المشطوبة — أقدم من {limit:.0f} شمعة")
    print("=" * 64)

    total_dead = total_live = 0
    freed = 0
    victims: list[tuple[str, str, str, float, Path]] = []

    for market in markets:
        mroot = root / market
        if not mroot.is_dir():
            continue
        for tfdir in sorted(mroot.iterdir()):
            if not tfdir.is_dir():
                continue
            tf = tfdir.name
            for sym in storage.stored_symbols(market, tf):
                last = storage.last_time_on_disk(market, sym, tf)
                behind = storage.bars_behind_from(last, tf, market=market)
                if behind is None:
                    continue
                if behind > limit:
                    total_dead += 1
                    for sfx in storage.SUFFIXES:
                        f = tfdir / f"{sym}{sfx}"
                        if f.exists():
                            freed += f.stat().st_size
                            victims.append((market, tf, sym, behind, f))
                else:
                    total_live += 1

    if not victims:
        print(f"\n{OK} لا رموز مشطوبة — {total_live} زوجاً حيّاً.")
        return 0

    by_market: dict[str, int] = {}
    for m, _tf, _s, _b, _f in victims:
        by_market[m] = by_market.get(m, 0) + 1
    print()
    for m, n in sorted(by_market.items(), key=lambda x: -x[1]):
        print(f"  {m:8} {n:5} ملفّاً")
    print(f"\n  المجموع: {len(victims)} ملفّاً · {freed / 1e6:.1f} ميغابايت")
    print(f"  أحياء:   {total_live} زوجاً")

    victims.sort(key=lambda v: -v[3])
    print("\n  أقدم عشرة:")
    seen = set()
    for m, tf, sym, behind, _f in victims:
        if sym in seen:
            continue
        seen.add(sym)
        last = storage.last_time_on_disk(m, sym, tf)
        print(f"    {sym:14} {tf:4} متأخّر {behind:8.0f} شمعة · "
              f"آخر شمعة {str(last)[:10]}")
        if len(seen) >= 10:
            break

    if not a.archive:
        print(f"\n  {DOT} عرضٌ فقط. للنقل إلى الأرشيف:")
        print("      python tools_prune_dead.py --archive")
        print(f"\n  {DOT} المزامنة تتخطّاها أصلاً منذ الإصلاح — الأرشفة")
        print("      تحرّر القرص وتُسرّع تعداد الملفّات، ولا تلزم.")
        return 0

    arch = root / "_archive"
    moved = failed = 0
    for m, tf, sym, _b, f in victims:
        dest = arch / m / tf
        try:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(dest / f.name))
            moved += 1
        except OSError as exc:
            failed += 1
            print(f"  {BAD} {sym} {tf}: {str(exc)[:70]}")
    print(f"\n{OK} نُقل {moved} ملفّاً إلى {arch}"
          + (f" · تعذّر {failed}" if failed else ""))
    print(f"  حُرّر {freed / 1e6:.1f} ميغابايت من مجلّد البيانات.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
