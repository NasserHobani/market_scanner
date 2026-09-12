# -*- coding: utf-8 -*-
"""File-based lock for concurrent learning cycles — no database required."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_LOCK_TIMEOUT_SEC = 30
DEFAULT_POLL_SEC = 0.05


def default_lock_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / ".learning_cycle.lock"


@contextmanager
def learning_cycle_lock(path: Path | None = None,
                        timeout: float = DEFAULT_LOCK_TIMEOUT_SEC) -> Iterator[None]:
    """Exclusive lock via atomic lock-file creation (works on Windows and Unix)."""
    lock_path = path or default_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"learning cycle lock timeout: {lock_path}")
            time.sleep(DEFAULT_POLL_SEC)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
