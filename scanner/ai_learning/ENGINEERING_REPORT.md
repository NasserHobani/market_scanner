# AIA-02 Principal Architect Report — AI Learning & Reflection Engine

## 1. Executive Summary

Sprint AIA-02 introduces continuous learning to the CS Edge Quant Platform. The Learning Engine reads completed AI evaluations, trade outcomes, research results, and optimization data — then produces structured lessons, knowledge proposals, research hypotheses, and ranked improvement candidates.

**Critical constraint:** Learning is purely advisory. It never modifies Knowledge, Prediction, Optimization, Decision, Trading, Research, or the AI Advisor. Every output requires human approval and research validation before any platform change.

The package `scanner/ai_learning/` contains 13 files with append-only persistence, a full learning cycle orchestrator, and a widget API endpoint for UI consumption without page redesign.

## 2. Learning Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    READ-ONLY INPUTS                              │
│  Evaluations │ Trade Outcomes │ Research │ Optimization │ Pred  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LearningEngine.run_cycle()                   │
│  Reflect → Detect → Generate Lessons → Propose → Hypothesize    │
│  → Rank → Report → Persist                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   Lessons    │  │ Knowledge        │  │  Hypotheses      │
│  (NEW status)│  │ Proposals        │  │  (for Research)  │
└──────────────┘  └──────────────────┘  └──────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Human Approval   │
                    │ + Research Valid │
                    └─────────────────┘
```

**Version:** `LEARNING_VERSION = "1.0.0"`

**Public API:** `LearningService` facade in `scanner/ai_learning/__init__.py`

## 3. Reflection Pipeline

`ReflectionEngine.reflect()` filters evaluations by scope:

| Scope Parameter | Effect |
|----------------|--------|
| `last_n` | Last N evaluations |
| `last_week` | Evaluations from past 7 days |
| `last_month` | Evaluations from past 30 days |
| `market` | Filter by market |
| `timeframe` | Filter by timeframe |
| `strategy` | Filter by strategy |
| `provider` | Filter by AI provider |

Output includes accuracy (with Wilson CI), failure/success summaries grouped by reason, provider, and market.

## 4. Lesson Schema

Every lesson stored in `data/learning_lessons.jsonl`:

```json
{
  "lesson_id": "lesson_abc123",
  "schema_version": "1.0.0",
  "title": "Recurring AI failure: wrong agreement",
  "description": "AI failed 3 times due to wrong agreement...",
  "supporting_evidence": ["eval_001", "eval_002"],
  "sample_size": 3,
  "confidence": 30.0,
  "affected_markets": ["crypto"],
  "affected_strategies": ["breakout"],
  "affected_providers": ["claude"],
  "affected_timeframes": ["4h"],
  "created_at": "2026-08-09T19:00:00+00:00",
  "status": "NEW",
  "source": "failure_analysis",
  "pattern_type": "wrong_agreement",
  "lesson_version": "1.0.0"
}
```

### Status Lifecycle

`NEW` → `UNDER_REVIEW` → `VALIDATED` | `REJECTED` → `ARCHIVED`

No automatic activation. Status changes require explicit `update_lesson_status()` call.

## 5. Pattern Detection

`PatternDetector` identifies evidence-backed recurring patterns:

| Pattern Type | Trigger |
|-------------|---------|
| `advisor_accuracy_drop` | Provider accuracy < 50% over ≥3 evaluations |
| `repeated_hallucination` | ≥2 hallucination events |
| `timeframe_specific_failure` | ≥60% failure rate on a timeframe (≥3 trades) |
| `strategy_specific_failure` | ≥60% failure rate on a strategy (≥3 trades) |
| `prediction_overconfidence` | High confidence (≥85%) + incorrect |
| `research_disagreement` | Research verdict disagrees with platform |
| `similarity_below_threshold` | Similarity score < 0.5 |
| `low_liquidity_failure` | Low liquidity trades correlated with failures |

Every pattern includes `supporting_evidence`, `sample_size`, and `confidence`.

## 6. Proposal Generation

`KnowledgeProposals` generates proposals mapped to affected modules:

| Pattern | Affected Module |
|---------|----------------|
| Hallucination / accuracy drop | `ai_advisor` |
| Timeframe failure | `decision` |
| Strategy failure | `optimization` |
| Similarity below threshold | `similarity` |
| Research disagreement | `research` |
| Prediction overconfidence | `prediction` |
| Low liquidity | `knowledge` |

Each proposal contains: `proposal_id`, `reason`, `supporting_lessons`, `expected_benefit`, `confidence`, `affected_module`, `required_experiment`.

**Never writes to Knowledge module.**

## 7. Hypothesis Framework

`HypothesisGenerator` produces research-ready hypotheses:

- "Increase Similarity threshold from current to 0.6+"
- "Disable {strategy} strategy under current market conditions"
- "Tighten evidence grounding validation in advisor prompts"
- "Reduce position size during low liquidity periods"

Each hypothesis includes: `statement`, `expected_outcome`, `supporting_evidence`, `sample_size`, `confidence`, `status: NEW`.

**Does NOT execute experiments.** Research module validates separately.

## 8. Improvement Ranking

`ImprovementCandidates.rank()` scores every lesson, proposal, and hypothesis:

| Factor | Weight |
|--------|--------|
| Impact | 30% |
| Confidence | 25% |
| Evidence count | 20% |
| Sample size | 15% |
| Inverse risk | 10% |

Sorted highest `composite_score` first. Risk weights vary by pattern type (e.g., `low_liquidity_failure` = 0.7 risk, `success_cluster` = 0.1 risk).

## 9. Persistence

| Store | Path | Content |
|-------|------|---------|
| Lessons | `data/learning_lessons.jsonl` | Structured lessons |
| Proposals | `data/learning_proposals.jsonl` | Knowledge proposals |
| Hypotheses | `data/learning_hypotheses.jsonl` | Research hypotheses |
| Reports | `data/learning_reports.jsonl` | Reflection reports |

All stores are append-only JSONL with `schema_version` on every record. Lesson status updates rewrite the file (same pattern as evaluation memory).

**Read-only inputs:** `AdvisorEvaluationDataset` is read, never modified.

## 10. Risks

| Risk | Mitigation |
|------|------------|
| Learning could be mistaken for auto-modification | `advisory_only: true` flag on all API responses; no write paths to other modules |
| Low sample lessons generate noise | Minimum sample thresholds (≥2 for lessons, ≥3 for patterns) |
| Proposal overload | Ranking limits top candidates; status lifecycle requires human review |
| Status rewrite is O(n) | Acceptable at current scale; AIA-03 can add indexed storage |
| Pattern false positives | Every pattern requires supporting evidence IDs |
| Hypothesis without experiment | Each proposal includes `required_experiment` field |

## 11. Future AIA-03

- Automatic learning cycle trigger after evaluation batch completes
- Lesson review UI with approve/reject workflow
- Integration bridge: validated hypotheses → Research experiment queue
- Integration bridge: validated proposals → Knowledge change requests
- Provider-specific learning profiles
- Cross-market pattern correlation
- Lesson deduplication (merge similar lessons)
- Indexed storage for large-scale learning history
- Learning effectiveness tracking (did validated lessons improve metrics?)

## 12. Test Results

```
python tests_ai_learning.py
```

**Coverage:**
- Lesson repository persistence and status lifecycle
- Learning history (proposals, hypotheses, reports)
- Reflection with scope filters (last_n, market)
- Pattern detection (8 pattern types + context inputs)
- Lesson generation from patterns, failures, successes
- Knowledge proposal generation with affected modules
- Hypothesis generation (advisory only)
- Improvement candidate ranking
- Reflection reports (daily) with provider comparison
- UI model generation
- Full learning cycle with persistence
- LearningService facade
- Version constants

All tests pass. Django check passes. No modifications to finalized modules.
