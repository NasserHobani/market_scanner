# -*- coding: utf-8 -*-
"""Per-symbol/timeframe sync locks — prevent concurrent writers."""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_META = threading.Lock()


def _key(market: str, symbol: str, timeframe: str) -> str:
    return f"market_sync:{market}:{symbol}:{timeframe}"


def _thread_lock(key: str) -> threading.Lock:
    with _META:
        if key not in _THREAD_LOCKS:
            _THREAD_LOCKS[key] = threading.Lock()
        return _THREAD_LOCKS[key]


@contextmanager
def sync_lock(
    market: str,
    symbol: str,
    timeframe: str,
    *,
    config: MarketSyncConfig = DEFAULT_SYNC_CONFIG,
    timeout: float = 30.0,
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
