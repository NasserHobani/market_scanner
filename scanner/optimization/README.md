# Strategy Optimization Engine

Deterministic strategy parameter optimization for the CS Edge AI Platform.

**No reinforcement learning. No evolutionary algorithms. No AutoML. Optimization only.**

## Purpose

Search for better strategy parameters using deterministic grid search, seeded random search, and walk-forward optimization. Ranks parameter sets by expectancy, profit factor, win rate, drawdown, and out-of-sample performance.

## Architecture

```
scanner/optimization/
├── optimization_engine.py    # Core orchestrator
├── optimizer.py              # Method factory (grid/random/walk_forward)
├── parameter_space.py        # Parameter definitions and constraints
├── grid_search.py            # Exhaustive grid search
├── random_search.py          # Seeded random search
├── walk_forward_optimizer.py # Train/validation rolling optimization
├── evaluation.py             # Parameter evaluation and filtering
├── ranking.py                # Leaderboard generation
├── report.py                 # Optimization reports
├── experiment_registry.py    # Append-only JSONL persistence
├── interfaces.py             # Protocol definitions
├── services.py               # OptimizationService public API
└── README.md
```

## Optimization Pipeline

```
Trade Rows
    ↓
Parameter Space Definition
    ↓
Search Method (grid / random / walk_forward)
    ↓
For each parameter set:
    Apply filters → Compute metrics
    ↓
Rank by composite score
    ↓
Generate Report + Leaderboard
    ↓
Persist to experiment registry
```

## Public API

```python
from scanner.optimization import (
    OptimizationService, ParameterSpace, Parameter, ParameterType,
    OptimizationMethod,
)

svc = OptimizationService()

space = ParameterSpace()
space.add(Parameter("min_score", ParameterType.INTEGER.value, low=60, high=80, step=10))
space.add(Parameter("require_htf", ParameterType.BOOLEAN.value))

result = svc.optimize(
    trade_rows,
    space,
    method="grid",
    title="HTF Score Optimization",
)

# Single evaluation
metrics = svc.evaluate(trade_rows, {"min_score": 70, "require_htf": True})

# Leaderboard
board = svc.leaderboard(result["experiment_id"])

# History
past = svc.history(limit=20)
```

## Parameter Space

| Type | Description | Example |
|------|-------------|---------|
| `numeric` | Float with range and step | `min_confidence: 0.5–0.9, step 0.1` |
| `integer` | Int with range and step | `min_score: 60–80, step 10` |
| `boolean` | True/False | `require_htf` |
| `categorical` | Fixed choices | `min_grade: A, B, C` |

Constraints are cross-parameter validation rules. Fixed parameters are held constant during search.

## Walk-Forward Optimization

```
[── Train Window ──][── Validation ──]
         step →
              [── Train ──][── Validation ──]
```

- Trades sorted chronologically — no look-ahead
- Optimize on train window using inner grid/random search
- Validate best params on OOS validation window
- Rolling evaluation across multiple folds
- Final result includes mean OOS expectancy

## Ranking Weights

| Metric | Weight |
|--------|--------|
| Expectancy | 0.35 |
| Profit Factor | 0.20 |
| Average R | 0.15 |
| Win Rate | 0.10 |
| OOS Expectancy | 0.20 |

## Reports

Each optimization produces a report with:
- Best parameters and metrics
- Improvement over baseline
- OOS metrics (walk-forward)
- Confidence score (high/medium/low)
- Warnings (low sample, negative OOS, etc.)

## Rules

- Do NOT modify previous platform layers
- Do NOT execute trades
- No UI, dashboard, REST API, or LLM
- Trade rows supplied by caller — never read from raw storage
