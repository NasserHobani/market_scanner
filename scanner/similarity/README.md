# Knowledge Similarity Engine

Deterministic retrieval of historical market situations from the Knowledge Base.
No ML, no embeddings, no vector database.

## Position in Stack

```
Knowledge Base (facts)
  ↓
Similarity Engine (retrieval)  ← this module
  ↓
Reasoning / Intelligence / Future AI Assistant
```

Reads from `KnowledgeRepository` only. Does not modify Knowledge, Pipeline,
Reasoning, or Intelligence layers.

## Quick Start

```python
from scanner.similarity import SimilarityService, RetrievalFilters
from scanner.knowledge import KnowledgeService

# Populate knowledge first
ks = KnowledgeService()
ks.capture_scan(scan_source)

# Find similar historical situations
svc = SimilarityService(knowledge_service=ks)
result = svc.find_similar(scan_source, top_n=10)

for match in result["matches"]:
    print(match["event_id"], match["similarity_score"]["overall"])
```

## Similarity Pipeline

```
Query (scan source or feature payload)
  ↓
build_fingerprint()        → explainable situational fingerprint
  ↓
_load_candidates()         → FEATURE snapshots from KnowledgeRepository
  ↓
apply_filters()            → market, timeframe, outcome, date range
  ↓
SimilarityScorer.score()   → 0–100 with component breakdown
  ↓
RankingEngine.rank()       → similarity + quality + confidence + recency
  ↓
SimilarityResult           → top N matches with outcomes
```

## Distance Calculation

`FeatureDistanceCalculator` supports:

| Type | Method | Distance |
|------|--------|----------|
| Numerical | `abs(a-b) / max_delta` | 0–1, clamped |
| Boolean | equal/not equal | 0 or 1 |
| Categorical | string equality | 0 or 1 |
| Missing | configurable penalty | default 0.5 |

All weights exposed in `DistanceConfig`.

## Similarity Score Components

| Component | Weight (default) | Source |
|-----------|-----------------|--------|
| Trend | 0.20 | htf_bias, trend components |
| Liquidity | 0.15 | liquidity class, sweeps |
| Structure | 0.15 | BOS, CHOCH, fib |
| Volume | 0.15 | rvol, vwap, spike signals |
| Pattern | 0.15 | pattern/candle counts |
| Environment | 0.20 | regime, atr, volatility |

Overall = weighted mean × 100. Every score includes `explanation[]`.

## Ranking Strategy

```
rank_score = similarity × 0.50
           + data_quality × 0.20
           + knowledge_confidence × 0.15
           + recency × 0.15
```

Weights configurable via `RankingWeights`. No random ordering.

## Retrieval Filters

| Filter | Description |
|--------|-------------|
| `market` | Market type (crypto, forex, etc.) |
| `timeframe` | Chart timeframe |
| `symbol` | Specific symbol |
| `outcome` | winner, loser, won, lost |
| `date_from` / `date_to` | Date range |
| `min_quality` | Minimum completeness score |
| `require_outcome` | Only events with OUTCOME snapshot |
| `exclude_event_ids` | Skip specific events |

## Similarity Result

Each `SimilarityMatch` includes:

- `similarity_score` — 0–100 with component breakdown
- `matched_features` / `different_features`
- `historical_outcome`, `r_multiple`, `expected_r`
- `supporting_evidence[]`
- `rank_score`, `data_quality`, `recency_score`

## Public API

```python
svc = SimilarityService()

svc.find_similar(query, top_n=10, filters=RetrievalFilters(market="crypto"))
svc.find_best_matches(query, top_n=5)
svc.compare(query, candidate)
svc.compare_events(event_id_a, event_id_b)
svc.fingerprint(source)
svc.statistics(query, top_n=25)
```

## Future AI Integration

- Reasoning `historical_similarity` stage can consume `SimilarityMatch` evidence
- Intelligence insights can reference fingerprint matches
- AI Assistant can explain matches using `explanation[]` and `supporting_evidence[]`

## Future Machine Learning Integration

- `FeatureDistanceCalculator` output provides labeled feature deltas
- `SimilarityScore` components serve as ML feature priors
- Fingerprint components enable regime-stratified training partitions
- No ML implemented in this sprint

## Module Structure

```
scanner/similarity/
├── fingerprint.py         Situational fingerprints
├── feature_distance.py    Deterministic distance
├── similarity_score.py    0–100 scoring
├── filters.py             Retrieval filters
├── retrieval.py           Candidate loading + scoring
├── ranking.py             Composite ranking
├── result.py              SimilarityMatch, SimilarityResult
├── similarity_engine.py   Orchestrator
├── interfaces.py          Provider protocols
├── services.py            SimilarityService
└── README.md
```

## Tests

```bash
python tests_similarity.py
```

## Rules

- No LLM, ML, embeddings, FAISS, Pinecone
- No modification of Knowledge, Pipeline, Reasoning, Intelligence
- Every result explainable, every distance reproducible, every rank deterministic
