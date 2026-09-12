# Predictive Modeling Platform

Extensible prediction architecture for the CS Edge AI Platform. **LightGBM is the first plugin — not the only one.**

## Purpose

Train, evaluate, version, and serve predictive models on versioned ML datasets. Predictions are analytical signals only — no buy/sell recommendations, no trade execution.

## Architecture

```
scanner/predictive/
├── plugins/
│   ├── base.py              # PredictiveModel interface
│   └── lightgbm.py          # LightGBM plugin (sklearn fallback)
├── trainer.py               # Generic trainer
├── evaluator.py             # Classification, regression, trading metrics
├── predictive_engine.py     # Orchestrator + walk-forward validation
├── prediction.py            # PredictionResult types
├── inference.py             # Inference engine
├── model_metadata.py        # Versioned metadata
├── model_registry.py        # Append-only registry
├── model_store.py           # Save/load/list/archive/delete
├── model_loader.py          # Model loader
├── interfaces.py            # Protocols
├── services.py              # PredictiveService
└── README.md
```

## Plugin Architecture

Every model plugin implements `PredictiveModel`:

```python
class PredictiveModel(ABC):
    def train(X, y, feature_names, hyperparameters, task_type) -> TrainResult
    def predict(X, feature_names) -> list[float]
    def predict_proba(X, feature_names) -> list[float] | None
    def evaluate(X, y, feature_names, task_type) -> dict
    def save(path) -> None
    @classmethod
    def load(path) -> PredictiveModel
```

Future plugins (XGBoost, CatBoost, RandomForest, TabPFN) register via `Trainer.register_plugin()` — no consumer code changes.

## Training Lifecycle

```
ML Dataset rows (from AI-05)
    → TrainingConfig (features, label, plugin, hyperparameters)
    → Trainer.train() → plugin.train()
    → Optional walk-forward validation
    → ModelStore.save() + ModelRegistry.register()
```

Every training run links to:
- `dataset_id` (ML Foundation)
- `feature_analysis_id` (Feature Intelligence)
- `research_experiment_id` (Research Engine)

## Prediction Lifecycle

```
Feature vector (dict)
    → ModelLoader.load(model_id)
    → InferenceEngine.predict()
    → PredictionResult (prediction, probability, confidence, explainability)
```

Prediction output includes disclaimer: analytical signal only, not a trading recommendation.

## Walk-Forward Validation

Time-aware validation — **no random shuffle**:

| Mode | Description |
|------|-------------|
| `rolling` | Fixed train window slides forward |
| `expanding` | Train window grows from start |
| `walk_forward` | Train on [0..t], test on [t+1..t+test_size] |

## Model Registry

Each model records:
- Model ID (`mdl_*`), plugin, fingerprint
- Dataset ID, feature analysis ID, research experiment ID
- Hyperparameters, evaluation summary, walk-forward summary
- Feature columns, label column, task type, status

Storage layout:
```
data/predictive/models/{model_id}/
    model.pkl
    metadata.json
data/predictive/registry.jsonl
```

## Public API

```python
from scanner.predictive import PredictiveService

svc = PredictiveService()

# Train
artifact = svc.train(
    rows=dataset_rows,
    feature_columns=["rsi", "score", "htf_bias"],
    label_column="label_binary_win",
    dataset_id="mls_abc",
    feature_analysis_id="fia_xyz",
    research_experiment_id="rex_123",
    run_walk_forward=True,
)

# Predict (analytical signal only)
result = svc.predict(artifact.model_id, {"rsi": 55.0, "score": 72.0, "htf_bias": 1})

# Evaluate
metrics = svc.evaluate(artifact.model_id, test_rows)

# Walk-forward only
wf = svc.walk_forward(rows, feature_columns=["rsi", "score"], train_size=20, test_size=5)

# Registry
models = svc.list_models()
registry = svc.registry(limit=20)
```

## Evaluation Metrics

| Category | Metrics |
|----------|---------|
| Classification | Accuracy, Precision, Recall, F1, ROC AUC |
| Regression | RMSE, MAE, R² |
| Trading | Expectancy, Profit Factor, Avg R, Win Rate |

All metrics are deterministic with no hidden calculations.

## Future AI Assistant Integration

Sprint AI-07 can use predictions as evidence:
- PredictionResult feeds into Reasoning context as analytical evidence
- Model registry links predictions to research experiments
- Walk-forward results inform confidence in model signals
- Feature explainability metadata supports evidence traces

Predictions do NOT directly generate buy/sell — that decision remains with Reasoning/Recommendation layers in future sprints.

## Rules

- Do NOT modify Knowledge, Similarity, Pipeline, Research, ML Foundation, or Feature Intelligence
- Do NOT generate trading recommendations
- Do NOT automatically execute trades
- Every prediction must be reproducible
- Every model must be versioned
- Plugin replacement must not change consumer code
