# AIA-09 Engineering Report — Predictive + LLM Decision Fusion

## Architecture

```
Platform Decision
       +
ACTIVE LightGBM (PredictionAdapter)
       +
Evidence Layers → UnifiedDecisionPackage
       ↓
Qwen / Claude (evaluates prediction, does not invent probability)
       ↓
FusionEngine → AgreementAnalyzer → FusionPolicy
       ↓
FusionHistory (append-only)
       ↓
Trade Close → OutcomeEvaluator → Learning / Research
```

## Safety

| Rule | Status |
|------|--------|
| No inactive model fallback | ✅ PredictionAdapter |
| NOT_PROMOTED blocked | ✅ |
| LLM cannot promote models | ✅ |
| Trading unchanged | ✅ shadow_mode |
| Three confidence types separated | ✅ confidence_policy |

## Current State

With NOT_PROMOTED models only:

- Prediction: **UNAVAILABLE**
- Fusion state: **PREDICTION_UNAVAILABLE**
- LLM reviews: **still work**

## Integration Points

- `layer_collectors._collect_prediction` → `PredictionAdapter`
- `prompt_builder` → prediction fusion instructions
- `ai_local.routing` → fusion history after review
- `production_hooks` → fusion outcome on trade close
- UI: Prediction tab, Fusion tab (`دمج القرار`), review drawer section
