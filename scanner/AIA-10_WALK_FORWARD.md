# AIA-10 Walk-Forward

## Implementation

Uses existing `PredictiveEngine.walk_forward()` with `TrainingConfig(feature_version="3.0.0")`.

Reports via `walk_forward_report()`:
- Per-fold train/validation/test sizes
- Accuracy per fold
- mean / median / stdev / min / max

## Requirement

Model must demonstrate stability across folds — single-fold success is insufficient.

## Current State

Walk-forward not meaningful until Dataset V3 has ≥20 eligible rows with provenance-valid features.

Run: `python scripts/verify_aia10_features.py` after sufficient trade/snapshot accumulation.
