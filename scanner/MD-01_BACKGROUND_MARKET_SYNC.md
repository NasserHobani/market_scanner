# MD-01 — Background Market Data Synchronization & Fast Scanner

**Status:** Implemented  
**Date:** 2026-08-11

---

## Architecture

```
Exchange
  → MarketDataSyncService (background daemon)
  → scanner.storage (CSV/Parquet OHLC — single source of truth)
  → Scan / Chart / Settlement / AI (consumers)
```

Reuses existing `storage.merge` / `bars_needed` / adapters / Django daemon-thread pattern.  
**Does not** introduce Celery/Redis or a second candle store.

---

## What changed

| Component | Path |
|-----------|------|
| Sync service | `scanner/market_sync/` |
| Background worker | `web/dashboard/market_sync_worker.py` |
| Startup hook | `web/dashboard/apps.py` (`MARKET_DATA_SYNC=1`) |
| Status API | `GET /api/market-data/sync/status/` |
| Manual sync API | `POST /api/market-data/sync/` |
| Latest candle poll | `GET /api/chart/<market>/<symbol>/latest/` |
| Scan freshness gate | `scan.py` + `api_scan_now` + `scheduler.run_scan(cached=True)` |
| UI | Badge in `base.html`; buttons «فحص السوق الآن» / «مزامنة البيانات» |

---

## Scan Now behavior (critical)

**Before:** Sync history → analyze → scan  

**After:**

1. Freshness gate (`scan_freshness_gate`)
2. If fresh → scan from disk (`--cached`)
3. If slightly stale → incremental refresh → scan
4. If critical → `MARKET_DATA_STALE` (no pretend-current analysis)

Full historical download is **not** part of Scan Now (`--full` remains available for ops only).

---

## Freshness statuses

| Status | Meaning |
|--------|---------|
| FRESH | within `fresh_max_bars` of expected candle |
| STALE | up to `stale_max_bars` behind |
| CRITICAL | older than stale threshold |
| ERROR | exchange/API failure |
| MISSING | no local file |

Configurable in `scanner/market_sync/config.py`.

---

## Performance

| Path | Behavior |
|------|----------|
| Background sync | Incremental only after bootstrap; bounded workers (≤10) |
| Scan with fresh cache | Network fetch skipped (`timing["cached"]`) |
| Chart | Reads local store; bootstrap only if <60 bars; latest poll every ~45s |
| AI | Never triggers market sync |

---

## PIT / AI compatibility

- Sync writes OHLC only — does not mutate PIT snapshots
- Closed bars remain append-only via `merge(..., keep="last")` on timestamp index
- Claude/Qwen continue to consume UDP + PIT; no sync coupling

---

## Tests

```
tests_market_data_background_sync.py  25/25 PASS
tests_ai_aia106_enrichment.py         39/39 PASS
tests_ai_aia105_runtime.py            PASS (regression)
```

Verification:

```
python scripts/verify_background_market_sync.py
```

---

## Env flags

| Variable | Default | Role |
|----------|---------|------|
| `MARKET_DATA_SYNC` | `1` | Start background worker |
| `MARKET_SYNC_MARKETS` | `AUTO_SCAN_MARKETS` / `crypto` | Markets to sync |

---

## Remaining ops notes

1. First boot: worker bootstraps missing symbol/TF files once, then incremental.
2. If many pairs show CRITICAL in the badge, press **مزامنة البيانات** once (or wait for the worker cycle).
3. Indicator incremental cache is deferred — scoring still recomputes from DF (same as before); candle sync is the MD-01 scope.
4. Do not run a second candle updater — settlement still uses `_fresh_candles` for live trades only (narrow scope).

---

## Definition of done

- [x] Background sync runs automatically  
- [x] Incremental sync + open-candle update + no duplicates  
- [x] Freshness visible (API + navbar badge)  
- [x] Chart reads synchronized data + latest poll  
- [x] Scanner uses cached data when fresh  
- [x] Scan does not full-sync  
- [x] Manual sync remains for recovery  
- [x] PIT immutable / AI does not sync  
- [x] Locks, backoff, metrics, events  
- [x] Tests + verify script  

**Principle:** The user should never need to press sync before every scan. Sync is infrastructure; scan is analysis.
