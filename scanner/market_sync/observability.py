# -*- coding: utf-8 -*-
"""Sync events and metrics — append-only JSONL + in-memory counters."""
from __future__ import annotations

import json
import statistics
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any

from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig
from .freshness import utc_now_iso

_METRICS_LOCK = threading.Lock()
_METRICS: dict[str, Any] = {
    "sync_count": 0,
    "successful_syncs": 0,
    "failed_syncs": 0,
    "retry_count": 0,
    "candles_inserted": 0,
    "candles_updated": 0,
    "candles_closed": 0,
    "skipped_busy": 0,
    "latencies_ms": deque(maxlen=500),
}


def reset_metrics() -> None:
    with _METRICS_LOCK:
        for k in list(_METRICS.keys()):
            if k == "latencies_ms":
                _METRICS[k] = deque(maxlen=500)
            else:
                _METRICS[k] = 0


def bump(name: str, n: int = 1) -> None:
    with _METRICS_LOCK:
        _METRICS[name] = int(_METRICS.get(name, 0)) + n


def record_latency(ms: float) -> None:
    with _METRICS_LOCK:
        _METRICS["latencies_ms"].append(float(ms))


def metrics_snapshot() -> dict[str, Any]:
    with _METRICS_LOCK:
        lats = list(_METRICS["latencies_ms"])
        out = {k: v for k, v in _METRICS.items() if k != "latencies_ms"}
    out["average_sync_latency"] = round(statistics.mean(lats), 2) if lats else None
    if lats:
        lats_sorted = sorted(lats)
        out["p95_sync_latency"] = round(lats_sorted[min(len(lats_sorted) - 1, int(len(lats_sorted) * 0.95))], 2)
    else:
        out["p95_sync_latency"] = None
    return out


# ═══ سجلٌّ بلا حدّ ليس سجلّاً بل تسريباً ═══
#
# بلغ ``events.jsonl`` **٣٠٥ ميغابايت**: ثلاثة أسطر لكل زوج في كل
# دورة، وألفان ومئة زوج، ودورة كل بضع دقائق. ولا شيء يحذف.
#
# والضرر مضاعف: قرصٌ يمتلئ، وقراءةُ السجلّ للتشخيص تصير مستحيلة —
# فالأداة التي وُضعت لتُفهم بها الأعطال صارت هي نفسها عطلاً.
#
# التدوير بالحجم لا بالزمن: الزمن يعتمد على معدّل الأحداث وهو
# متغيّر، والحجم هو ما يهمّ القرص فعلاً. ونسخة واحدة سابقة تكفي:
# التشخيص يحتاج ما قبل العطل بقليل لا تاريخ الشهر.
MAX_EVENT_BYTES = 32 * 1024 * 1024
_LAST_SIZE_CHECK = [0.0]


def _rotate(path: Path) -> None:
    """يُدوِّر السجلّ عند تجاوز الحدّ. لا يرمي أبداً."""
    import time as _t

    # الفحص مرّةً كل عشر ثوانٍ لا في كل سطر: ``stat`` رخيصة لكن
    # آلاف النداءات في الدقيقة ليست كذلك.
    now = _t.time()
    if now - _LAST_SIZE_CHECK[0] < 10.0:
        return
    _LAST_SIZE_CHECK[0] = now
    try:
        if not path.exists() or path.stat().st_size < MAX_EVENT_BYTES:
            return
        old = path.with_suffix(path.suffix + ".1")
        try:
            old.unlink(missing_ok=True)
        except OSError:
            return
        path.replace(old)
    except OSError:
        pass          # التدوير رفاهية؛ فشلُه لا يُسقط المزامنة


def log_event(
    event: str,
    *,
    market: str = "",
    symbol: str = "",
    timeframe: str = "",
    status: str = "",
    candle_timestamp: str = "",
    latency_ms: float | None = None,
    extra: dict[str, Any] | None = None,
    config: MarketSyncConfig = DEFAULT_SYNC_CONFIG,
) -> None:
    row = {
        "event": event,
        "timestamp": utc_now_iso(),
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": status,
        "candle_timestamp": candle_timestamp,
        "latency_ms": latency_ms,
    }
    if extra:
        row["extra"] = extra
    path = Path(config.events_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate(path)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def recent_events(limit: int = 100, *, config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> list[dict]:
    path = Path(config.events_path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
