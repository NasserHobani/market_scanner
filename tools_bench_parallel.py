# -*- coding: utf-8 -*-
"""هل يُسرّع التوازي التحليل على **جهازك**؟

═══ لماذا يُقاس عندك لا عندي ═══

الجواب يعتمد على عدد الأنوية وسرعة القرص ونظام التشغيل. وقياسٌ على
آلةٍ بنواتين لا يقول شيئاً عن آلةٍ بستّ عشرة.

والقياس على آلة التطوير (نواتان)::

    متسلسل              2.75ث   (115 ms/رمز)
    خيوط ×4             3.50ث   ×0.78     أبطأ
    عمليّات ×4 (spawn)   4.99ث   ×0.55     أبطأ

═══ ولماذا الخيوط تُبطئ ═══

‏pandas يحرّر قفل المفسّر في أجزاء ويُمسكه في أخرى. والتقييم كثير
النداءات الصغيرة، فتتنازع الخيوط على القفل بدل أن تتقاسم العمل.
والجلب الشبكيّ عكسه — انتظارٌ خالص — ولذلك يبقى مُخيَّطاً في المسح.

═══ ولماذا العمليّات قد تُبطئ أيضاً ═══

على ويندوز تُنشأ العمليّة بـ ``spawn``: كل عاملٍ يعيد استيراد
‏pandas و numpy وحزمة ``scanner`` كاملةً — ثانيتان أو ثلاث قبل أن
يعمل شيئاً. وهذه الكلفة ثابتة لا تُقسَّم، فتبتلع الربح إن كان
العمل قصيراً.

    python tools_bench_parallel.py
    python tools_bench_parallel.py --market crypto --n 40
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ═══ هامش المعنى ═══
#
# ‏×1.04 ليس ربحاً بل ضجيج. والنسخة الأولى أوصت به وجعلت التحذير
# حاشية — فمن يقرأ «الأسرع: عمليّات ×4» يبدّل إعداده ويدفع تعقيداً
# مقابل لا شيء. والربع ليس رقماً مقدّساً، لكنّه أوسع من تذبذب
# الجدولة المعتاد.
MIN_GAIN = 1.25

# كل قياس يُعاد ويُؤخذ أسرعه: تشغيلةٌ واحدة تقيس الضجيج مع العمل.
REPEAT = 3

# للإسقاط على السوق كاملاً — الرقم الذي يهمّ فعلاً لا زمن العيّنة.
FULL_MARKET = 300

_CFG_CACHE: dict = {}


def _run_threads(syms, w: int) -> None:
    with ThreadPoolExecutor(max_workers=w) as p:
        list(p.map(score_one, syms))


def _run_procs(syms, w: int) -> None:
    # ‏spawn عمداً: هو ما يقع على ويندوز، و``fork`` على لينكس يعطي
    # قياساً متفائلاً لا يُنقَل.
    ctx = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=w, mp_context=ctx) as p:
        list(p.map(score_one, syms, chunksize=max(1, len(syms) // (w * 2))))


def score_one(args) -> tuple[str, float | None]:
    """تقييم رمز واحد — قابل للنقل بين العمليّات."""
    sym, market, tf = args
    from scanner import storage
    from scanner.config import load_market
    from scanner.scoring import score_with_recommendation

    cfg = _CFG_CACHE.get(market)
    if cfg is None:
        cfg = load_market(str(ROOT / "config" / f"{market}.yaml"))
        _CFG_CACHE[market] = cfg
    df = storage.load(market, sym, tf)
    if df is None or len(df) < 60:
        return sym, None
    r = score_with_recommendation(df, sym, tf, cfg)
    return sym, float(r.score)


def main() -> int:
    ap = argparse.ArgumentParser(description="قياس التوازي")
    ap.add_argument("--market", default="saudi")
    ap.add_argument("--timeframe", default="")
    # ═══ لماذا ستّون لا أربعة وعشرون ═══
    #
    # كلفة ``spawn`` ثابتة (استيراد pandas في كل عامل). وعلى عيّنةٍ
    # صغيرة تبتلع الربح كلّه، فيبدو التوازي خاسراً وهو قد يربح على
    # السوق كاملاً. والعيّنة يجب أن تشبه العمل الحقيقي.
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()

    from scanner import storage
    from scanner.config import load_market

    cfg = load_market(ROOT / "config" / f"{a.market}.yaml")
    tf = a.timeframe or cfg.timeframes[0]
    syms = [(s, a.market, tf)
            for s in storage.stored_symbols(a.market, tf)[: a.n]]

    print("=" * 60)
    print(f"قياس التوازي — {a.market} · {tf}")
    print("=" * 60)
    if len(syms) < 8:
        print(f"\n✗ عيّنة صغيرة ({len(syms)} رمزاً) — القياس عليها ضجيج.")
        return 1
    cores = os.cpu_count() or 1
    print(f"  العيّنة: {len(syms)} رمزاً · أنوية الجهاز: {cores}")

    # ═══ يُعاد القياس ويُؤخذ الأسرع ═══
    #
    # تشغيلةٌ واحدة تقيس الضجيج مع العمل: جدولة النظام، وذاكرة
    # المعالج، وما يعمل في الخلفية. والأسرع من ثلاث أقرب إلى الكلفة
    # الحقيقية من متوسّطٍ تجرّه تشغيلةٌ متعثّرة.
    def timeit(fn, repeat: int = REPEAT) -> float:
        best = float("inf")
        for _ in range(repeat):
            t = time.perf_counter()
            fn()
            best = min(best, time.perf_counter() - t)
        return best

    serial = timeit(lambda: [score_one(x) for x in syms])
    per = serial / len(syms) * 1000
    print(f"\n  متسلسل              {serial:6.2f}ث "
          f"({per:5.0f} ms/رمز)")

    best_name, best_t = "متسلسل", serial

    def report(name: str, el: float) -> None:
        nonlocal best_name, best_t
        ratio = serial / el
        flag = "أسرع" if ratio > 1.0 else "أبطأ"
        print(f"  {name:<18} {el:6.2f}ث   ×{ratio:.2f}  {flag}")
        if el < best_t:
            best_name, best_t = name.strip(), el

    for w in (2, 4, max(4, cores)):
        report(f"خيوط ×{w}", timeit(
            lambda w=w: _run_threads(syms, w)))

    for w in (2, 4, max(4, cores)):
        try:
            report(f"عمليّات ×{w}", timeit(
                lambda w=w: _run_procs(syms, w)))
        except Exception as exc:  # noqa: BLE001
            print(f"  عمليّات ×{w:<2}         ✗ {str(exc)[:50]}")

    # ═══ الحكم يحتاج هامشاً ═══
    #
    # ‏×1.04 ليس ربحاً بل ضجيج قياس. والنسخة الأولى من هذه الأداة
    # أوصت به وجعلت التحذير حاشية — وهذا خطأ في الأداة لا في
    # القارئ: من يقرأ «الأسرع: عمليّات ×4» يبدّل إعداده، فيدفع
    # تعقيداً مقابل لا شيء.
    #
    # فدون ``MIN_GAIN`` يُعلَن المتسلسل فائزاً صراحةً.
    gain = serial / best_t if best_t else 1.0
    if gain < MIN_GAIN:
        best_name = "متسلسل"

    print("\n" + "=" * 60)
    if best_name == "متسلسل":
        if gain > 1.0:
            print(f"  ✓ ابقَ على المتسلسل — أفضل بديل ×{gain:.2f} فقط،")
            print(f"    وهو دون هامش المعنى (×{MIN_GAIN:.2f}). فرقٌ كهذا")
            print("    يتبدّل بين تشغيلةٍ وأخرى، وتبديل الإعداد لأجله")
            print("    يشتري تعقيداً بلا مقابل.")
        else:
            print("  ✓ المتسلسل هو الأسرع على جهازك — لا تُفعّل التوازي.")
        print("\n    وهذا شائع: التقييم نداءات pandas صغيرة متلاحقة،")
        print("    والتوازي يضيف كلفةً أكبر ممّا يوفّر.")
    else:
        print(f"  ✓ الأسرع: {best_name} — ×{gain:.2f}")
        n = best_name.split("×")[-1]
        kind = "threads" if "خيوط" in best_name else "processes"
        print(f"\n    شغّل المسح به:")
        print(f"      python web/manage.py scan --market {a.market} "
              f"--analyze {kind} --jobs {n}")
    full = int(FULL_MARKET)
    print(f"\n  · بهذا المعدّل، تحليل {full} رمزاً ≈ "
          f"{per * full / 1000:.0f}ث بالمتسلسل"
          + (f" · {best_t / len(syms) * full:.0f}ث بـ{best_name}"
             if best_name != "متسلسل" else ""))
    print("  · المقيس هنا التحليل وحده. الجلب مُخيَّط أصلاً في المسح")
    print("    لأنّه انتظار شبكة — وهو ما تنفع فيه الخيوط فعلاً.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
