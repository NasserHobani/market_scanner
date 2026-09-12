# AIA-12 Dataset Readiness Report

## API

`GET /api/prediction/readiness/`

Returns:

- `eligible_rows`, `required_rows` (100), `progress_percent`
- Runtime PIT counts (good / partial / failed)
- `linked_closed_trades`, `leakage_rejected`
- `dataset_fingerprint`, `ready_for_training`, `reason`, `status`
- Legacy vs runtime partitions
- Alerts (coverage, stall, linkage, leakage) — **not** for normal `NOT_PROMOTED`

## Status vocabulary

| Status | Meaning |
|--------|---------|
| COLLECTING | eligible &lt; 100 |
| READY_FOR_TRAINING | threshold reached |
| TRAINING | job running |
| COMPLETED / NOT_PROMOTED / CANDIDATE_FOR_PROMOTION | post-eval |
| FAILED | train error (recoverable) |

## Thresholds

- Smoke: 20 (measurement only)
- Train: **100** (default automatic trigger)
- Preferred: 200+
- After success: **+20** new eligible rows (or feature-version change / manual force)

## Module

`scanner/predictive/dataset_readiness.py`
