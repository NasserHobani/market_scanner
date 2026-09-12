# AI Advisor Framework (Sprint AIA-01)

## Mission

Integrate Large Language Models into CS Edge as an **AI Advisor** in **Shadow Mode**.

- The LLM **reviews**. The platform **decides**.
- The LLM never receives raw market data.
- The LLM never changes BUY, SELL, STOP, TARGET, or any calculation.

## Architecture

```
Layer outputs (deterministic)
        │
        ▼
DecisionPackageBuilder ──► DecisionPackage (strongly typed, no OHLC)
        │
        ▼
PromptBuilder (versioned templates: v1, v2, v3)
        │
        ▼
ProviderRegistry ──► LLMProvider.analyze()
        │
        ▼
ResponseParser ──► ResponseValidator (grounding check)
        │
        ▼
ReviewEngine ──► AdvisorReview
        │
        ├──► AdvisorMemory (persistent JSONL)
        ├──► AdvisorHistory (query)
        └──► AdvisorScore (quality metrics)
```

## Shadow Mode

First implementation is Shadow Mode only:

| Allowed | Forbidden |
|---------|-----------|
| Read Decision Package | Change BUY/SELL |
| Review and comment | Change STOP/TARGET |
| Agree or disagree | Override calculations |
| Suggest experiments | Execute trades |
| Flag risks | Modify platform state |

## Decision Package

The only input an LLM may receive. Contains:

- Trade, Market Context, Knowledge Summary
- Research Summary, Similarity Summary, Prediction Summary
- Feature Intelligence, Optimization Summary
- Statistics, Risk, Confidence, Decision
- Execution Metadata, Evidence Index

No OHLC. No candles. No DataFrames. No CSV. No raw indicators.

## Provider Layer

Runtime-registered providers via `ProviderRegistry`:

- Claude, OpenAI, Gemini, DeepSeek, OpenRouter, Open Source
- All are stub implementations (no API keys, no network)
- Real API integration deferred to Sprint AIA-02

## Multi-Model Ready

`AIAdvisorService.review_multi()` sends one Decision Package to
multiple providers simultaneously. Voting/consensus is NOT implemented
yet — only the dispatch architecture.

## Usage

```python
from scanner.ai_advisor import AIAdvisorService

svc = AIAdvisorService()

package = svc.build_package(
    "evt_001",
    knowledge_context={...},
    reasoning_review={...},
    similarity_context={...},
    prediction={...},
)

review = svc.review(package, provider_id="mock")
print(review.agreement, review.confidence)
print(review.to_ui_model())
```

## Tests

```bash
python tests_ai_advisor.py
```

## Rules

1. Do NOT modify Knowledge, Research, Prediction, Optimization, Decision AI, Trading Engine, or Risk Engine.
2. Only integrate via read-only layer outputs.
3. Never trust LLM output — always validate and ground.
4. Every claim must reference an evidence_id from the Decision Package.
