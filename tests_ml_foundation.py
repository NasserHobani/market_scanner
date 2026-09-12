# -*- coding: utf-8 -*-
"""Unit tests for scanner.ml foundation — run: python tests_ml_foundation.py"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ml import (
    DatasetExporter,
    DatasetRegistry,
    DatasetValidator,
    FeatureVectorBuilder,
    LabelName,
    LabelStore,
    MLFeatureRegistry,
    MLFoundationService,
    PreprocessingPipeline,
)
from scanner.ml.feature_store import FeatureStore, MLDataset
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _feature_snapshot(i: int, *, market: str = "crypto", tf: str = "4h",
                      grade: str = "A", htf: int = 1) -> dict:
    sid = f"fsnap_{i:04d}"
    eid = f"evt_{i:04d}"
    return {
        "snapshot_id": sid,
        "event_id": eid,
        "symbol": "BTCUSDT",
        "market": market,
        "timeframe": tf,
        "candle_time": datetime(2025, 1, 1 + i % 28, 12, 0,
                                tzinfo=timezone.utc).isoformat(),
        "final_grade": grade,
        "final_score": 72.0 + i,
        "feature_registry": {
            "rsi": {"name": "rsi", "value": 55.0 + i, "source": "score_context",
                    "calculation_module": "indicators", "calculation_version": "1.0"},
            "score": {"name": "score", "value": 70.0 + i, "source": "score_context",
                      "calculation_module": "scoring", "calculation_version": "1.0"},
            "htf_bias": {"name": "htf_bias", "value": htf, "source": "score_context",
                         "calculation_module": "htf", "calculation_version": "1.0"},
            "atr_pct": {"name": "atr_pct", "value": 2.1, "source": "score_context",
                        "calculation_module": "indicators", "calculation_version": "1.0"},
        },
        "raw_components": {"trend": 1, "rsi": 1, "vwap": 0, "spike": -1},
        "factor_labels": ["htf", "confluence"],
    }


def _trade_row(i: int, *, status: str = WON, r: float = 2.0) -> dict:
    return {
        "event_id": f"evt_{i:04d}",
        "feature_snapshot_id": f"fsnap_{i:04d}",
        "status": status,
        "r_multiple": r,
        "market": "crypto",
        "timeframe": "4h",
        "symbol": "BTCUSDT",
    }


N = 25
SNAPSHOTS = [_feature_snapshot(i) for i in range(N)]
TRADES = [
    _trade_row(i, status=WON if i % 3 != 0 else LOST,
               r=2.0 if i % 3 != 0 else -1.0)
    for i in range(N)
]

# ── Feature Registry ───────────────────────────────────────────────────────

reg = MLFeatureRegistry()
check("FeatureRegistry has rsi", reg.get("rsi") is not None)
check("FeatureRegistry list_all", len(reg.list_all()) >= 10, str(len(reg.list_all())))
check("FeatureRegistry training features", len(reg.list_training()) >= 5)
check("FeatureRegistry components", reg.get("c_trend") is not None)
check("FeatureRegistry schema_version", reg.schema_version() == "1.0.0")

# ── Feature Vector Builder ─────────────────────────────────────────────────

vec = FeatureVectorBuilder().from_feature_snapshot(SNAPSHOTS[0])
check("FeatureVector has values", len(vec.values) > 0, str(len(vec.values)))
check("FeatureVector column_order", len(vec.column_order) > 0)
check("FeatureVector rsi", vec.values.get("rsi") is not None, str(vec.values.get("rsi")))
check("FeatureVector components", vec.values.get("c_trend") == 1)
check("FeatureVector to_flat_list", len(vec.to_flat_list()) == len(vec.column_order))
check("FeatureVector deterministic",
      vec.values == FeatureVectorBuilder().from_feature_snapshot(SNAPSHOTS[0]).values)

# ── Label Store ────────────────────────────────────────────────────────────

labels = LabelStore()
extracted = labels.extract(TRADES[1])  # i=1 → won
check("Label winner", extracted[LabelName.WINNER.value] == 1)
check("Label r_multiple", extracted[LabelName.R_MULTIPLE.value] == 2.0)
check("Label binary_win", extracted[LabelName.BINARY_WIN.value] == 1)
check("Label loser trade", labels.extract(TRADES[0])[LabelName.LOSER.value] == 1)
check("Label list_all", len(labels.list_all()) >= 6)
check("Label deterministic",
      labels.extract(TRADES[0]) == labels.extract(TRADES[0]))

# ── Feature Store ──────────────────────────────────────────────────────────

store = FeatureStore()
rows = store.build_rows(feature_snapshots=SNAPSHOTS, trade_rows=TRADES)
check("FeatureStore join", len(rows) == N, str(len(rows)))
check("FeatureStore has features", "rsi" in rows[0].features)
check("FeatureStore has labels", LabelName.R_MULTIPLE.value in rows[0].labels)

dataset = store.build_dataset(
    dataset_id="mls_test",
    feature_snapshots=SNAPSHOTS,
    trade_rows=TRADES,
)
check("MLDataset row_count", dataset.row_count == N, str(dataset.row_count))
check("MLDataset column_order", len(dataset.column_order) > 0)
check("MLDataset label_columns", len(dataset.label_columns) >= 6)

# ── Preprocessing ──────────────────────────────────────────────────────────

preprocessed = PreprocessingPipeline().transform(dataset)
check("Preprocessing transforms", preprocessed.row_count == N)
check("Preprocessing no null rsi",
      all(r.features.get("rsi") is not None for r in preprocessed.rows))
check("Preprocessing filter tag",
      "preprocessing:deterministic" in preprocessed.filters_applied)
check("Preprocessing grade encoded",
      isinstance(preprocessed.rows[0].features.get("final_grade"), int))

# ── Validation ───────────────────────────────────────────────────────────

valid = DatasetValidator().validate(preprocessed)
check("Validation valid dataset", valid.valid, str(valid.to_dict()))
check("Validation row_count", valid.row_count == N)

empty_ds = MLDataset(dataset_id="empty", rows=[])
invalid = DatasetValidator().validate(empty_ds)
check("Validation empty dataset", not invalid.valid)
check("Validation empty error", any(i.code == "EMPTY_DATASET" for i in invalid.issues))

# ── Dataset Export ─────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)

    csv_result = DatasetExporter().export(preprocessed, tmp_path / "data.csv", fmt="csv")
    check("Export CSV", Path(csv_result.path).exists())
    check("Export CSV rows", csv_result.row_count == N)
    check("Export CSV meta", (tmp_path / "data.meta.json").exists())

    json_result = DatasetExporter().export(preprocessed, tmp_path / "data.json", fmt="json")
    check("Export JSON", Path(json_result.path).exists())
    payload = json.loads(Path(json_result.path).read_text(encoding="utf-8"))
    check("Export JSON metadata", "metadata" in payload)
    check("Export JSON rows", len(payload["rows"]) == N)

    parquet_result = DatasetExporter().export(preprocessed, tmp_path / "data.parquet", fmt="parquet")
    check("Export Parquet interface", parquet_result.format == "parquet")
    check("Export Parquet sidecar", Path(parquet_result.path).exists())

# ── Dataset Registry ───────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    reg_path = Path(tmp) / "registry.jsonl"
    registry = DatasetRegistry(reg_path)
    entry = registry.register(
        dataset_id="mls_reg_test",
        row_count=N,
        feature_count=len(preprocessed.column_order),
        label_columns=preprocessed.label_columns,
        research_experiment_id="rex_test",
    )
    check("Registry register", entry.metadata.dataset_id == "mls_reg_test")
    check("Registry fingerprint", entry.metadata.fingerprint.startswith("mlfp_"))
    check("Registry load", registry.load("mls_reg_test").metadata.row_count == N)
    check("Registry history", len(registry.history()) >= 1)

# ── MLFoundationService ────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    reg_path = Path(tmp) / "registry.jsonl"
    svc = MLFoundationService(registry=DatasetRegistry(reg_path))

    built = svc.build_dataset(
        feature_snapshots=SNAPSHOTS,
        trade_rows=TRADES,
        research_experiment_id="rex_svc",
    )
    check("Service build_dataset", built.row_count == N)
    check("Service registered", len(svc.dataset_history()) >= 1)

    export_path = Path(tmp) / "export.csv"
    exp_result = svc.export_dataset(built, export_path, fmt="csv")
    check("Service export_dataset", Path(exp_result.path).exists())

    val = svc.validate_dataset(built)
    check("Service validate_dataset", val.valid)

    feats = svc.list_features()
    check("Service list_features", len(feats) >= 10, str(len(feats)))

    lbls = svc.list_labels()
    check("Service list_labels", len(lbls) >= 6, str(len(lbls)))

# ── Summary ────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"ML Foundation Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
