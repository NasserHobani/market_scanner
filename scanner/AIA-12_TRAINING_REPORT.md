# AIA-12 Training Report

## Trigger

`scanner/predictive/v3_retrain.py`

- Lock prevents concurrent duplicate jobs
- Dataset fingerprint skips identical retrain
- Default: run only when `eligible >= 100`
- After a completed evaluation: require `+20` eligible (unless FV change / `force=True`)
- Async via settlement `schedule_if_ready_async` — never blocks scanner/trading/Claude/Qwen

## Evaluation

Uses existing `run_v3_experiment`:

- Naive majority + rule baselines
- V3 LightGBM
- OOS, walk-forward, calibration, expectancy
- Unchanged quality gates

## Lifecycle

Possible results: `NOT_PROMOTED` | `CANDIDATE_FOR_PROMOTION`

- **Never** auto-promote to ACTIVE
- Manual/API promotion only

## Manual

`POST /api/prediction/train/` forces V3 evaluate (`force=True`) in addition to V2 orchestrator path.
