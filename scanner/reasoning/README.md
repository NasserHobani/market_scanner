# AI Reasoning Framework (`scanner/reasoning`)

Explainable, evidence-based review of existing recommendations.

**No LLM. No ML. No new indicators. No trading logic changes.**

Sits between `scanner/knowledge/` and the future AI Assistant.

---

## Reasoning Pipeline

```
Knowledge Context (dict)
        │
        ▼
┌───────────────────┐
│  EvidenceEngine   │  Facts → Evidence (weight, strength, source, trace)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ ContradictionEngine│  Opposing evidence pairs (traceable)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ ConfidenceEngine  │  Weighted category breakdown (reproducible)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│   DecisionTree    │  Configurable stage flow
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ExplainabilityEngine│ Structured strengths / weaknesses / risks
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│RecommendationReviewer│ Agreement score + verdict (reviews, not generates)
└───────────────────┘
```

---

## Decision Tree (default stages)

1. Trend → 2. Market Regime → 3. Liquidity → 4. Structure → 5. Momentum
6. Volume → 7. Risk → 8. Historical Similarity → 9. Recommendation Review

Configurable via `DecisionTree(stages=[...])`.

---

## Evidence System

Raw indicators are **never** exposed to future AI directly.

| Instead of | Reasoning receives |
|------------|-------------------|
| `EMA20 > EMA50` | `Bullish Trend Evidence` |
| `rvol=1.4` | `Volume Participation Evidence` |
| `bos_count=1` | `Market Structure Evidence` |

Each `Evidence` includes: `label`, `category`, `direction`, `weight`, `strength`, `confidence`, `source`, `facts`, `trace`.

---

## Confidence Calculation

Default category weights:

| Category | Weight |
|----------|--------|
| Trend | 30% |
| Liquidity | 20% |
| Volume | 15% |
| Structure | 20% |
| History | 15% |

Auxiliary: Regime, Momentum, Confluence, Risk (10% each in breakdown).

Formula: weighted average of per-category scores minus contradiction penalty.

---

## Usage

```python
from scanner.knowledge import KnowledgeService
from scanner.reasoning import ReasoningService

ks = KnowledgeService()
rs = ReasoningService()

ids = ks.capture_scan(scan_source)
kctx = ks.get_context(ids["event_id"])
review = rs.review_from_knowledge(kctx)

print(review.verdict)           # aligned | caution | misaligned
print(review.agreement_score)   # 0–1
print(review.explanation)       # structured dict
```

---

## Future AI Integration

| System | How reasoning helps |
|--------|---------------------|
| **AI Assistant** | LLM receives `RecommendationReview` + `StructuredExplanation` — not raw OHLCV |
| **Similarity Engine** | Historical evidence category links to fingerprint matches |
| **LightGBM** | Feature importance cross-check via `important_features` |
| **Continuous Learning** | Store review verdict + outcome for calibration |

---

## Rules

- Reviews existing recommendations only
- Every score is reproducible from evidence + weights
- Every contradiction has `supporting_id` + `contradicting_id`
- No modification to `scanner/knowledge/`

---

## Testing

```bash
python tests_reasoning.py
```
