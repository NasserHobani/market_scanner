# AIA-10.6 Feature Enrichment Report

**Sprint:** AIA-10.6 — Runtime Feature Enrichment  
**Date:** 2026-08-11  
**Status:** Implemented and verified in tests

---

## 1. Before Coverage

Measured on representative scan-path inputs (no fabricated defaults):

| Source | Features | Coverage |
|--------|----------|----------|
| Flattened scan row only (`dict(r)` without `ScoreResult`) | 17–24 / 36 | **47–67%** |
| `ScoreResult` + row context (scoring components, RSI, RVOL, ATR) | ~26 / 36 | **~72%** |

Observed pre-sprint runtime average (persisted snapshots): **~47%** (consistent with AIA-10.5).

---

## 2. After Coverage

With `enrich_snapshot_source()` wired into `capture_from_scan_row()`:

| Scenario | Features | Coverage |
|----------|----------|----------|
| ScoreResult + structure zones + knowledge + similarity + validated research | 36 / 36 | **100%** |
| ScoreResult + mocked collectors (integration test) | 32+ / 36 | **≥88%** |
| Production scan path (collectors best-effort) | varies | **target ≥70%** when engines return data |

Enrichment adds similarity, knowledge, and validated research without recalculating indicators.

---

## 3. Coverage Delta

Synthetic measurement (same decision timestamp, point-in-time safe):

```
Before (row-only):     24/36 = 66.7%
After (full enrich):   36/36 = 100.0%
Delta:                 +33.3 percentage points
```

Typical delta when collectors populate: **+6 to +15 features** (similarity block + knowledge block + research block).

---

## 4. Feature / Category Availability

| Category | Captured from | Notes |
|----------|---------------|-------|
| Platform scoring | `ScoreResult.components`, `recommendation` | score, confidence, grade, RR, side, factor flags |
| Trend | `htf`, `components.trend` | direction, strength, HTF, MTF alignment |
| Momentum | `context.rsi`, `components` | RSI, div component, momentum strength |
| Volatility | `context.atr_pct`, channel | ATR; percentile only if engine provides it |
| Volume | `context.rvol`, `components.volume` | RVOL, participation |
| Structure | `recommendation.analysis.price_action` | BOS/CHoCH from events; S/R distance from zones + close |
| Similarity | `SimilarityService` via layer collector | match_count, win_rate, expectancy; `similarity_dataset_timestamp` |
| Knowledge | `KnowledgeService.capture_scan` | score, patterns, regime, confidence |
| Research | `ExperimentStore` validated only | `research_id`, `validation_status`, `created_at <= decision_ts` |

---

## 5. Missing Features (typical when engines sparse)

When collectors unavailable, snapshots still report honestly:

```json
[
  "match_count", "similarity_score", "historical_win_rate", "historical_expectancy",
  "knowledge_score", "regime", "knowledge_confidence",
  "research_signal", "research_confidence", "research_sample_size",
  "atr_percentile", "choch_count", "support_distance", "resistance_distance"
]
```

`missing_by_category` is stored on each snapshot and aggregated in runtime audit.

---

## 6. Provenance

- Every populated V3 feature has `name`, `value`, `source`, `source_timestamp`, `calculation_version`.
- `validate_snapshot_provenance()` + `validate_provenance()` enforce `source_timestamp <= decision_timestamp`.
- Future provenance timestamps are rejected (`future provenance … > decision_ts`).

**Test result:** PASS (39/39 AIA-10.6 tests, all regression suites green)

---

## 7. Leakage

- No future candles, outcomes, or post-trade lessons in snapshot features.
- Research collector filters `ended_at > decision_timestamp`.
- Similarity uses historical index at query time; `similarity_dataset_timestamp` recorded.
- Adversarial leakage tests pass (AIA-10, AIA-10.5, AIA-10.6).

**Test result:** PASS

---

## 8. Runtime Latency

| Metric | Target | Observed |
|--------|--------|----------|
| Collection latency (mocked collectors) | <100ms | ~22ms |
| Full capture (mocked) | <100ms | PASS in tests |
| Full capture (live collectors) | <100ms aspirational | depends on Knowledge/Similarity I/O |

`capture_latency_ms` and `collection_latency_ms` stored per snapshot.

---

## 9. Dataset V3 Eligible Rows

Unchanged by enrichment alone:

- V3 smoke: **≥20** eligible PIT-linked closed trades — **not ready**
- V3 train: **≥100** eligible rows — **not ready**
- Historical reconstruction coverage remains **~1.5%** (separate from runtime)

Training remains **blocked** until eligibility thresholds pass quality gates.

---

## 10. Prediction Status

**UNAVAILABLE** — correct. No model promotion. Enrichment improves feature honesty, not inference availability.

---

## 11. Fusion Status

Unchanged. Fusion reports `PREDICTION_UNAVAILABLE` when no active promoted model. Feature enrichment does not alter trading behavior.

---

## 12. Remaining Blockers

1. **Similarity** — requires historical match corpus at scan time; marks `similarity_status=unavailable` when empty.
2. **Knowledge** — depends on `KnowledgeService.capture_scan` success; fallback is limited.
3. **Research** — only validated completed experiments; often none at decision time.
4. **ATR percentile** — not computed in scoring context today → `missing_atr` reason.
5. **Structure S/R** — needs `price_action.zones` + `close` in recommendation analysis.
6. **V3 dataset size** — insufficient PIT-linked closed trades for training.

---

## 13. Exact Next Action

1. Deploy and accumulate runtime snapshots on live scans.
2. Monitor `scripts/monitor_aia10_runtime.py` AIA-10.6 section for real coverage distribution.
3. If similarity/knowledge remain top missing categories, improve **engine output availability at scan time** (not snapshot recalculation).
4. Continue collecting closed trades with `feature_snapshot_id` until V3 smoke (≥20) then train gate (≥100).
5. Re-evaluate V3 model only after eligibility + leakage + quality gates pass.

---

## Implementation Summary

| File | Change |
|------|--------|
| `scanner/feature_snapshots/enrichment.py` | **NEW** — adapter layer, collectors, coverage meta |
| `scanner/feature_snapshots/service.py` | Enrichment hook, LLM evidence IDs, UDP meta |
| `scanner/feature_snapshots/builder.py` | Structure from events/zones, div component, channel vol |
| `scanner/feature_snapshots/contract.py` | `missing_by_category`, `enrichment_meta`, `collection_latency_ms` |
| `scanner/feature_snapshots/runtime_audit.py` | `enrichment_runtime_report()` |
| `web/dashboard/management/commands/scan.py` | Pass `ScoreResult` to capture |
| `scripts/monitor_aia10_runtime.py` | AIA-10.6 monitor section |
| `tests_ai_aia106_enrichment.py` | **NEW** — 39 tests |

---

## Tests

```
tests_ai_aia106_enrichment.py     39/39 PASS
tests_ai_aia105_runtime.py        32/32 PASS
tests_ai_aia10_features.py        23/23 PASS
tests_prediction_improvement.py   13/13 PASS
tests_ai_fusion.py                17/17 PASS
tests_ai_unified_package.py       28/28 PASS
tests_ai_advisor.py               47/47 PASS
tests_ai_learning.py              58/58 PASS
tests_ai_advisor_evaluation.py    44/44 PASS
```

---

## Principle

Feature enrichment succeeded because data is **real**, **point-in-time safe**, **provenance-complete**, and **non-blocking**. Coverage improves when platform engines provide outputs at decision time — never by fabrication.

If V3 still fails after sufficient eligible rows: **keep Prediction UNAVAILABLE**. That is valuable evidence about predictive signal in current features.
