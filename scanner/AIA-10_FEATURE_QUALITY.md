# AIA-10 Feature Quality

## V3 Registry

- **36** spec features across 9 categories
- Audit: `audit_features_v3()` in `scanner/predictive/feature_audit.py`

## Classifications

| Status | Meaning |
|--------|---------|
| ACTIVE | coverage ≥ 20%, non-constant |
| LOW_COVERAGE | availability < 20% |
| CONSTANT | zero variance — rejected for training |
| HIGH_MISSING | missing rate > 80% |
| LEAKAGE_REJECTED | failed provenance/timestamp check |
| UNAVAILABLE | no source data |

## Constant Feature Policy

Zero-variance features are **recorded and rejected** — not silently dropped. V1/V2 known constants: `market_enc`, `side_buy` (documented in AIA-08).

## Redundancy

Use existing `scanner/feature_intelligence` redundancy analysis. V3 does not auto-remove correlated features — report first, human/feature-selection pipeline decides.

## Runtime Target

New runtime coverage ≥ **80%** (warning below). Preferred ≥ **95%**.
