# AIA-12 Quality Gate Report

## Policy

**Quality gates were not changed.**

Required for candidate:

- OOS improvement ≥ 2%
- Walk-forward PASS
- Calibration PASS
- Expectancy PASS
- Leakage PASS
- Dataset quality PASS

Any failure → `NOT_PROMOTED` (valid successful pipeline outcome).

## ACTIVE-only prediction

`PredictionAdapter` remains ACTIVE-only. No fallback to candidate / not_promoted / latest.

If no ACTIVE model:

- `prediction_available = false`
- reason `no_active_model`
- Fusion: `PREDICTION_UNAVAILABLE`

## Engineering note

Optimizing for a trustworthy pipeline — not for forcing an ACTIVE model. After 100+ eligible trades, if LightGBM loses to baseline, keep Prediction UNAVAILABLE and report evidence.
