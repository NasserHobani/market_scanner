# AIA-10 — Point-in-Time Feature Snapshot Architecture

## Decision Timestamp

The platform decision occurs at **scan/recommendation time** — when `ScanResult` is written with `candle_time`, score, and recommendation. This is **before** trade open and **before** any outcome exists.

```
Market Data (OHLCV, indicators)
    ↓
Scanner (`scanner/scoring/engine.py`)
    ↓
Recommendation (`scanner/analysis/recommend.py`)
    ↓
Flat snapshot `fs_*` (`scanner/features/store.py`)     ← legacy V1/V2 join
    ↓
Point-in-time snapshot `pit_*` (`scanner/feature_snapshots/`)  ← AIA-10 V3
    ↓
Decision / Trade open (`scanner/trades.py` — copies `feature_snapshot_id`)
    ↓
Outcome (WON/LOST) — label only, never in features
    ↓
Dataset V3 (`scanner/predictive/dataset_v3.py`)
    ↓
Prediction (`PredictionAdapter` — ACTIVE model only)
    ↓
Fusion (`scanner/ai_fusion/`)
```

## Production Flow (AIA-10)

```
Market Data → Analysis → Recommendation → Feature Snapshot → Decision → Trade
```

Hook: `web/dashboard/management/commands/scan.py` calls `PointInTimeSnapshotService.capture_from_scan_row()` after `feature_store.write_snapshot()`. Failures are logged; trading is **not** blocked.

## FeatureSnapshot Contract

Canonical type: `scanner/feature_snapshots/contract.py` → `PointInTimeSnapshot`

| Field | Purpose |
|-------|---------|
| `snapshot_id` | `pit_{sha256}` |
| `decision_timestamp` | When platform decided |
| `feature_timestamp` | When features were known (`<= decision_timestamp`) |
| `features` | Numeric V3 feature vector |
| `provenance` | Per-feature source, timestamp, calc version |
| `coverage` | Fraction of V3 spec populated |
| `status` | CREATED / PARTIAL / FAILED / REJECTED / HISTORICAL_* |
| `legacy_snapshot_id` | Link to `fs_*` flat snapshot |

## V3 Feature Categories

Registry: `scanner/predictive/feature_registry.py` (`V3_SPECS`, 36 features)

- Trend, Momentum, Volatility, Volume, Structure, Similarity, Knowledge, Research (validated only), Platform recommendation

Builder: `scanner/feature_snapshots/builder.py` — extracts only from provided scan/knowledge context; never fabricates.

## UDP Integration

`UnifiedDecisionPackage.feature_snapshot` exposes:

```json
{
  "available": true,
  "snapshot_id": "pit_...",
  "version": "3.0.0",
  "coverage": 0.47,
  "quality": "PARTIAL",
  "feature_count": 17
}
```

Separate from `prediction` and `feature_intelligence`. LLM receives summarized snapshot via `PointInTimeSnapshotService.summarize_for_llm()` — no raw OHLC.

## Historical Reconstruction

`scanner/feature_snapshots/historical.py` upgrades `fs_*` rows from `data/features/snapshots.jsonl` when available. Missing data → `HISTORICAL_SNAPSHOT_UNAVAILABLE` (no fabrication).

## Safety

- No trading engine changes
- Snapshot failure never blocks scan/trade
- No LLM-generated features
- Quality gates unchanged (AIA-08)
- `NOT_PROMOTED` is a valid outcome
