# -*- coding: utf-8 -*-
"""Background market-data sync worker — same daemon-thread pattern as settlement."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_state = {
    "running": False,
    "thread_started": False,
    "last_cycle": None,
    "last_error": None,
    "last_summary": None,
    "cycle_count": 0,
}
_lock = threading.Lock()


def status() -> dict:
    return dict(_state)


def is_running() -> bool:
    return bool(_state["running"])


def run_once(markets: list[str] | None = None, *, force: bool = False) -> dict:
    """One sync cycle across configured markets."""
    from scanner.market_sync import get_service
    from scanner.market_sync import status_store
    from scanner.market_sync.freshness import utc_now_iso

    markets = markets or _default_markets()
    if not _lock.acquire(blocking=False):
        # ``busy``: ازدحامٌ لا فشل — انظر scheduler.run_scan
        return {"ok": False, "busy": True,
                "reason": "دورة مزامنة أخرى جارية"}

    _state.update(running=True, last_error=None)
    started = time.time()
    try:
        svc = get_service()
        summaries = []
        for market in markets:
            try:
                summaries.append(svc.sync_market(market, force=force))
            except Exception as exc:  # noqa: BLE001
                log.exception("market sync failed: %s", market)
                summaries.append({"market": market, "ok": False, "reason": str(exc)[:200]})
        elapsed = round(time.time() - started, 2)
        ok = sum(int(s.get("successful") or 0) for s in summaries)
        failed = sum(int(s.get("failed") or 0) for s in summaries)
        summary = {
            "ok": True,
            "markets": markets,
            "successful": ok,
            "failed": failed,
            "elapsed_sec": elapsed,
            "details": [
                {
                    "market": s.get("market"),
                    "symbols": s.get("symbols"),
                    "successful": s.get("successful"),
                    "failed": s.get("failed"),
                }
                for s in summaries
            ],
        }
        _state["last_summary"] = summary
        _state["cycle_count"] = int(_state.get("cycle_count") or 0) + 1
        _state["last_cycle"] = utc_now_iso()
        status_store.update_worker({
            "running": True,
            "last_cycle": _state["last_cycle"],
            "last_successful_sync": utc_now_iso() if ok else None,
            "last_error": None,
            "cycle_count": _state["cycle_count"],
            "last_summary": summary,
        })
        return summary
    except Exception as exc:  # noqa: BLE001
        err = str(exc)[:300]
        _state["last_error"] = err
        status_store.update_worker({"last_error": err, "running": True})
        return {"ok": False, "reason": err}
    finally:
        _state["running"] = False
        _lock.release()


def _default_markets() -> list[str]:
    raw = os.environ.get("MARKET_SYNC_MARKETS") or os.environ.get("AUTO_SCAN_MARKETS", "crypto")
    return [m.strip() for m in raw.split(",") if m.strip()]


def _loop_interval(markets: list[str]) -> float:
    """Use the shortest configured TF interval across markets."""
    from django.conf import settings
    from scanner.config import load_market
    from scanner.market_sync import DEFAULT_SYNC_CONFIG

    intervals = []
    for m in markets:
        try:
            cfg = load_market(settings.SCANNER_CONFIG_DIR / f"{m}.yaml")
            for tf in cfg.timeframes:
                intervals.append(DEFAULT_SYNC_CONFIG.interval_seconds.get(tf, 300))
        except Exception:  # noqa: BLE001
            intervals.append(300)
    # Also refresh faster TFs periodically
    intervals.append(DEFAULT_SYNC_CONFIG.interval_seconds.get("1h", 300))
    return float(min(intervals) if intervals else 300)


def _loop(markets: list[str], initial_delay: float = 5.0) -> None:
    time.sleep(initial_delay)
    from scanner.market_sync import status_store
    from scanner.market_sync.freshness import utc_now_iso

    status_store.update_worker({
        "thread_started": True,
        "started_at": utc_now_iso(),
        "markets": markets,
    })
    log.info("market-data sync worker started: %s", ", ".join(markets))

    while True:
        try:
            interval = _loop_interval(markets)
            next_at = datetime.now(timezone.utc).timestamp() + interval
            status_store.update_worker({
                "next_sync": datetime.fromtimestamp(next_at, tz=timezone.utc).isoformat(),
            })
            run_once(markets)
        except Exception:  # noqa: BLE001
            log.exception("market sync loop error")
            _state["last_error"] = "loop error"
            time.sleep(60)
            continue
        sleep_for = max(30.0, _loop_interval(markets))
        time.sleep(sleep_for)


def start(markets: list[str] | None = None) -> bool:
    if _state["thread_started"]:
        return False
    markets = markets or _default_markets()
    if not markets:
        return False
    _state["thread_started"] = True
    thread = threading.Thread(
        target=_loop, args=(markets,), name="market-data-sync", daemon=True,
    )
    thread.start()
    log.info("market-data sync thread launched: %s", ", ".join(markets))
    return True
