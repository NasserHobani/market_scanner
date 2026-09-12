# Market Analysis Orchestrator

Production orchestration layer for the CS Edge AI Platform. Coordinates all platform components into one deterministic market analysis workflow.

**No UI. No REST API. No LLM. Orchestration only.**

## Purpose

Transform independent engines into a complete market analysis workflow with execution order, retries, timeouts, partial failure handling, caching, and final aggregation.

## Architecture

```
scanner/orchestration/
├── analysis_orchestrator.py   # Main orchestrator
├── workflow.py                # Deterministic stage order
├── execution_context.py       # Immutable shared context
├── stage.py                   # Stage engine (prepare/execute/validate/cleanup)
├── stage_handlers.py          # Adapters to platform services
├── retry.py                   # Retry failed stages
├── timeout.py                 # Per-stage and workflow timeouts
├── cache.py                   # Deterministic stage caching
├── aggregator.py              # MarketAnalysis assembly
├── scheduler.py               # Job queue
├── result.py                  # MarketAnalysis, StageExecutionResult
├── interfaces.py              # Protocols
├── services.py                # AnalysisService public API
└── README.md
```

## Workflow

```
Load Market
    ↓
Knowledge
    ↓
Reasoning
    ↓
Similarity
    ↓
Research
    ↓
Prediction
    ↓
Decision AI
    ↓
Aggregation
```

Every stage is isolated. Optional stages (similarity, research, prediction, decision_ai) can fail without aborting the workflow.

## Public API

```python
from scanner.orchestration import AnalysisService

svc = AnalysisService(
    knowledge_service=KnowledgeService(),
    reasoning_service=ReasoningService(),
    similarity_service=SimilarityService(),
    research_service=ResearchService(),
    predictive_service=PredictiveService(),
    decision_service=DecisionAIService(),
    model_id="mdl_abc",
)

# Full market analysis
analysis = svc.analyze_market(
    symbol="BTCUSDT",
    market="crypto",
    timeframe="4h",
    scan_source=scan_dict,
    trade_rows=trade_rows,
)

# By symbol
analysis = svc.analyze_symbol("BTCUSDT", market="crypto", timeframe="4h")

# With strategy context
analysis = svc.analyze_strategy("default", symbol="BTCUSDT", trade_rows=rows)

# Status
status = svc.status(analysis.analysis_id)

# Job queue
job = svc.enqueue("ETHUSDT", market="crypto")
result = svc.run_queued()
```

## Execution Context

Immutable `ExecutionContext` shared across all stages:

| Field | Description |
|-------|-------------|
| `analysis_id` | Unique analysis identifier |
| `symbol`, `market`, `timeframe` | Market identity |
| `scan_source` | Raw scan input |
| `knowledge` | Knowledge layer output |
| `reasoning` | Reasoning review |
| `similarity` | Similarity context |
| `research` | Research statistics |
| `prediction` | Model prediction |
| `decision_review` | Decision AI review |
| `stage_outputs` | Per-stage raw outputs |

## Retry Strategy

- Retry failed stages only — never retry successful stages
- Default: 2 retries with exponential backoff (100ms base)
- Configurable via `RetryPolicy(max_retries, backoff_ms, backoff_multiplier)`

## Timeout Policy

- Per-stage timeout: 30 seconds (default)
- Workflow timeout: 120 seconds (default)
- Graceful cancellation via thread join

## Caching

| Stage | Cacheable | Key |
|-------|-----------|-----|
| Knowledge | Yes | symbol + market + timeframe |
| Similarity | Yes | symbol + market + timeframe |
| Research | Yes | symbol + market + timeframe |
| Prediction | Conditional | Only when model_version matches |

Default TTL: 3600 seconds.

## MarketAnalysis Output

```json
{
  "analysis_id": "ana_...",
  "symbol": "BTCUSDT",
  "status": "completed|partial|failed",
  "knowledge": {},
  "reasoning": {},
  "similarity": {},
  "research": {},
  "prediction": {},
  "decision_review": {},
  "execution_trace": []
}
```

## Rules

- Do NOT modify previous platform layers
- Orchestration calls existing services via adapters
- Partial failures produce `partial` status, not hard failure
- Required stages: load_market, knowledge, reasoning, aggregation
- Optional stages: similarity, research, prediction, decision_ai
