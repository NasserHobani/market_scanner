# AIA-10.5 — Runtime PIT Snapshot Validation

## Objective

Validate the production snapshot pipeline lifecycle without training models:

```
SCAN → RECOMMENDATION → PIT SNAPSHOT → TRADE → CLOSE → SNAPSHOT LINK → DATASET ELIGIBILITY
```

## Implementation Summary

| Component | Path |
|-----------|------|
| Runtime audit | `scanner/feature_snapshots/runtime_audit.py` |
| Configurable thresholds | `scanner/feature_snapshots/config.py` |
| Monitor script | `scripts/monitor_aia10_runtime.py` |
| Dashboard API | `GET /api/snapshots/runtime/` |
| Tests | `tests_ai_aia105_runtime.py` (29/29) |

## 1. Snapshot Creation Point

**Location:** `web/dashboard/management/commands/scan.py` (~line 306)

After `feature_store.write_snapshot()` → `fs_*`, then:

```python
PointInTimeSnapshotService().capture_from_scan_row(..., legacy_snapshot_id=snapshot_id)
```

**Decision timestamp** = scan `candle_time` (before trade open, before outcome).

**Recommendation ID** = `reco_{fs_*}` (1:1 with ScanResult flat snapshot).

## 2. Runtime Quality Classification (Configurable)

| Rating | Criteria |
|--------|----------|
| **GOOD** | coverage ≥ 90%, valid provenance, no leakage |
| **PARTIAL** | coverage ≥ 70%, valid provenance, no leakage |
| **FAILED** | coverage < 70%, leakage, or invalid provenance |

Config: `RuntimeSnapshotConfig` in `config.py`.

## 3. Failure Reasons (Not Generic "Partial")

Each snapshot stores `failure_reasons[]`, e.g.:

- `missing_rsi`, `missing_rvol`, `missing_structure`
- `missing_similarity`, `missing_research`, `missing_knowledge`
- `missing_components`, `low_coverage`, `invalid_provenance`

Exposed in UDP `feature_snapshot.failure_reasons` and dashboard UI.

## 4. Current Production Evidence

| Metric | Value |
|--------|-------|
| Runtime snapshot count | Accumulates per scan post-deploy |
| Historical coverage | ~1.5% (3/203) — separate metric |
| Runtime coverage | Measured from `events.jsonl` + `by_legacy` index |
| Average feature coverage | ~47–50% on scan-only path (expected until components enriched) |
| GOOD / PARTIAL / FAILED | Reported by monitor |
| V3 eligible rows | Low until runtime snapshots link to closed trades |
| Prediction | **UNAVAILABLE** (correct — no training) |

### Typical Scan-Path Missing Features

Without full `components`/`context`/`similarity`/`research` at scan time:

- `missing_similarity`, `missing_research`, `missing_structure` (partial)
- Platform features (`score`, `rsi`, `rvol`, `confidence`) usually present

**Next action:** Enrich scan row with scoring `components` and wire similarity/knowledge at capture time to raise coverage above 70%.

## 5. Linkage Model

```
ScanResult.feature_snapshot_id (fs_*)
    → PointInTimeSnapshot.legacy_snapshot_id
    → index.by_legacy[fs_*] → pit_*
    → Trade.feature_snapshot_id (copy on open)
    → Dataset V3 via encode_row_v3()
```

**Immutability:** `content_hash` on snapshot; outcome never writes back to PIT store.

## 6. Leakage

- Provenance timestamp ≤ decision timestamp
- Adversarial tests: future RSI/ATR/volume/structure/similarity/outcome → **LEAKAGE_DETECTED**
- Events logged to `data/feature_snapshots/events.jsonl`

## 7. UDP / LLM

`UnifiedDecisionPackage.feature_snapshot`:

- `available`, `snapshot_id`, `recommendation_id`, `coverage_pct`, `failure_reasons`
- `summary_by_category`: trend, momentum, volatility, volume, structure, similarity, knowledge
- No raw OHLC
- `evidence_id` for Claude/Qwen traceability

## 8. Dataset V3 Eligibility

| Condition | Result |
|-----------|--------|
| PIT snapshot + provenance + no leakage | Eligible |
| No `fs_*` / no `pit_*` | Rejected: `historical_snapshot_unavailable` |
| Invalid / leakage | Rejected: `leakage:...` |

**Training gate:** `v3_smoke_min_rows=20`, `v3_train_min_rows=100` — model evaluation skipped until met.

## 9. Performance

Target: **< 100ms** per snapshot (no Claude/Qwen/Research/Training).

Measured via `capture_latency_ms` on snapshot + `events.jsonl` latency stats.

## 10. Monitor Status Rules

| Status | Condition |
|--------|-----------|
| **PASS** | runtime coverage ≥ target, no leakage, valid provenance |
| **WARNING** | coverage below target or partial snapshots |
| **FAIL** | leakage or corrupted provenance or broken lifecycle |

Run: `python scripts/monitor_aia10_runtime.py`

## 11. Tests

```
python tests_ai_aia105_runtime.py  # 29/29
python tests_ai_aia10_features.py  # 23/23
```

All AIA-08/09/unified regression suites pass.

## 12. Blockers

1. Historical 1.5% linkage — cannot fabricate; runtime path is the fix
2. Scan-only feature coverage often < 70% → runtime quality FAILED/PARTIAL until enrichment
3. V3 eligible rows < 20 — **do not train yet**

## 13. Exact Next Action

1. Deploy and run production scans; monitor with `monitor_aia10_runtime.py`
2. Enrich `capture_from_scan_row` with similarity + knowledge context at scan time
3. When `v3_eligible_trades >= 100` and runtime coverage ≥ 80%, proceed to V3 model experiment

**Do not promote models or lower quality gates.**
