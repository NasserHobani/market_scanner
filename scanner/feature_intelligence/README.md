# Feature Intelligence Engine

Deterministic feature analytics for the CS Edge AI Platform. **No model training. No ML-based importance. No AI.**

## Purpose

Evaluate feature quality over time before any ML model training. Understand importance, stability, drift, correlation, and redundancy of every feature in versioned datasets.

## Architecture

```
scanner/feature_intelligence/
├── feature_importance.py          # Correlation, statistical importance
├── feature_stability.py           # Monthly, rolling, market, TF stability
├── feature_drift.py               # Distribution, range, missing, category drift
├── feature_correlation.py         # Feature vs feature, outcome, strategy
├── redundancy.py                  # Highly correlated feature groups
├── ranking.py                     # Composite deterministic ranking
├── feature_report.py              # Structured reports
├── feature_intelligence_engine.py # Orchestrator + history store
├── interfaces.py                  # Protocols
├── services.py                    # FeatureIntelligenceService
└── README.md
```

## Feature Lifecycle

```
ML Dataset (from AI-05)
    → FeatureIntelligenceService.analyze()
    → Importance + Stability + Drift + Correlation
    → Redundancy detection
    → Deterministic ranking
    → Structured reports
    → History persisted at data/feature_intelligence/history.jsonl
```

## Public API

```python
from scanner.feature_intelligence import FeatureIntelligenceService

svc = FeatureIntelligenceService()

# Full analysis
result = svc.analyze(dataset_rows)

# Rank features
ranking = svc.rank(dataset_rows)

# Drift only
drift = svc.drift(dataset_rows)

# Retrieve report
report = svc.report(result.analysis_id)

# History
history = svc.history(limit=20)

# Exposed ranking weights
weights = svc.ranking_weights()
```

## Importance Metrics

| Metric | Type | Description |
|--------|------|-------------|
| Correlation with Win Rate | Deterministic | Pearson with binary win label |
| Correlation with R Multiple | Deterministic | Pearson with regression target |
| Mean Diff Winners/Losers | Deterministic | Average feature value difference |
| Statistical Importance | Composite | Mean of available signal magnitudes |
| Mutual Information | Placeholder | Deferred to ML training sprint |
| Information Gain | Placeholder | Deferred to ML training sprint |

## Stability Dimensions

| Dimension | Method |
|-----------|--------|
| Monthly | Coefficient of variation across monthly means |
| Rolling | CV across rolling window means |
| Market | CV across market group means |
| Timeframe | CV across timeframe group means |
| Version | CV across feature version groups |

Higher stability score = lower variation (score in [0, 1]).

## Drift Detection

Compares baseline (first half) vs current (second half) of dataset:

| Signal | Evidence |
|--------|----------|
| Distribution shift | Normalized mean difference |
| Range shift | Min/max range change |
| Missing rate increase | Baseline vs current missing % |
| Category changes | New categorical values in current period |

Every drift warning includes explicit evidence strings.

## Ranking Algorithm

Composite score with **exposed weights** (no hidden calculations):

| Component | Weight |
|-----------|--------|
| Importance | 0.30 |
| Stability | 0.25 |
| Coverage | 0.15 |
| Drift (inverted) | 0.15 |
| Data Quality | 0.10 |
| Research Confidence | 0.05 |

## Redundancy Detection

- Identifies feature pairs with |correlation| ≥ 0.85
- Groups correlated features into redundancy clusters
- Generates warnings with evidence

## Reports

Each feature report contains:
- History metadata
- Importance metrics
- Stability scores
- Outcome correlation
- Drift analysis
- Ranking position
- Warnings (deterministic)
- Recommendations (rule-based, not AI)

## Future LightGBM Integration

Sprint AI-06 can use feature intelligence to:
- **Feature selection** — use ranking to choose top-N features for `lgb.Dataset`
- **Drift monitoring** — retrain triggers when drift score exceeds threshold
- **Redundancy pruning** — remove correlated features before training
- **Importance validation** — compare LightGBM feature importance against statistical importance

## Rules

- Do NOT modify ML Foundation, Research Engine, Pipeline, or Knowledge layers
- Every score must be explainable
- Every ranking must be reproducible
- Every drift warning must expose evidence
- No hidden weights
