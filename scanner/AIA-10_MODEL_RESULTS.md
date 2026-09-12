# AIA-10 Model Results

## Experiment Runner

`run_v3_experiment()` in `scanner/predictive/dataset_v3.py`

Compares:
1. Naive majority baseline
2. Historical win-rate baseline
3. Rule-based score baselines
4. LightGBM V3 (chronological train/test)
5. Walk-forward validation

## Known Production State (pre-V3 data volume)

| Metric | Value |
|--------|-------|
| Baseline (V2 era) | ~51.6% |
| Best OOS (V1/V2) | ~45.2% |
| V1/V2 promotion | NOT_PROMOTED |
| V3 promotion | NOT_RUN / NOT_PROMOTED (insufficient PIT-linked samples) |

## Quality Gates

Unchanged from AIA-08:
- No leakage
- Minimum sample size
- OOS improvement over baseline (+2%)
- Walk-forward stability
- Calibration
- Expectancy

## Prediction Status

**UNAVAILABLE** — correct. No model passed quality gates.

## Honest Conclusion

V3 infrastructure is production-ready; model promotion requires more point-in-time linked closed trades. Do not promote until gates pass on real V3 dataset.
