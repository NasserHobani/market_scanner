# AIA-12 Runtime Accumulation Report

## Objective

Automatically accumulate high-quality PIT snapshots and closed trades toward Dataset V3 readiness (≥100 eligible rows; preferred ≥200).

## Verified pipeline behavior

| Step | Behavior |
|------|----------|
| Scan | Enriched PIT capture; logs failures (no silent `pass`) |
| ScanResult | Persists `feature_snapshot_id`, `pit_snapshot_id`, `recommendation_id` |
| Trade open | Copies PIT linkage + `decision_timestamp` + `feature_version` |
| Trade close | Outcomes only — PIT features immutable |
| Settlement hook | `schedule_if_ready_async()` — trains only when ready |
| Legacy | No fabrication; `HISTORICAL_SNAPSHOT_UNAVAILABLE` excluded |

## Metrics (separate historical vs runtime)

- `legacy_total` / `legacy_reconstructed` / `legacy_unavailable`
- `runtime_new` / `runtime_good` / `runtime_partial` / `runtime_failed`
- Runtime coverage % (not mixed with legacy average)

## Current runtime evidence (verify_aia12)

- PIT total: 378 (mostly legacy FAILED; mean coverage ~64.4%)
- GOOD: 0 · PARTIAL: 15 · FAILED: 363
- V3 eligible: **0 / 100** — accumulating
- Prediction: **UNAVAILABLE** (correct — no ACTIVE model)
- Fusion: **PREDICTION_UNAVAILABLE**

## Note

AIA-11 proved the **new** capture path can reach ≥80% (up to 36/36). Existing store rows remain mostly pre-enrichment. Progress depends on new scans + closed linked trades, not rewriting immutable legacy snapshots.
