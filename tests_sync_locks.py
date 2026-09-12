# -*- coding: utf-8 -*-
"""قفل المزامنة — وكيف أوقف ملفٌّ فارغ السوقَ شهراً بلا رسالة.

═══ ما وقع ═══

قفل الزوج ملفٌّ يُنشأ بـ ``O_EXCL`` ويُحذف في ``finally``. وما لا
يمرّ بـ‎finally‎ يترك الملفّ: حاويةٌ تُقتَل، ‏docker stop يبلغ
مهلته، كهرباءٌ تنقطع، عمليةٌ تُنهى من مدير المهامّ.

ثمّ تعود كل مزامنةٍ تالية لذلك الزوج ``{"ok": false, "reason":
"locked"}`` — **بلا استثناء ولا سطر سجلّ**. فتشيخ شموعه، ويصير
``critical``، وتُعلن البوّابة «بيانات السوق متأخرة جداً» وتحجب
المسح. والسبب ملفٌّ فارغ لا يذكره أحد.

قِيس على الجهاز: ٢١٦ قفلاً عالقاً، أقدمها من ١١ أغسطس — شهرٌ
كامل لم تُزامَن فيه تلك الأزواج، والنظام «يعمل» طوال الوقت.

═══ ولماذا ليس بالـPID ═══

القفل يحمل ‏PID كاتبه، والإغراء أن يُسأل: أحيٌّ هو؟ لكنّ الأرقام
تُعاد داخل الحاويات — كلّ حاويةٍ فضاءٌ يبدأ من ١. فقفلٌ كتبه
‎PID 7‎ في حاويةٍ ماتت يبدو حيّاً حين يصادف ‎PID 7‎ في التي بعدها.

فالحكم بالعمر: مزامنة زوجٍ واحد ثوانٍ، وما جاوز عشر دقائق متروك.

═══ والثمن الثاني ═══

المهلة كانت ثلاثين ثانية لكل زوج. ومئتا رمزٍ مقفلة = ساعةٌ
وأربعون دقيقة من الانتظار المحض في الدورة الواحدة. فالمهلة خمسٌ
الآن: القفل المشغول يعني أنّ عاملاً آخر يجلبه، وانتظارُه لا يضيف
شمعة.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.market_sync import locks  # noqa: E402
from scanner.market_sync.config import (  # noqa: E402
    DEFAULT_SYNC_CONFIG, MarketSyncConfig)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def _cfg(d: Path, stale: float = 2.0) -> MarketSyncConfig:
    return MarketSyncConfig(lock_dir=str(d), lock_stale_seconds=stale)


def _try_acquire(cfg, timeout: float = 0.3):
    """محاولةٌ من خيطٍ آخر — القفل الخيطيّ لكل خيطٍ على حدة."""
    out: list[bool] = []

    def run() -> None:
        with locks.sync_lock("crypto", "BTC", "4h",
                             config=cfg, timeout=timeout) as got:
            out.append(got)

    t = threading.Thread(target=run)
    t.start()
    t.join(timeout + 5)
    return out[0] if out else None


# ═══════════ ١) القفل يحمي فعلاً ═══════════
#
# الفحص الأوّل ليس «هل يُستعاد المتروك» بل «هل يمنع المشغول» —
# فاستعادةٌ نهمة أسوأ من العطب: كاتبان على ملفٍّ واحد.
with tempfile.TemporaryDirectory() as _d:
    d = Path(_d)
    cfg = _cfg(d)
    with locks.sync_lock("crypto", "BTC", "4h", config=cfg) as first:
        check("١ القفل يُؤخَذ", first is True)
        check("  والملفّ يُنشأ", any(d.glob("*.lock")))
        check("  والثاني يُردّ ما دام الأوّل حيّاً",
              _try_acquire(cfg) is False)
    check("  ويُحذف عند الخروج", not any(d.glob("*.lock")))

# والخروج بخطأ يحرّره أيضاً — وإلّا صنع كل عطبٍ قفلاً أبدياً
with tempfile.TemporaryDirectory() as _d:
    d = Path(_d)
    cfg = _cfg(d)
    try:
        with locks.sync_lock("crypto", "BTC", "4h", config=cfg):
            raise RuntimeError("عطبٌ في منتصف الجلب")
    except RuntimeError:
        pass
    check("  والاستثناء لا يترك قفلاً", not any(d.glob("*.lock")))


# ═══════════ ٢) المتروك يُستعاد ═══════════
with tempfile.TemporaryDirectory() as _d:
    d = Path(_d)
    d.mkdir(exist_ok=True)
    cfg = _cfg(d, stale=2.0)

    stale = d / "crypto_ETH_4h.lock"
    stale.write_text("99999")          # ‏PID لا وجود له
    old = time.time() - 3600
    os.utime(stale, (old, old))

    t0 = time.time()
    with locks.sync_lock("crypto", "ETH", "4h", config=cfg,
                         timeout=5.0) as got:
        took = time.time() - t0
        check("٢ القفل المتروك يُستعاد", got is True)
        # ═══ والسرعة جزءٌ من الإصلاح ═══
        #
        # استعادةٌ بعد انتظار المهلة كاملةً تُصلح الصحّة وتُبقي
        # الإشباع: مئتا زوجٍ × المهلة في كل دورة.
        check("  بلا انتظار المهلة", took < 1.0, f"{took:.2f}ث")

    # وقفلٌ حديث لا يُمَسّ ولو كان صاحبه غائباً: العمر هو الحكم
    fresh = d / "crypto_XRP_4h.lock"
    fresh.write_text("99999")
    check("  والحديث لا يُستعاد",
          locks._reclaim_if_stale(fresh, 600.0) is False and fresh.exists())
    check("  والقديم يُستعاد",
          locks._reclaim_if_stale(stale.__class__(fresh), 0.0) is True)


# ═══════════ ٣) العمر لا الـPID ═══════════
src = (ROOT / "scanner" / "market_sync" / "locks.py").read_text(
    encoding="utf-8")
code = "\n".join(l for l in src.splitlines()
                 if not l.strip().startswith("#"))
check("٣ الحكم بزمن التعديل", "st_mtime" in code)
# ‏os.kill(pid, 0) داخل حاويةٍ يسأل عن فضاء أسماءٍ آخر
check("  ولا os.kill لفحص الحياة", "os.kill" not in code)
check("  والحدّ من الإعداد لا مكتوباً", "config.lock_stale_seconds" in code)
check("  وله قيمة افتراضية", DEFAULT_SYNC_CONFIG.lock_stale_seconds > 0)
# عشر دقائق: أطول بكثيرٍ من مزامنة زوج، وأقصر بكثيرٍ من أن يُشلّ
# السوق أسبوعاً
check("  معقولة (دقيقتان–ساعة)",
      120 <= DEFAULT_SYNC_CONFIG.lock_stale_seconds <= 3600,
      str(DEFAULT_SYNC_CONFIG.lock_stale_seconds))


# ═══════════ ٤) المهلة لا تُشبع الجدول ═══════════
import inspect  # noqa: E402

sig = inspect.signature(locks.sync_lock.__wrapped__
                        if hasattr(locks.sync_lock, "__wrapped__")
                        else locks.sync_lock)
tmo = sig.parameters["timeout"].default
check("٤ المهلة الافتراضية قصيرة", tmo <= 10, f"{tmo}ث")
# ٢١٠ رمزاً × ٣٠ث = ١٠٥ دقيقة انتظارٍ محض في الدورة الواحدة
check("  وأسوأ حالةٍ تحت نصف ساعة", 210 * tmo < 1800, f"{210*tmo/60:.0f}د")


# ═══════════ ٥) التنظيف عند الإقلاع ═══════════
with tempfile.TemporaryDirectory() as _d:
    d = Path(_d)
    cfg = _cfg(d)
    for i in range(5):
        (d / f"crypto_S{i}_4h.lock").write_text("1")
    (d / "keep.txt").write_text("ليس قفلاً")
    n = locks.clear_all(cfg)
    check("٥ clear_all يحذف الأقفال", n == 5, str(n))
    check("  ولا يمسّ غيرها", (d / "keep.txt").exists())
    check("  ومجلّدٌ غائب لا يرمي",
          locks.clear_all(_cfg(d / "nope")) == 0)

# وتُنادى عند إقلاع المجدول — لا في كل دورة، وإلّا سرق قفل الحيّ
sched = (ROOT / "docker-scheduler.sh").read_text(encoding="utf-8")
sh = "\n".join(l for l in sched.splitlines()
               if not l.lstrip().startswith("#"))
check("  والمجدول ينظّف عند الإقلاع", "locks.clear_all()" in sh)
check("  قبل الحلقة لا داخلها",
      0 < sh.find("clear_all") < sh.find("while "), str(sh.find("clear_all")))


# ═══════════ التقرير ═══════════
print(__doc__.strip().splitlines()[0])
print()
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name
          + (f"   [{extra}]" if extra and not ok else ""))
bad = [n for ok, n, _ in results if not ok]
print()
print(f"{len(results) - len(bad)}/{len(results)} "
      + ("✓" if not bad else "✗ فشل: " + " · ".join(bad[:5])))
sys.exit(1 if bad else 0)
