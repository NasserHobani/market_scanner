# AIA-08 Model Comparison

## Existing model
- Model ID: `mdl_2097ebe89fb14b7b`
- OOS accuracy: 0.4516
- Baseline (majority): 0.5161
- Gap: -0.0645

## Baselines
- **naive_majority**: accuracy=0.5161
- **historical_winrate**: accuracy=0.5161
- **rule_score_60**: accuracy=0.4194
- **rule_score_70**: accuracy=0.4194

## Root cause
Primary: **oos_underperformance**

[
  {
    "factor": "oos_underperformance",
    "evidence": "model 45.2% < baseline 51.6%",
    "severity": "high"
  },
  {
    "factor": "weak_features",
    "evidence": "constant/zero-variance: market_enc, side_buy",
    "severity": "medium"
  },
  {
    "factor": "insufficient_signal",
    "evidence": "snapshot coverage 1.5%",
    "severity": "high"
  },
  {
    "factor": "strong_naive_baseline",
    "evidence": "near-balanced classes (47.8% positive)",
    "severity": "medium"
  }
]
