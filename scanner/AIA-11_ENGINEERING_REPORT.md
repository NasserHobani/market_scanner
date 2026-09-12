# AIA-11 Engineering Report

## Coverage

| Path | Coverage |
|------|----------|
| Pre-enrichment ScoreResult only | **72.2%** (26/36) |
| After AIA-11 enrichment (engines available) | **100%** (36/36) |
| Existing store average (legacy captures) | **64.4%** (378 snaps; many pre-AIA-11) |
| Target | ≥80% new captures (prefer ≥90%) |

New scan-path captures with ScoreResult + collectors reach ≥80% (tests: PASS).  
Legacy snapshots remain until re-scanned — do not backfill with future data.

## Dataset

- Eligible (verify env): **0** PIT-linked closed trades loaded
- Train gate (≥100): **not ready**
- Smoke (≥20): **not ready**

## Prediction

- Status: **UNAVAILABLE**
- ACTIVE model: **NO**
- Quality gates: **preserved** (no auto-promotion)

This is a successful outcome of the gates: no weak model entered production.

## What changed

P0 feature honesty fixes:
- `atr_percentile` from ATR series at decision bar
- `volume_participation` from spike/cmf/mfi
- BOS/CHOCH counts include zero
- `knowledge_confidence` from reco confidence
- no silent `side_buy=buy` default
- volatility_regime ignores channel `"—"`
- `missing_feature_reasons` + category coverage
- V3 eligibility requires coverage ≥70%
- async V3 retrain trigger (lock + fingerprint; never ACTIVE)

## Remaining blockers

1. Live scans with enrichment to replace PARTIAL/FAILED legacy snaps
2. ≥100 PIT-linked closed trades for real V3 training
3. Explicit `promote_model` only if CANDIDATE

## Exact next sprint

**AIA-12** — Accumulate enriched runtime snapshots + closed trades until Dataset V3 ≥100 eligible, then evaluate LightGBM under unchanged gates. Keep Prediction UNAVAILABLE until evidence warrants CANDIDATE + explicit promotion.
