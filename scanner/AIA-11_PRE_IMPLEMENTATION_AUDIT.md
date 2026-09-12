# AIA-11 Pre-Implementation Audit

**Date:** 2026-08-11  
**Repo:** market-scanner  
**Rule:** No architecture redesign · No gate weakening · No fabricated features · No future data

---

## Decision-time pipeline

```
OHLCV (local sync / MD-01)
 → score_with_recommendation / score_symbol
 → recommend.build
 → feature_store.write_snapshot (fs_*)
 → PointInTimeSnapshotService.capture_from_scan_row(+ ScoreResult)
      → enrichment.enrich_snapshot_source (AIA-10.6)
      → builder.extract_v3_features → pit_*
 → ScanResult.feature_snapshot_id
 → Trade copies fs_* on open
 → dataset_v3.encode_row_v3 → train / quality gates → ACTIVE-only fusion
```

**Decision timestamp** = scan candle / recommendation timestamp.  
**Absolute rule:** `feature_timestamp <= decision_timestamp`.

---

## Coverage (observed)

| Path | Coverage |
|------|----------|
| Historical trade↔PIT | ~1.5% |
| Pre-enrichment runtime | ~44–50% |
| ScoreResult + context | ~72% |
| Full enrich (engines available) | up to 100% in synthetic |
| Target AIA-11 | ≥80% runtime, prefer ≥90% |

---

## Per-feature audit (36 V3)

| Feature | Source | At decision? | PIT today | Gap / action |
|---------|--------|--------------|-----------|--------------|
| trend_direction | scoring htf+trend | yes | yes | reuse |
| trend_strength | abs(score)/100 proxy | yes | yes | document proxy |
| higher_timeframe_trend | htf_bias | yes | yes | reuse |
| multi_timeframe_alignment | htf==trend | yes | yes | reuse |
| rsi | pine.rsi → context | yes | yes | reuse |
| momentum_state | components.rsi | yes | yes w/ ScoreResult | ensure ScoreResult path |
| divergence | components.div | yes | yes w/ ScoreResult | reuse |
| momentum_strength | abs(components.rsi) | yes | yes | reuse |
| atr_pct | pine.atr → context | yes | yes | reuse |
| atr_percentile | **not computed** | n/a | **NO** | **P0:** add from ATR series at decision bar |
| volatility_regime | channel / volatility | partial | partial | tighten `"—"` channel |
| rvol | volume.rvol | yes | yes | reuse |
| volume_participation | looks for `components.volume` | n/a | **NO** | **P0:** map spike/cmf/mfi |
| volume_trend | components.obv_macd | yes | yes | reuse |
| bos_count | price_action events | yes | partial (0 dropped) | **P0:** emit 0 |
| choch_count | price_action events | yes | partial | **P0:** emit 0 |
| structure_direction | pa.trend | yes | partial | reuse |
| support_distance | demand zones | yes | partial | reuse |
| resistance_distance | supply zones | yes | partial | reuse |
| match_count | SimilarityService | yes | partial | reuse collector |
| similarity_score | sim stats | yes | partial | reuse |
| historical_win_rate | sim win_rate | yes | partial | PIT index only |
| historical_expectancy | sim avg_r | yes | partial | PIT index only |
| knowledge_score | KnowledgeService | yes | partial | reuse |
| detected_pattern_count | knowledge groups | yes | yes (often 0) | reuse |
| regime | market_environment | partial | partial | reuse |
| knowledge_confidence | **never set** | n/a | **NO** | **P0:** map reco confidence |
| research_* | validated experiments | rare | often missing | keep validated-only filter |
| score | ScoreResult.score | yes | yes | reuse |
| confidence | recommend.build | yes | partial | reuse |
| grade_enc | recommendation.grade | yes | partial | reuse |
| risk_reward | recommendation.rr | yes | partial | reuse |
| expected_r | duplicate of rr | yes | partial | reuse |
| side_buy | recommendation.side | yes | biased default | **P0:** no silent buy default |

---

## Quality gates (DO NOT LOWER)

| Gate | Threshold |
|------|-----------|
| Snapshot GOOD | ≥90% coverage |
| Snapshot PARTIAL | ≥70% |
| V3 smoke | ≥20 eligible rows |
| V3 train | ≥100 eligible rows |
| OOS vs baseline | ≥ +2% |
| Walk-forward stdev | ≤ 0.15 |
| Calibration mean error | ≤ 0.20 |
| Promotion | explicit only; ACTIVE-only inference |

---

## Leakage risks

| Area | Risk | Mitigation |
|------|------|------------|
| Similarity aggregates | low | index at decision time; dataset cutoff |
| Research | medium | `ended_at <= decision_ts` + VALIDATED only |
| Future trades in hist_* | high if naive DB | PIT similarity only |
| atr_percentile | none if computed from bars ≤ decision | lookback on existing ATR series |

---

## Files to modify (AIA-11)

1. `scanner/scoring/engine.py` — atr_percentile in context  
2. `scanner/feature_snapshots/builder.py` — volume_participation, bos/choch zeros, side, volatility, knowledge_confidence  
3. `scanner/feature_snapshots/enrichment.py` — structure zeros, knowledge confidence, missing reasons  
4. `scanner/feature_snapshots/service.py` / `runtime_audit.py` — category coverage + missingness  
5. `scanner/predictive/dataset_v3.py` + quality reports  
6. Training path + verify_aia11.py + tests  
7. Dashboard prediction observability  

**Do not:** rewrite engines, lower gates, auto-promote, send OHLC to LLM.

---

## Exact next implementation steps

1. Close P0 feature gaps (honest reuse only).  
2. Measure runtime coverage after enrichment.  
3. Build Dataset V3 + leakage + feature quality reports.  
4. Train only if ≥100 eligible (smoke ≥20).  
5. Evaluate with existing gates → CANDIDATE or NOT_PROMOTED.  
6. Keep Prediction UNAVAILABLE unless explicitly promoted.
