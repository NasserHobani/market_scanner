# AIA-01.5 Engineering Report — AI Evaluation Framework

## 1. Executive Summary

Sprint AIA-01.5 delivers a read-only evaluation framework that measures AI Advisor quality after trades close. The platform now treats the AI Advisor like a trading strategy: every completed trade produces a versioned evaluation record, metrics with confidence intervals, provider leaderboards, statistical benchmarks, and scheduled reports.

The framework lives entirely in `scanner/ai_advisor/evaluation/` and does not modify any finalized module (Decision Engine, Prediction, Knowledge, Research, Optimization, Trading Engine, or AI Advisor core). A new widget API endpoint exposes evaluation UI models without page redesign.

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Trade Closed Event                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              AdvisorEvaluationService (facade)               │
│  evaluate_trade │ metrics │ leaderboard │ benchmark │ reports│
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌─────────────────┐ ┌─────────────┐ ┌──────────────────┐
│ EvaluationEngine│ │AdvisorMetrics│ │ ProviderLeaderboard│
│ (core pipeline) │ │ (Wilson CI)  │ │ + ProviderBenchmark│
└────────┬────────┘ └─────────────┘ └──────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────────┐
│ Memory │ │ Evaluation   │
│ (read) │ │ Dataset JSONL│
└────────┘ └──────────────┘
```

**Package structure:** 12 files under `scanner/ai_advisor/evaluation/`.

**Version constants:**
- `EVALUATION_VERSION = "1.0.0"` — engine logic version
- `EVALUATION_SCHEMA_VERSION = "1.0.0"` — dataset record schema

## 3. Evaluation Pipeline

1. **Trigger:** Trade closes with `trade_id`, `trade_result`, and linked `review_id`.
2. **Load:** `AdvisorMemory.load(review_id)` retrieves the advisor review and decision package ID.
3. **Evaluate:** `EvaluationEngine` computes correctness, warning quality, and hallucination flags.
4. **Store:** Record appended to `data/advisor_evaluations.jsonl`.
5. **Update:** `AdvisorMemory.update_performance()` writes outcome back to the original review record.
6. **Aggregate:** `AdvisorMetrics.compute()` recalculates all metrics from the full dataset.

### Correctness Rules

| Advisor Agreement | Trade Outcome | Correct? |
|-------------------|---------------|----------|
| agree             | won           | Yes      |
| disagree          | lost          | Yes      |
| agree             | lost          | No       |
| disagree          | won           | No       |
| partial           | any           | No       |

### Warning Quality

- **Useful warning:** risks listed AND trade lost
- **False warning:** risks listed AND trade won with R ≥ 1.0
- **Missed warning:** no risks AND trade lost with R ≤ −1.0

### Hallucination

Detected from `validation.hallucination_count > 0` on the stored review response.

## 4. Metrics Definitions

Every rate metric includes `value`, `sample_size`, `confidence_interval` (Wilson 95%), and `last_updated`.

| Metric | Definition |
|--------|------------|
| Overall Accuracy | % of evaluations where `advisor_correct = true` |
| Agreement Rate | % where `advisor_agreement = "agree"` |
| Useful Warnings | % where `useful_warning = true` |
| False Warnings | % where `false_warning = true` |
| Missed Warnings | % where `missed_warning = true` |
| Hallucination Rate | % where `hallucination = true` |
| Average Confidence | Mean `advisor_confidence` across evaluations |
| Market/Timeframe/Strategy/Trend Accuracy | Grouped accuracy by dimension |
| Long/Short Accuracy | Grouped by trade direction |

## 5. Calibration Methodology

Confidence calibration uses five buckets: 50–60%, 60–70%, 70–80%, 80–90%, 90–100%.

For each bucket:
- **Expected midpoint:** average of bucket bounds
- **Actual accuracy:** % correct within the bucket
- **Calibration error:** actual − expected midpoint

Overconfident advisors show negative calibration error in high buckets. The daily report recommends recalibration when error < −15 in any bucket.

## 6. Leaderboard Design

`ProviderLeaderboard` groups evaluations by `provider` and ranks by accuracy (descending), then review count.

Per provider:
- Accuracy (with Wilson CI)
- Agreement rate
- Hallucination rate
- Useful reviews count
- Average confidence
- Review count
- Rank

Supported providers: Claude, OpenAI (GPT), Gemini, DeepSeek, Open Source, OpenRouter, Mock.

## 7. Benchmark Design

`ProviderBenchmark.compare(provider_a, provider_b)` pairs evaluations on the **same `decision_package_id`** — ensuring both providers reviewed identical decision packages.

Output:
- **Winner:** provider with higher paired accuracy
- **Metric differences:** accuracy, hallucination rate, useful warnings
- **Statistical confidence:** two-proportion z-test (90%/95%/99% or not significant)
- **Z-score:** raw test statistic

Minimum 2 paired packages required for significance testing.

## 8. Dataset Schema

Each record in `data/advisor_evaluations.jsonl`:

```json
{
  "evaluation_id": "eval_abc123",
  "schema_version": "1.0.0",
  "evaluated_at": "2026-08-09T18:00:00+00:00",
  "trade_id": "trade_001",
  "decision_package_id": "pkg_001",
  "advisor_review_id": "adv_001",
  "provider": "claude",
  "model": "claude-sonnet",
  "prompt_version": "advisor_prompt_v1",
  "trade_result": "won",
  "advisor_prediction": "agree",
  "advisor_agreement": "agree",
  "advisor_confidence": 85.0,
  "advisor_correct": true,
  "hallucination": false,
  "useful_warning": false,
  "false_warning": true,
  "missed_warning": false,
  "execution_date": "2026-08-09",
  "market": "crypto",
  "timeframe": "4h",
  "strategy": "breakout",
  "trend": "bullish",
  "direction": "buy",
  "expectancy": 0.8,
  "profit_factor": 1.5,
  "r_multiple": 1.5,
  "evaluation_version": "1.0.0"
}
```

## 9. Persistence

| Store | Path | Pattern |
|-------|------|---------|
| Evaluation dataset | `data/advisor_evaluations.jsonl` | Append-only JSONL |
| Advisor memory | `data/advisor_memory.jsonl` | Read + update `later_performance` |

The evaluation dataset is the source of truth for metrics. Memory updates link evaluations back to original reviews for audit trail continuity.

## 10. Reporting

### Daily (`AdvisorReport`)
Filters today's evaluations. Includes overall score, provider ranking, best/worst markets, best timeframes, common errors, hallucination summary, and recommendations.

### Weekly (`WeeklyReport`)
Last 7 days of evaluations with same structure.

### Monthly (`MonthlyReport`)
Last 30 days of evaluations with same structure.

### Scheduler (`EvaluationScheduler`)
Entry points: `run_daily()`, `run_weekly()`, `run_monthly()`. No cron implementation — architecture only, ready for external scheduler integration.

### UI Models (`AdvisorReport.to_ui_model()`)
- Advisor Score
- Provider Leaderboard
- Accuracy Trend (by date)
- Calibration Curve
- Recent Evaluations
- Hallucination Summary
- Recommendations

**API:** `GET /api/widgets/ai-advisor-evaluation/`

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Low sample sizes produce misleading accuracy | Wilson CI on every metric; benchmarks require paired packages |
| Evaluation rules may not match all trade types | Rules are explicit and versioned; future sprints can add rule variants |
| Memory rewrite on performance update is O(n) | Acceptable at current scale; AIA-02 can add indexed storage |
| No automatic trade-close hook yet | Service API is ready; integration is a one-line call at trade settlement |
| Partial agreement always marked incorrect | Conservative default; avoids inflating accuracy |

## 12. Future AIA-02

- Automatic evaluation trigger on trade settlement in the trading engine
- Per-prompt-version benchmarking and A/B testing
- Calibration-aware provider routing (send packages to best-calibrated provider)
- Evaluation dashboard page (frontend only, using existing UI models)
- Indexed storage (SQLite or PostgreSQL) for large-scale evaluation history
- Multi-model consensus scoring when `review_multi()` is used in production
- Outcome-weighted scoring (R-multiple magnitude affects correctness weight)

## 13. Test Results

```
python tests_ai_advisor_evaluation.py
```

**Coverage:**
- Dataset persistence and versioning
- Evaluation engine (correctness, warnings, hallucination)
- Memory performance update
- All metrics with confidence intervals
- Calibration buckets (5 buckets)
- Provider leaderboard ranking
- Provider benchmark with z-test
- Daily/weekly/monthly reports
- Scheduler entry points
- Service facade
- UI model generation

All tests pass. Django check passes with no modifications to finalized modules.
