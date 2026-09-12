# AIA-10 Leakage Report

## Checks

1. **Forbidden columns** — outcome fields, `r_multiple`, post-trade meta
2. **Timestamp ordering** — `feature_timestamp <= decision_timestamp`
3. **Provenance** — every V3 feature has `source`, `source_timestamp`, `calculation_version`
4. **Provenance timestamps** — `source_timestamp <= decision_timestamp`

## Adversarial Tests

`adversarial_leakage_tests()` in `scanner/predictive/leakage_detector.py`:

| Test | Expected |
|------|----------|
| future RSI | LEAKAGE_DETECTED |
| future ATR | LEAKAGE_DETECTED |
| future volume | LEAKAGE_DETECTED |
| future BOS | LEAKAGE_DETECTED |
| future similarity | LEAKAGE_DETECTED |
| future outcome in features | LEAKAGE_DETECTED |

## Dataset V3

Rows with leakage violations are **rejected** with reason `leakage:...`. Dataset build does not include outcome columns in feature dict.

## Result

Unit tests: **PASS** (23/23 AIA-10 tests including adversarial suite).

Production dataset: requires sufficient PIT-linked closed trades for full validation.
