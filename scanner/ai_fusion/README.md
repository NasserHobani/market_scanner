# AI Fusion (AIA-09)

Multi-layer decision fusion: Platform + ACTIVE LightGBM + LLM evidence review.

## Principles

- LightGBM never influences trading unless **ACTIVE** (explicit promotion).
- LLM never invents statistical probabilities.
- Three separate confidence values: platform, prediction probability, LLM review.
- Shadow mode only — fusion is advisory.

## Package

`scanner/ai_fusion/`

| Module | Role |
|--------|------|
| `prediction_adapter.py` | ACTIVE-only inference |
| `fusion_engine.py` | Orchestrates fusion |
| `agreement_analyzer.py` | Platform vs prediction vs LLM |
| `fusion_history.py` | Append-only `data/ai_fusion_history.jsonl` |
| `outcome_evaluator.py` | Trade-close fusion evaluation |
| `fusion_metrics.py` | Accuracy, calibration, cost metrics |

## Verification

```bash
python tests_ai_fusion.py
python scripts/verify_ai_fusion.py
```
