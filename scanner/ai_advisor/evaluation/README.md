# AI Advisor Evaluation Framework (AIA-01.5)

Measures AI Advisor quality after trades close. The AI becomes measurable — evaluated exactly like trading strategies.

## Architecture

```
scanner/ai_advisor/evaluation/
├── __init__.py              # Public API + AdvisorEvaluationService
├── interfaces.py            # Protocols
├── advisor_dataset.py       # Persistent versioned dataset (JSONL)
├── evaluation_engine.py     # Trade closed → evaluate pipeline
├── advisor_metrics.py       # All metrics + calibration buckets
├── leaderboard.py           # Provider ranking
├── benchmark.py             # Provider A vs B comparison
├── advisor_report.py        # Daily report + UI models
├── weekly_report.py         # Weekly report
├── monthly_report.py        # Monthly report
├── scheduler.py             # Scheduler entry points (no cron)
├── README.md
└── ENGINEERING_REPORT.md
```

## Data Flow

```
Trade Closed
    ↓
Load Decision Package (from memory)
    ↓
Load AI Review (from memory)
    ↓
Load Trade Result
    ↓
Evaluate
    ↓
Update Advisor Metrics
    ↓
Store Evaluation (advisor_evaluations.jsonl)
    ↓
Update Provider Score (memory later_performance)
```

## Usage

```python
from scanner.ai_advisor.evaluation import AdvisorEvaluationService

svc = AdvisorEvaluationService()

# After a trade closes
evaluation = svc.evaluate_trade(
    trade_id="trade_001",
    review_id="adv_abc123",
    trade_result={
        "status": "won",
        "r_multiple": 1.5,
        "market": "crypto",
        "timeframe": "4h",
        "strategy": "breakout",
        "direction": "buy",
        "execution_date": "2026-08-09",
    },
)

# Metrics, leaderboard, benchmark
metrics = svc.metrics()
leaderboard = svc.leaderboard()
comparison = svc.benchmark("claude", "openai")

# Reports
daily = svc.daily_report()
weekly = svc.weekly_report()
monthly = svc.monthly_report()

# UI API model
ui = svc.to_ui_model()
```

## API Endpoint

`GET /api/widgets/ai-advisor-evaluation/`

Returns: Advisor Score, Provider Leaderboard, Accuracy Trend, Calibration Curve, Recent Evaluations.

## Strict Rules

- Does NOT modify Decision Engine, Prediction, Knowledge, Research, Optimization, Trading Engine, or AI Advisor core.
- AI Advisor remains read-only.
- This sprint only measures quality.

## Tests

```bash
python tests_ai_advisor_evaluation.py
```
