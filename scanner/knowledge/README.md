# Trading Knowledge Base (`scanner/knowledge`)

Foundation layer for AI, machine learning, and quantitative research on the CS Edge platform.

**Schema version:** `1.1` (Sprint AI-01.5)

This module **does not** execute trades, generate recommendations, or run backtests.

---

## Architecture (v1.1)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Platform (unchanged)                             │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SnapshotBuilder                                                         │
│  ├─ MarketEnvironment   (macro context)                                  │
│  ├─ MarketSnapshot      (+ fingerprint)                                  │
│  ├─ FeatureSnapshot     (+ FeatureRegistry metadata, to_vector)          │
│  ├─ RecommendationSnapshot                                               │
│  ├─ TradeSnapshot                                                        │
│  └─ OutcomeSnapshot                                                      │
│       each carries: SchemaMetadata + AuditTrail + DataQualityReport      │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  KnowledgeRepository (JSONL)                                             │
│  + KnowledgeRelationship records (explicit graph edges)                    │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
     KnowledgeGraph      ContextBuilder    KnowledgeMemory
     (traversal)         (AI context)      (AI summary slots)
```

### Knowledge Graph (lifecycle chain)

```
MarketEnvironment
        ↓ derived_from
MarketSnapshot ──fingerprint──► (future Similarity Engine)
        ↓ produces
FeatureSnapshot ──to_vector()──► (future LightGBM)
        ↓ informs
RecommendationSnapshot
        ↓ triggers
TradeSnapshot
        ↓ closes_as
OutcomeSnapshot
        ↓ evaluated_by
Experiment (placeholder)
        ↓ trained_by
Model (placeholder)
```

---

## Snapshot Versioning

Every snapshot includes `schema`:

| Field | Purpose |
|-------|---------|
| `schema_version` | Loader compatibility (`1.1`) |
| `created_at` | UTC capture time |
| `created_by` | Pipeline actor |
| `generator_version` | Knowledge module version |
| `platform_version` | `scanner.__version__` |

Legacy v1.0 records upgrade in-memory via `upgrade_snapshot()`.

---

## Feature Metadata

Features are stored as `FeatureValue` objects:

```python
FeatureValue(
    name="rsi",
    value=58.2,
    source="score_context",
    calculation_module="scanner.indicators.pine",
    calculation_version="1.0",
    notes="",
)
```

`FeatureSnapshot` exposes:

- `to_dict()` — full export
- `to_vector()` — numeric list (no ML deps)
- `to_dataframe()` — `{columns, rows}` tabular export (no pandas)

Legacy `groups` dict is retained for backward compatibility.

---

## Market Environment

`MarketEnvironment` is **not** a feature snapshot. It captures macro conditions:

- Market regime, trend state (trending/range/expansion/compression)
- Volatility class, liquidity class, trading session
- Market breadth, dominance, fear & greed (when provided)
- Sector strength, correlation summary (extension slots)

---

## Audit Layer

Every snapshot includes `audit`:

- `creator`, `source`, `pipeline_stage`
- `verification_status` (unverified / verified / rejected / partial)
- `version`, `created_at`

---

## Data Quality

Every snapshot includes `quality`:

- `completeness_score` (0–1)
- `missing_features`, `warnings`, `validation_errors`, `unknown_values`
- `is_valid` — false when validation errors exist

Use `assert_valid(report, strict=True)` to reject bad payloads.

---

## Knowledge Memory (foundation)

`KnowledgeMemory` holds empty slots for future AI-generated summaries:

- `KnowledgeSummary`, `MarketSummary`, `StrategySummary`, `PerformanceSummary`

`empty_slots()` reports which summaries still need AI population.

---

## Future Integrations

| Capability | v1.1 Preparation |
|------------|------------------|
| **Similarity Engine** | `market_fingerprint()` on `MarketSnapshot` |
| **AI Assistant** | `ContextBuilder` + `KnowledgeMemory` slots |
| **LightGBM** | `FeatureSnapshot.to_vector()` / `to_dataframe()` |
| **Feature Store** | `FeatureRegistry` with provenance metadata |
| **Knowledge Graph** | `KnowledgeGraph.walk_chain()`, explicit edges |

---

## Testing

```bash
python tests_knowledge.py
```

---

## Rules

- Architecture only — no trading/recommendation/backtest changes
- Django-free
- Backward compatible with Sprint AI-01 payloads
