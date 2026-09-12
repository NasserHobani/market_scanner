# Quant Research Engine

Reproducible research laboratory for the CS Edge AI Platform.

**No ML. No LLM. No predictions. Pure research.**

## Purpose

The research module enables systematic hypothesis testing, metric computation,
group comparison, and structured reporting over historical trade data.

## Architecture

```
scanner/research/
├── experiment.py          # Experiment model + persistence
├── hypothesis.py          # Declarative hypothesis engine
├── experiment_runner.py   # Lifecycle orchestration
├── metrics.py             # Deterministic metrics
├── comparison.py          # Group comparison engine
├── statistics.py          # Statistical difference helpers
├── report.py              # Structured research reports
├── dataset.py             # Dataset builder (no raw storage access)
├── research_engine.py     # Top-level orchestrator
├── interfaces.py          # Protocols
├── services.py            # ResearchService public API
├── dashboard.py           # (existing) dashboard computation
└── README.md
```

## Research Workflow

1. **Provide trade rows** — caller supplies completed trade data (never raw storage).
2. **Define hypothesis** — declarative filter (factor, market, timeframe, regime).
3. **Configure dataset** — optional filters (completed, market, timeframe, etc.).
4. **Run experiment** — runner prepares dataset, splits groups, computes metrics.
5. **Compare** — statistical differences exposed between treatment and baseline.
6. **Report** — structured output with conclusions, warnings, limitations.
7. **Persist** — append-only experiment registry at `data/research/experiments.jsonl`.

## Experiment Lifecycle

```
PENDING → RUNNING → COMPLETED
                  ↘ FAILED
```

Each experiment records:
- ID, title, description
- Hypothesis configuration
- Dataset metadata (count, filters, fingerprint)
- Configuration hash
- Start/end timestamps
- Status, version
- Results (metrics, comparison, report)

## Public API

```python
from scanner.research import ResearchService, Hypothesis

svc = ResearchService()

# Run hypothesis test
exp = svc.run_experiment(
    title="HTF Filter Test",
    rows=trade_rows,
    hypothesis=Hypothesis(
        hypothesis_id="hyp_htf",
        title="HTF filter improves expectancy",
        filter_type="factor",
        filter_key="htf",
    ),
    dataset_config={"completed_only": True},
)

# Compare two groups
cmp = svc.compare(group_a, group_b, label_a="strategy_a", label_b="strategy_b")

# Compute metrics
stats = svc.statistics(trade_rows)

# Retrieve report
report = svc.generate_report(exp.experiment_id)

# Experiment history
history = svc.history(limit=20)
```

## Hypothesis Testing

Supported filter types:

| Type | Description |
|------|-------------|
| `factor` | Trade has factor in `factors` list |
| `market` | Trade market matches key |
| `timeframe` | Trade timeframe matches key |
| `regime` | Trade grade/regime matches key |
| `status_won` | Winning trades only |
| `status_lost` | Losing trades only |
| `custom_field` | Arbitrary field equality |

No hardcoded assumptions — all hypotheses are declarative.

## Metrics

All metrics are deterministic and explainable:

| Metric | Source |
|--------|--------|
| Expectancy | `tracking.summarize()` |
| Profit Factor | `tracking.summarize()` |
| Average R | `tracking.summarize()` |
| Median R | Computed from closed trades |
| Win Rate | `tracking.summarize()` + Wilson intervals |
| Max Drawdown | `tracking.summarize()` |
| Sharpe | `tracking.summarize()` |
| Recovery Factor | `tracking.summarize()` |
| Consistency Score | `tracking.summarize()` |

## Comparison Engine

Supports:

- Strategy vs Strategy
- Filter vs Filter
- Market vs Market
- Timeframe vs Timeframe
- Version vs Version

Every comparison exposes:
- Side-by-side metrics
- Delta and percent change per metric
- Wilson interval overlap (significance proxy)
- Sample size reliability flags
- Winner by expectancy

## Dataset Builder

Experiments never read raw storage. Datasets are built from provided rows:

```python
from scanner.research import DatasetBuilder

builder = DatasetBuilder()
ds = builder.from_rows(trade_rows)
ds = builder.completed(ds)
ds = builder.by_market(ds, "crypto")
ds = builder.by_factor(ds, "htf")
ds = builder.by_similarity_group(ds, event_ids)
```

## Reports

Structured output sections:
- Dataset Summary
- Methodology
- Metrics (treatment/baseline/all)
- Comparison statistics
- Conclusions (deterministic, not AI-generated)
- Warnings (sample size, reliability)
- Limitations (historical bias, no costs modeled)

## Future ML Integration

The research engine is designed as a foundation for future ML sprints:

- **Feature store**: Dataset builder can export filtered groups as ML-ready datasets.
- **Experiment tracking**: Append-only registry compatible with model versioning.
- **Metrics baseline**: Deterministic metrics serve as ground truth for model evaluation.
- **Hypothesis framework**: Declarative filters map directly to feature ablation studies.
- **Comparison engine**: Statistical difference framework extends to model A/B testing.

No ML infrastructure is included in this sprint.

## Rules

- Do NOT modify Pipeline, Similarity, Knowledge, or Recommendation layers.
- Do NOT introduce AI models, LLMs, or dashboards in this module.
- Every experiment must be reproducible from its stored configuration.
- Every metric must be explainable with no hidden calculations.
