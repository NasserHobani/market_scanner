# -*- coding: utf-8 -*-
"""Per-symbol/timeframe sync locks — prevent concurrent writers."""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig

log = logging.getLogger(__name__)

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_META = threading.Lock()


def clear_all(config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> int:
    """احذف كل الأقفال. يُنادى عند الإقلاع وحده.

    لحظةُ بدء العملية هي اللحظة الوحيدة التي يُعلَم فيها يقيناً
    أنّ لا مزامنةَ جارية — فحذفُها حينئذٍ آمنٌ بالبناء لا
    بالتقدير. وفي أيّ وقتٍ آخر قد يكون القفل لعاملٍ يعمل.
    """
    d = Path(config.lock_dir)
    if not d.is_dir():
        return 0
    n = 0
    for p in d.glob("*.lock"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    if n:
        log.info("حُذف %d قفلاً عند الإقلاع", n)
    return n


def _key(market: str, symbol: str, timeframe: str) -> str:
    return f"market_sync:{market}:{symbol}:{timeframe}"


def _thread_lock(key: str) -> threading.Lock:
    with _META:
        if key not in _THREAD_LOCKS:
            _THREAD_LOCKS[key] = threading.Lock()
        return _THREAD_LOCKS[key]


def _reclaim_if_stale(path: Path, max_age: float) -> bool:
    """احذف قفلاً هجره صاحبه. ``True`` إن حُذف.

    ═══ لماذا بالعمر لا بالـPID ═══

    القفل يحمل ‏PID كاتبه، والإغراء أن يُسأل: أحيٌّ هو؟ لكنّ
    الأرقام تُعاد داخل الحاويات — كلّ حاويةٍ فضاءٌ مستقلّ يبدأ من
    ١. فقفلٌ كتبه ‎PID 7‎ في حاويةٍ ماتت يبدو حيّاً تماماً حين
    يصادف ‎PID 7‎ في التي بعدها، فلا يُحرَّر أبداً.

    والعمر لا يكذب: مزامنة زوجٍ واحد ثوانٍ، فما جاوز الحدّ متروك.
    """
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:          # اختفى بيننا — وهذا نجاحٌ لا فشل
        return True
    if age < max_age:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    log.warning("قفلٌ متروك حُذف: %s (عمره %.0f دقيقة)", path.name, age / 60)
    return True


@contextmanager
def sync_lock(
    market: str,
    symbol: str,
    timeframe: str,
    *,
    config: MarketSyncConfig = DEFAULT_SYNC_CONFIG,
    # ═══ خمسٌ لا ثلاثون ═══
    #
    # القفل المشغول يعني أنّ عاملاً آخر يجلب هذا الزوج الآن —
    # فانتظارُه لا يضيف شمعة. والثلاثون ثانية كانت تُضرَب في مئتي
    # رمز: ساعةٌ وأربعون دقيقة من الانتظار المحض في الدورة
    # الواحدة، وهي جزءٌ من إشباع الجدول المقيس.
    timeout: float = 5.0,
) -> Iterator[bool]:
    """Acquire process + file lock. Yields True if acquired, False if busy."""
    key = _key(market, symbol, timeframe)
    tlock = _thread_lock(key)
    if not tlock.acquire(blocking=False):
        yield False
        return

    lock_dir = Path(config.lock_dir)
    lock_dir.mkdir(parents=True, exist_ok=True)
    safe = f"{market}_{symbol}_{timeframe}".replace("/", "_").replace(":", "_")
    lock_path = lock_dir / f"{safe}.lock"
    fd: int | None = None
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while time.monotonic() < deadline:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("ascii"))
                acquired = True
                break
            except FileExistsError:
                # المحاولة الأولى تسأل: أهو مشغول أم متروك؟ وبلا
                # هذا السؤال ينتظر الحيُّ الميّتَ حتى المهلة، كل
                # دورة، إلى الأبد.
                if _reclaim_if_stale(lock_path, config.lock_stale_seconds):
                    continue
                time.sleep(0.05)
        if not acquired:
            yield False
            return
        yield True
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if acquired:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        tlock.release()
