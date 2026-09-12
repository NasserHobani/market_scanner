# AIA-08 Runtime Verification

**Overall: WARNING**

| Stage | Status | Detail |
|---|---|---|
| load_trades | PASS | 203 closed |
| dataset_generation | PASS | eligible=203 rejected=0 |
| feature_audit | PASS | 20 active, 2 constant |
| leakage_test | PASS | injection rejected |
| dataset_quality | PASS | diversity ok |
| label_analysis | PASS | positive_rate=0.4778 |
| chronological_split | PASS | train=142 val=30 test=31 |
| baselines | PASS | majority=0.5161 |
| existing_model | PASS | model=mdl_2097ebe89fb14b7b oos=0.4516 |
| walk_forward | PASS | folds=24 mean=0.575 |
| calibration | PASS | INSUFFICIENT_SAMPLE |
| quality_gates | WARNING | accuracy improvement -0.065 < 0.02 |
| model_registry | PASS | 2 models |
| inference | PASS | no active model |
| orchestrator_status | PASS | status=UNAVAILABLE active=None |

## Summary numbers
```json
{
  "total_trades": 203,
  "eligible_trades": 203,
  "rejected_trades": 0,
  "dataset_id": "ds_d02224f6fdb54e82",
  "feature_version": "2.0.0",
  "feature_count": 22,
  "useless_features": [
    "market_enc",
    "side_buy"
  ],
  "class_distribution": {
    "positive": 97,
    "negative": 106,
    "positive_rate": 0.4778,
    "imbalance_ratio": 1.09
  },
  "snapshot_coverage": {
    "with_snapshot": 3,
    "without_snapshot": 200,
    "coverage_rate": 0.0148
  },
  "label_noise": 0.0,
  "baseline_accuracy": 0.5161,
  "model_count": 2,
  "model_oos_accuracy": 0.4516,
  "promotion_status": "NOT_PROMOTED",
  "prediction_status": "UNAVAILABLE",
  "active_model": null,
  "root_cause": "oos_underperformance",
  "next_training_trigger": 20
}
```

## Label audit
{
  "primary_label": "label_binary_win",
  "definition": "1 if r_multiple > 0 OR status=WON, else 0",
  "positive_class": "WIN (label_binary_win=1)",
  "negative_class": "LOSS (label_binary_win=0)",
  "neutral_handling": "r_multiple==0 counted as loss unless status=WON",
  "r_threshold": "> 0 for positive R label",
  "sample_size": 203,
  "win_loss_positive_rate": 0.4778,
  "positive_r_rate": 0.4778,
  "status_vs_r_disagreements": 0,
  "neutral_r_count": 0,
  "label_noise_estimate": 0.0,
  "comparison": {
    "model_a": "WIN/LOSS (status-based with r fallback)",
    "model_b": "positive R / negative R (r_multiple > 0)",
    "agreement_rate": 1.0,
    "recommendation": "Labels are equivalent"
  }
}

## Prediction status
- Status: **UNAVAILABLE**
- Active model: `None`
- Models trained: 2
