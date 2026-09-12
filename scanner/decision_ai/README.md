# AI Decision Support Engine

Structured AI reasoning for the CS Edge AI Platform. **No LLM calls. No chat. No buy/sell. The AI is a reviewer, never the trading engine.**

## Purpose

Integrate all platform layers (Knowledge, Reasoning, Similarity, Research, Feature Intelligence, Prediction) into one immutable AI context for structured decision support.

## Architecture

```
scanner/decision_ai/
├── context_builder.py      # Immutable AI context from all layers
├── evidence_builder.py     # Unified evidence model
├── prompt_builder.py       # Template-based prompts (5 types)
├── decision_summary.py     # JSON-only structured summaries
├── confidence_fusion.py    # Multi-source confidence fusion
├── guardrails.py           # Uncertainty validation rules
├── ai_review.py            # Structured AI review output
├── interfaces.py           # Protocols
├── services.py             # DecisionAIService
└── README.md
```

## Context Lifecycle

```
Layer outputs (Knowledge, Reasoning, Similarity, Research, FI, Prediction)
    → ContextBuilder.build() → DecisionAIContext (immutable)
    → EvidenceBuilder.build() → UnifiedEvidenceBundle
    → ConfidenceFusion.fuse() → FusedConfidence
    → Guardrails.validate() → GuardrailReport
    → DecisionSummaryBuilder.build() → DecisionSummary (JSON)
    → PromptBuilder.build() → StructuredPrompt (template only)
    → AIReviewEngine.review() → AIReview
```

## Evidence Model

Every `UnifiedEvidenceItem` includes:

| Field | Description |
|-------|-------------|
| `evidence_id` | Unique identifier |
| `source` | reasoning, similarity, prediction, research, feature_intelligence |
| `label` | Human-readable description |
| `category` | Evidence category |
| `direction` | supports, contradicts, neutral, missing |
| `confidence` | 0.0–1.0 |
| `timestamp` | ISO UTC |
| `version` | Source layer version |
| `facts` | Key=value evidence strings |
| `trace` | Dot-path provenance |

## Prompt Templates

| Type | Purpose |
|------|---------|
| `market_review` | Market context analysis |
| `trade_review` | Trade setup review |
| `risk_review` | Risk factor assessment |
| `research_review` | Research support evaluation |
| `prediction_review` | Model prediction assessment |

Templates only — `llm_ready: false`. Future sprint adds provider integration.

## Confidence Fusion

| Component | Weight |
|-----------|--------|
| Reasoning | 0.30 |
| Similarity | 0.20 |
| Prediction | 0.20 |
| Research | 0.15 |
| Feature Intelligence | 0.15 |

Weights exposed via `svc.fusion_weights()`. Re-normalized over available sources only.

## Guardrails

| Rule | Trigger |
|------|---------|
| `missing_evidence_source` | Expected evidence layer not present |
| `prediction_confidence_low` | Prediction confidence < 0.55 |
| `research_sample_small` | Research sample < 20 |
| `similarity_insufficient` | Match count < 3 |
| `feature_drift_high` | Feature drift score > 0.5 |

Guardrails report uncertainty — never hide missing evidence.

## Public API

```python
from scanner.decision_ai import DecisionAIService

svc = DecisionAIService()

# Build context from all layers
ctx = svc.build_context(
    event_id="evt_001",
    knowledge_context=knowledge_dict,
    reasoning_review=reasoning_dict,
    similarity_context=similarity_dict,
    prediction=prediction_dict,
    research_report=research_dict,
    feature_analysis=fi_dict,
)

# Generate decision summary (JSON only)
summary = svc.decision_summary(ctx)

# Build prompt template
prompt = svc.build_prompt("trade_review", ctx)

# Full trade review
review = svc.review_trade(
    event_id="evt_001",
    knowledge_context=knowledge_dict,
    reasoning_review=reasoning_dict,
    similarity_context=similarity_dict,
    prediction=prediction_dict,
)

# Market review
market_review = svc.review_market(event_id="evt_001", knowledge_context=knowledge_dict)
```

## Future LLM Integration

Sprint AI-08 can add:
- `LLMProvider` protocol with `complete(prompt) -> structured_response`
- Provider plugins: OpenAI, Claude, Gemini
- `AIReviewEngine` invokes LLM with built prompt
- Response parsed into existing `DecisionSummary` structure
- Guardrails run before and after LLM call

Current sprint prepares all inputs — no provider integration.

## Rules

- Do NOT call OpenAI, Claude, or Gemini
- Do NOT implement chat
- Do NOT execute trades or generate buy/sell
- Do NOT modify Predictive, Research, Reasoning, Similarity, or Knowledge layers
- Every AI input must be traceable
- Every confidence value must expose its source
- Every missing fact must be reported
