# Machine Learning Foundation

Infrastructure-only module for ML data preparation. **No model training. No predictions.**

## Purpose

Prepare reproducible, versioned ML datasets from knowledge snapshots and trade outcomes. This module is the foundation for future LightGBM/XGBoost integration.

## Architecture

```
scanner/ml/
├── feature_registry.py    # Feature schema definitions
├── feature_vector.py      # Knowledge → feature vectors
├── feature_store.py       # Join snapshots + trades
├── label_store.py         # Standardized label extraction
├── dataset_registry.py    # Versioned dataset registry
├── dataset_export.py      # CSV / JSON / Parquet (interface)
├── validation.py          # Schema, feature, label validation
├── preprocessing.py       # Deterministic transforms (no fitting)
├── metadata.py            # Version constants + metadata types
├── interfaces.py          # Protocols
├── services.py            # MLFoundationService public API
├── dataset.py             # (legacy) Django training data loader
├── train_lgbm.py          # (legacy) — not used by foundation
└── runtime.py             # (legacy) — not used by foundation
```

## Feature Lifecycle

1. **Definition** — `MLFeatureRegistry` holds schema for each feature (name, type, source, version)
2. **Extraction** — `FeatureVectorBuilder` converts `FeatureSnapshot` dicts to typed vectors
3. **Join** — `FeatureStore` joins snapshots to trade rows via `feature_snapshot_id`
4. **Preprocessing** — `PreprocessingPipeline` applies fixed encodings and fill values
5. **Validation** — `DatasetValidator` checks schema, missing features, invalid labels
6. **Export** — `DatasetExporter` writes CSV/JSON with metadata sidecar

## Dataset Lifecycle

```
Provide snapshots + trades
    → build_dataset()
    → preprocess (deterministic)
    → validate
    → register in data/ml/datasets/registry.jsonl
    → export_dataset() → CSV / JSON / Parquet schema
```

Each registered dataset records:
- Dataset ID (`mls_*`)
- Schema version, feature version, label version
- Research experiment ID (optional link to AI-04)
- Row count, feature count, label columns
- Fingerprint for reproducibility

## Label Lifecycle

| Label | Type | Source |
|-------|------|--------|
| `label_winner` | Binary | `status == won` |
| `label_loser` | Binary | `status == lost` |
| `label_break_even` | Binary | `r_multiple == 0` |
| `label_r_multiple` | Regression | `r_multiple` |
| `label_binary_win` | Binary | `r_multiple > 0` |
| `label_outcome_class` | Multiclass | winner/loser/break_even |

Labels are deterministic. New labels can be registered via `LabelStore.register()` without redesign.

## Versioning

| Constant | Value | Scope |
|----------|-------|-------|
| `ML_FOUNDATION_VERSION` | 1.0.0 | Module version |
| `SCHEMA_VERSION` | 1.0.0 | Dataset schema |
| `FEATURE_VERSION` | 1.0.0 | Feature registry |
| `LABEL_VERSION` | 1.0.0 | Label definitions |

Version mismatches produce validation warnings/errors.

## Public API

```python
from scanner.ml import MLFoundationService

svc = MLFoundationService()

# Build dataset (caller provides all data — no raw storage access)
dataset = svc.build_dataset(
    feature_snapshots=snapshots,
    trade_rows=trades,
    outcome_rows=outcomes,          # optional
    research_experiment_id="rex_abc",  # optional link to research
)

# Export
svc.export_dataset(dataset, "data/ml/exports/train.csv", fmt="csv")
svc.export_dataset(dataset, "data/ml/exports/train.json", fmt="json")

# Validate
result = svc.validate_dataset(dataset)

# List available features and labels
features = svc.list_features()
labels = svc.list_labels()

# Registry history
history = svc.dataset_history(limit=20)
```

## Preprocessing Rules

- **No fitting** — all transforms use fixed constants
- **Missing numerics** → fill with `0.0`
- **Missing categoricals** → fill with `-1`
- **Grade encoding** — `—=0, C=1, B=2, A=3`
- **Market encoding** — `crypto=0, forex=1, stocks=2, commodities=3`
- **RSI clipping** — `[0, 100]`
- **Component clipping** — `[-1, 1]`

## Future LightGBM Integration

Sprint AI-06 can add:

```python
# Planned (not implemented)
from scanner.ml.train import LightGBMTrainer

trainer = LightGBMTrainer()
trainer.fit(dataset, target="label_binary_win")
trainer.evaluate(oos_dataset)
```

Foundation provides:
- Versioned datasets with metadata
- Deterministic feature vectors matching `FeatureSnapshot.to_vector()`
- Binary and regression labels ready for `lgb.Dataset`
- Export to CSV compatible with existing `train_lgbm.py`

## Future XGBoost Integration

Same dataset format applies. `MLDataset.to_dicts()` produces flat rows suitable for `xgb.DMatrix`. Feature column order is stable and recorded in export metadata.

## Rules

- Do NOT train models in this module
- Do NOT modify Research Engine, Pipeline, Knowledge, or Similarity layers
- Every dataset must be reproducible from stored metadata
- Every feature must be versioned
- Every export must include metadata sidecar
