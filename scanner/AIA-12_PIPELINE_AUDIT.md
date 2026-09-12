# AIA-12 Pipeline Audit

Evidence-based trace of the production ID chain. No fabricated paths.

## End-to-end flow

```
Market Data Sync (MD-01 worker)
  → Scan (management/commands/scan.py)
  → Recommendation (reco on ScanResult)
  → PIT Snapshot (PointInTimeSnapshotService.capture_from_scan_row)
  → Trade (trades.open_from_reco)
  → Trade Close (settlement → production_hooks.on_trade_settled)
  → Dataset V3 (predictive/dataset_v3.build_dataset_v3)
  → Training (predictive/v3_retrain.maybe_trigger_v3_retrain)
  → Quality Gates (predictive/quality_gates — unchanged)
  → Registry (CANDIDATE_FOR_PROMOTION | NOT_PROMOTED only)
  → PredictionAdapter (ACTIVE-only)
  → Fusion (PREDICTION_UNAVAILABLE when no ACTIVE)
```

## ID creation & propagation

| ID | Created where | Propagated to | Notes |
|----|---------------|---------------|-------|
| `scan_id` | `ScanRun.pk` on scan start | `ScanResult.run` FK | Integer PK; not on PIT contract |
| `fs_*` (`feature_snapshot_id`) | Legacy feature store write during scan | `ScanResult.feature_snapshot_id`, `Trade.feature_snapshot_id`, PIT `legacy_snapshot_id` | Primary join key historically |
| `recommendation_id` | `make_recommendation_id(legacy=fs_*)` → `reco_{fs_*}` | PIT snapshot field | Must match ScanResult linkage |
| `pit_*` (`snapshot_id`) | PIT store on capture | Index `by_legacy[fs_*]→pit_*`; AIA-12 also persists on ScanResult/Trade | Immutable after write |
| `trade_id` | `Trade.pk` | Dataset V3 rows | Outcome labels only — never rewrite PIT features |
| `dataset_fingerprint` | Hash of eligible trade+pit IDs, feature version, schema, label def, config | V3 retrain state | Blocks duplicate trains |
| `model_id` | Trainer / `run_v3_experiment` | Registry metadata | Never auto-ACTIVE |

## Linkage loss points (verified)

1. **Silent PIT failure in scan** — `scan.py` wrapped `capture_from_scan_row` in bare `except: pass`. Result: `fs_*` saved on ScanResult while no `pit_*` / `by_legacy` entry. **AIA-12 fix:** log failure; persist `pit_snapshot_id` / `recommendation_id` when capture succeeds.

2. **Trade `get_or_create` defaults-only** — If a trade row already exists without `feature_snapshot_id`, conflict path never backfills. **AIA-12 fix:** backfill empty linkage fields on existing rows (does not alter outcomes).

3. **Coverage gate** — Dataset V3 rejects `coverage < 0.70` as `low_snapshot_coverage`. Correct behavior; legacy FAILED (~64% avg) stay ineligible.

4. **Legacy reconstruction honesty** — Missing legacy → `HISTORICAL_SNAPSHOT_UNAVAILABLE`; never fabricate. Excluded from eligible V3 rows.

5. **Dual training stacks** — Orchestrator still trains V2 by default; V3 evaluate-only via `v3_retrain`. PredictionAdapter remains ACTIVE-only across both.

6. **Advisor payload `trade_id` misuse** — Some advisor paths used `ScanResult.id` as trade id (shadow/advisory). Does not break V3 eligibility chain; document only — trading logic untouched.

## Immutability

- PIT features frozen at decision time T0.
- Trade entry T1 / close T2 append outcome externally only.
- Close path must never rewrite PIT feature values.

## Accumulation blocker (pre AIA-12)

Insufficient **PIT-linked high-quality closed trades** for Dataset V3 (≥100 eligible). New enriched capture path can reach 36/36 when engines available; automatic accumulation + readiness/training trigger is the operational fix.

## Safety

No changes to order placement, risk, scanner decision rules, or trade eligibility. PIT / training / LLM failures must not break trading.
