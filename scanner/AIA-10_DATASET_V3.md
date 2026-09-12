# AIA-10 Dataset V3

## Builder

`scanner/predictive/dataset_v3.py` → `build_dataset_v3()`

Each row:
- `features` — V3 numeric vector from `pit_*` snapshot
- `provenance` — full audit trail
- `label_binary_win` — independent outcome label
- `_meta` — symbol, timeframe, snapshot status

## Manifest Fields

`dataset_id`, `dataset_version` (3.0.0), `feature_schema_hash`, `row_count`, `eligible_count`, `rejected_count`, `date_range`, `symbols`, `timeframes`, `label_distribution`, `fingerprint`

## Reproducibility

Fingerprint hashes trade IDs + signal times + pit snapshot IDs.

## Current State

With ~1.5% historical snapshot linkage, eligible V3 rows remain low until:
1. Runtime scans accumulate `pit_*` snapshots
2. Trades opened after deploy link to snapshots
3. Historical `fs_*` reconstruction runs via `batch_reconstruct()`

## Quality

`dataset_v3_quality()` adds concentration warnings (`DATASET_CONCENTRATION_WARNING` if >90% one symbol/TF).
