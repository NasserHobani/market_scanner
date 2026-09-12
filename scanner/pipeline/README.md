# Production Integration Pipeline

Connects Knowledge, Similarity, Reasoning, and Intelligence into a single
deterministic production flow. No LLM, no ML, no Django — integration only.

## Architecture Position

```
Scanner
  ↓
Knowledge Capture      (KnowledgeService)
  ↓
Similarity Retrieval   (SimilarityService)  ← optional, never fails pipeline
  ↓
Reasoning Review       (ReasoningService)   ← consumes similarity as evidence
  ↓
Intelligence Analysis  (IntelligenceService) ← consumes similarity statistics
  ↓
Persistence            (PipelineStore)
  ↓
Events                 (EventBus)
```

## Quick Start

```python
from scanner.pipeline import PipelineService

svc = PipelineService()

# After scan completes — similarity runs automatically
result = svc.run_scan_pipeline(scan_source, trade_rows=closed_trades)

# Similarity summary in result
result["similarity_summary"]  # match_count, avg_similarity, top_matches (refs only)

# Standalone similarity
sim = svc.run_similarity(scan_source, event_id=result["event_id"])

# Similarity status
status = svc.similarity_status(execution_id=result["execution_id"])
```

## Pipeline Stages (v2.1.0)

| Order | Stage | Required | On Failure |
|-------|-------|----------|------------|
| 1 | Knowledge | Yes | Pipeline fails |
| 2 | Similarity | No | Continues with "No Historical Evidence" |
| 3 | Reasoning | Yes | Pipeline fails |
| 4 | Intelligence | Conditional | Skipped without trade_rows |

## Similarity Lifecycle

1. After knowledge capture, `SimilarityStage` calls `SimilarityService.find_similar()`
2. Results converted to `SimilarityContext` (immutable downstream contract)
3. `SimilaritySummary` persisted (references only — no full historical records)
4. Reasoning receives `similarity_context` as historical evidence
5. Intelligence report enriched with `similarity_statistics` section

## Failure Isolation

Similarity is **optional**. If similarity fails:
- Pipeline continues
- Reasoning receives `"No Historical Evidence"`
- Intelligence runs without similarity statistics
- Error recorded in `similarity_metrics.error`

## Execution Context Fields

| Field | Consumer | Purpose |
|-------|----------|---------|
| `similarity_result` | Internal | Full similarity output |
| `similarity_context` | Reasoning, Intelligence | Immutable evidence contract |
| `similarity_summary` | Persistence | Reference-only stored summary |
| `match_count` | Reasoning evidence | Historical match count |
| `average_win_rate` | Reasoning evidence | Win rate over matches |
| `average_r` | Reasoning evidence | Average R over matches |
| `historical_evidence` | Reasoning | Evidence strings |
| `historical_warnings` | Reasoning | Warning strings |

## Public API

```python
svc.run_scan_pipeline(scan_source, trade_rows=...)
svc.run_trade_pipeline(scan_source=..., trade_source=..., trade_rows=...)
svc.run_similarity(query, event_id=..., top_n=10)
svc.rebuild_similarity(event_id, scan_source=...)
svc.similarity_status(execution_id=...)  # or event_id=...
svc.rebuild_trade(event_id, trade_rows=...)
svc.status(execution_id)
svc.history(limit=20)
svc.get_metrics()
```

## Observability

Per-execution `metrics.similarity`:
- `candidate_count` — total candidates scanned
- `filtered_candidates` — after filters applied
- `retrieved_matches` — matches returned
- `avg_similarity` — average similarity score

## Persistence

`similarity_summary` stored on `PipelineExecution`:
```python
{
    "match_count": 5,
    "avg_similarity": 72.5,
    "avg_r": 1.2,
    "win_rate": 60.0,
    "query_fingerprint_id": "sf_...",
    "top_matches": [{"event_id": "ke_...", "similarity": 85, "r_multiple": 2.0}],
    "knowledge_event_id": "ke_..."
}
```

## Design Principles

- Similarity provides **evidence**, not decisions
- Reasoning interprets evidence
- Intelligence learns from evidence
- No layer bypasses another
- No circular dependencies
- Deterministic execution

## Tests

```bash
python tests_pipeline.py
python tests_pipeline_integration.py
```
