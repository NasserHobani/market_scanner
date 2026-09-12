# Intelligence Layer

Statistical discovery from historical completed trades. This layer learns from
data — it does **not** predict, call LLMs, or run machine learning models.

## Position in the Stack

```
Trading Platform  →  Knowledge (facts)  →  Reasoning (evidence)  →  Intelligence (discovery)  →  Future AI
```

Intelligence reads trade history only. It does not modify Knowledge, Reasoning,
or the Recommendation Engine.

## Modules

| Module | Purpose |
|--------|---------|
| `pattern_engine.py` | Discover recurring factor combinations with measured outcomes |
| `edge_monitor.py` | Rolling expectancy, profit factor, win rate, drawdown; edge decay alerts |
| `trend_monitor.py` | Sequential bucket performance trends |
| `market_memory.py` | Long-term regime buckets (trending, range, volatility) |
| `strategy_health.py` | Composite health scores with exposed components |
| `historical_statistics.py` | Rankings: best/worst patterns, timeframes, markets, regimes |
| `knowledge_summary.py` | Structured factor importance over last N trades |
| `insight.py` | `Insight` objects and `InsightEngine` |
| `intelligence_engine.py` | Full pipeline orchestrator |
| `services.py` | `IntelligenceService` public API |
| `interfaces.py` | Provider protocols for dependency injection |

## Quick Start

```python
from scanner.intelligence import IntelligenceService

rows = [...]  # completed trade dicts from scanner.tracking
report = IntelligenceService().analyze(rows, strategy_id="momentum_v1")

patterns = report["patterns"]
edge = report["edge"]
health = report["strategy_health"]
insights = report["insights"]
```

## Trade Row Format

```python
{
    "status": "won" | "lost",
    "r_multiple": 1.5,
    "factors": ["htf", "confluence", "price_action"],
    "market": "crypto",
    "timeframe": "4h",
    "grade": "A",
    "closed_at": datetime(...),
    "atr_pct": 2.1,
}
```

## Pattern Discovery

`PatternEngine` enumerates factor combinations (size 1–3) across closed trades.
Each combination with ≥ `min_trades` (default 3) becomes a `PatternInsight`:

- `success_rate` / `win_rate`
- `expectancy`, `profit_factor`, `avg_r`, `total_r`
- Human-readable `label` (e.g. `Trend + Liquidity + OrderBlock`)

No prediction — pure counting and `scanner.tracking.summarize()`.

## Edge Monitoring

`EdgeMonitor` computes rolling snapshots for windows `[10, 20, 30, 50]`:

| Metric | Description |
|--------|-------------|
| Rolling Expectancy | Mean R per trade in window |
| Rolling Profit Factor | Gross wins / gross losses |
| Rolling Win Rate | % won |
| Rolling Drawdown | Max drawdown in R |
| Edge Stability | Fraction of windows with positive expectancy |
| Edge Decay | `(recent_exp − baseline_exp) / |baseline_exp|` |

Generates structured `EdgeAlert` objects when thresholds are breached.

## Strategy Health

`StrategyHealthEngine` produces transparent composite scores (0–100):

| Score | Formula basis |
|-------|-----------------|
| Overall Health | Mean of 7 exposed components |
| Stability | Edge stability ± decay penalty |
| Consistency | Tracking consistency score |
| Confidence | Sample quality + expectancy + stability |
| Sample Quality | `closed_count / min_reliable × 100` |
| Data Quality | % rows with `r_multiple` + `factors` |
| Research Coverage | Patterns + memory buckets discovered |

Every score exposes its `components` dict — no hidden calculations.

## Knowledge Summary

`KnowledgeSummaryEngine` analyzes the last 500 trades (configurable):

- Per-factor marginal expectancy delta (with vs without)
- Importance scores: `|delta| × (factor_count / total)`
- Named buckets: `trend_importance`, `liquidity_importance`, etc.

Output is structured objects only — no natural language generation.

## Insights

`InsightEngine` converts analytics into `Insight` objects:

- `title`, `description`, `importance`, `confidence`
- `evidence[]`, `supporting_statistics`, `trace`
- `affected_strategy`

These become inputs for future AI Assistant and Similarity Engine.

## Interfaces

```python
from scanner.intelligence import (
    IntelligenceProvider,
    PatternProvider,
    InsightProvider,
    HealthProvider,
)
```

Runtime-checkable `Protocol` classes for DI and testing.

## Future AI Integration

| Future Component | Intelligence Feed |
|------------------|-------------------|
| Similarity Engine | Pattern insights + market memory records |
| AI Assistant | Insight objects with evidence chains |
| Machine Learning | Feature importance from knowledge summaries |
| Continuous Learning | Edge decay alerts + health degradation signals |

## Tests

```bash
python tests_intelligence.py
```

## Rules

- No LLM, ML, or prediction models
- No modification of Knowledge or Reasoning layers
- No new indicators — uses existing `factors` and `scanner.tracking`
- Every insight must be explainable and reproducible
