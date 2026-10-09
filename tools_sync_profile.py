# -*- coding: utf-8 -*-
"""أين يذهب زمن المزامنة؟ — بالقياس لا بالتخمين.

    docker exec <web> python tools_sync_profile.py
    docker exec <web> python tools_sync_profile.py --market us

═══ لماذا أداة ═══

«المزامنة بطيئة» تُفسَّر بالشبكة تلقائياً، فيُرفع عدد الخيوط أو
يُقلَّل عدد الرموز — وكلاهما علاجٌ لعَرَضٍ قد لا يكون السبب.

وهذه تقيس الأجزاء الأربعة على عيّنةٍ صغيرة، فيُرى أيّها يأكل
الزمن فعلاً:

    ١. قراءة ذيل الملفّ   (‏last_time_on_disk)
    ٢. قراءة الملفّ كاملاً (‏storage.load)
    ٣. كتابة حالة زوج     (‏status_store.update_pair)
    ٤. طلبٌ شبكيّ واحد    (‏adapter.fetch)

ولا تكتب شيئاً ولا تزامن: القراءات على ملفّاتٍ قائمة، والكتابة
على ملفّ حالةٍ مؤقّت.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

SAMPLE = 12


def _ms(fn, n: int = 1) -> float:
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t0) * 1000.0 / max(1, n)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--market", default="crypto")
    ap.add_argument("--tf", default="4h")
    ap.add_argument("--net", action="store_true",
                    help="اقْس طلباً شبكياً واحداً أيضاً")
    args = ap.parse_args()

    print(__doc__.strip().splitlines()[0])
    print()

    from scanner import storage
    from scanner.market_sync import get_service, status_store
    from scanner.market_sync.config import DEFAULT_SYNC_CONFIG

    svc = get_service()
    syms = svc.resolve_symbols(args.market)
    if not syms:
        print(f"✗ لا رموز في {args.market}")
        return 1

    tfs = svc._timeframes_for(
        svc._market_cfg(Path(ROOT / "config"), args.market))
    pairs_total = len(syms) * len(tfs)
    print(f"السوق {args.market} · {len(syms)} رمزاً × {len(tfs)} فريماً "
          f"= {pairs_total} زوجاً في الدورة")
    print(f"الفريمات: {' · '.join(tfs)}")
    print()

    probe = [s for s in syms[:SAMPLE]]

    # ── ١) ذيل الملفّ ──
    tail = _ms(lambda: [storage.last_time_on_disk(args.market, s, args.tf)
                        for s in probe]) / len(probe)
    # ── ٢) الملفّ كاملاً ──
    full = _ms(lambda: [storage.load(args.market, s, args.tf)
                        for s in probe]) / len(probe)

    # ── ٣) كتابة حالة زوج ──
    #
    # على نسخةٍ مؤقّتة: القياس لا يلمس ملفّ الإنتاج.
    tmpdir = tempfile.mkdtemp(prefix="syncprof-")
    try:
        src = Path(DEFAULT_SYNC_CONFIG.status_path)
        dst = Path(tmpdir) / "status.json"
        size_mb = 0.0
        if src.exists():
            shutil.copy2(src, dst)
            size_mb = src.stat().st_size / 1e6
        cfg = type(DEFAULT_SYNC_CONFIG)(
            **{**DEFAULT_SYNC_CONFIG.__dict__, "status_path": str(dst)})
        write = _ms(lambda: status_store.update_pair(
            args.market, probe[0], args.tf, {"mode": "probe"}, config=cfg), 3)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"{'الجزء':<28}{'لكل زوج':>12}{'× أزواج الدورة':>18}")
    print("─" * 60)

    def line(name: str, per_ms: float) -> float:
        total = per_ms * pairs_total / 1000.0
        print(f"{name:<28}{per_ms:>9.2f}ms{total:>15.1f}ث")
        return total

    t_tail = line("قراءة ذيل الملفّ", tail)
    t_full = line("قراءة الملفّ كاملاً", full)
    t_write = line("كتابة حالة زوج", write)

    net = 0.0
    if args.net:
        from scanner.adapters import get_adapter, http_pool

        cfg_m = svc._market_cfg(Path(ROOT / "config"), args.market)
        ad = get_adapter(cfg_m.adapter)

        # ═══ الأوّل يدفع المصافحة والبقيّة لا ═══
        #
        # قياسُ متوسّطٍ يخلطهما ويُخفي الفرق — وهو الفرق كلّه.
        first = _ms(lambda: ad.fetch(probe[0], args.tf, 5), 1)
        warm = _ms(lambda: ad.fetch(probe[0], args.tf, 5), 5)
        net = line("طلبٌ شبكيّ (الأوّل)", first)
        line("طلبٌ شبكيّ (بعد الإحماء)", warm)
        st = http_pool.stats()
        print(f"{'':28}المجمّع: "
              f"{'مُفعَّل' if st['pool_enabled'] else '**مُطفأ**'} · "
              f"{st['pooled']} مجمَّع · {st['fallback']} ارتداد")
        if not st["requests_lib"]:
            print(f"{'':28}⚠ ‎requests‎ غير مثبّتة — لا إعادة استعمال")
        net = warm

    print()
    print(f"حجم ملفّ الحالة: {size_mb:.2f} ميغابايت")
    print()

    # ═══ الحكم ═══
    worst = max([("قراءة الملفّ كاملاً", t_full),
                 ("كتابة حالة زوج", t_write)] +
                ([("الشبكة", net)] if net else []),
                key=lambda x: x[1])
    print(f"⇒ الأثقل: {worst[0]} — {worst[1]:.0f} ثانية في الدورة "
          "لو نُفّذ لكل زوج.")
    print()
    print("وهذان الاثنان عُولجا:")
    print(f"  • الحالة تُكتب **مرّةً** في نهاية الدورة لا لكل زوج")
    print(f"    (توفير ~{t_write:.0f}ث)")
    print(f"  • والذيل يُقرأ قبل الملفّ كاملاً، فما لم تُغلَق له")
    print(f"    شمعةٌ جديدة لا يُقرأ أصلاً (توفير حتى ~{t_full - t_tail:.0f}ث)")
    if net:
        # ═══ والتوازي يقسم الشبكة وحدها ═══
        #
        # ‏القرص والقفل لا يتوازيان: القفل يُسلسلهما. فالخيوط تقسم
        # الانتظار الشبكيّ لا غير.
        from scanner.market_sync.config import DEFAULT_SYNC_CONFIG as D

        workers = D.max_workers
        print()
        print(f"بـ{workers} خيوط: الشبكة ≈ "
              f"{net * pairs_total / 1000.0 / workers:.0f} ثانية للسوق")
        print("  (والقرص لا يتوازى — القفل يُسلسله، ولهذا جُمّعت "
              "الكتابة)")

    print()
    print("وإن بقيت الشبكة هي الأثقل بعد الإحماء فالعلاج:")
    print("  • قلّل فريمات المزامنة — كل فريمٍ يضرب عدد الرموز")
    print("  • أو أطِل فترة ‎market_sync‎ لتطابق مدّتها الحقيقية")
    print("  • ولا مزيدٌ من الخيوط: حدّ Binance على الوزن لكل **IP**")
    print("    لا لكل اتّصال — فالزيادة تبلغ الحدّ ولا تُنقص الزمن.")
    return 0


if __name__ == "__main__":
    import django

    django.setup()
    raise SystemExit(main())
