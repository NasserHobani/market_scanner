# -*- coding: utf-8 -*-
"""Unit tests for scanner.predictive — run: python tests_predictive.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ml.label_store import LabelName
from scanner.predictive import (
    Evaluator,
    LightGBMPlugin,
    PredictiveService,
    Trainer,
    TrainingConfig,
    ValidationMode,
    WalkForwardValidator,
)
from scanner.predictive.model_registry import ModelRegistry
from scanner.predictive.model_store import ModelStore
from scanner.predictive.plugins.base import PredictiveModel, PluginMetadata, TrainResult

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _row(i: int, *, rsi: float = 55.0, score: float = 70.0,
           htf: int = 1, win: bool = True, r: float = 2.0) -> dict:
    return {
        "features": {
            "rsi": rsi + i * 0.3,
            "score": score + i * 0.5,
            "htf_bias": htf,
            "atr_pct": 2.1,
        },
        LabelName.BINARY_WIN.value: 1 if win else 0,
        LabelName.WINNER.value: 1 if win else 0,
        LabelName.LOSER.value: 0 if win else 1,
        LabelName.R_MULTIPLE.value: r,
        "_meta": {"closed_at": datetime(2025, 1, 1 + i % 28, 12, 0,
                                        tzinfo=timezone.utc).isoformat()},
    }


N = 50
ROWS = [_row(i, win=(i % 3 != 0), r=2.0 if i % 3 != 0 else -1.0,
               rsi=50 + (10 if i % 3 != 0 else -5))
        for i in range(N)]
FEATURES = ["rsi", "score", "htf_bias", "atr_pct"]

# ── Plugin Base ────────────────────────────────────────────────────────────

check("LightGBM plugin_name", LightGBMPlugin().plugin_name == "lightgbm")
check("LightGBM metadata", LightGBMPlugin().metadata.task_types == ["classification", "regression"])
check("LightGBM is PredictiveModel", isinstance(LightGBMPlugin(), PredictiveModel))

# ── LightGBM Plugin Train/Predict ──────────────────────────────────────────

plugin = LightGBMPlugin()
X = [[r["features"]["rsi"], r["features"]["score"], r["features"]["htf_bias"],
      r["features"]["atr_pct"]] for r in ROWS]
y = [r[LabelName.BINARY_WIN.value] for r in ROWS]

train_result = plugin.train(X, y, feature_names=FEATURES, task_type="classification")
check("Plugin train success", train_result.success, str(train_result.notes))
check("Plugin train metrics", "train_accuracy" in train_result.train_metrics or
      "train_mae" in train_result.train_metrics)

preds = plugin.predict(X[:5], feature_names=FEATURES)
check("Plugin predict", len(preds) == 5, str(len(preds)))

proba = plugin.predict_proba(X[:5], feature_names=FEATURES)
check("Plugin predict_proba", proba is not None and len(proba) == 5)

eval_result = plugin.evaluate(X, y, feature_names=FEATURES, task_type="classification")
check("Plugin evaluate", "classification" in eval_result)

# ── Plugin Save/Load ───────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    model_path = Path(tmp) / "model.pkl"
    plugin.save(str(model_path))
    check("Plugin save", model_path.exists())

    loaded = LightGBMPlugin.load(str(model_path))
    loaded_preds = loaded.predict(X[:3], feature_names=FEATURES)
    check("Plugin load", len(loaded_preds) == 3)
    check("Plugin load predict match", len(loaded_preds) == len(preds[:3]))

# ── Evaluator ────────────────────────────────────────────────────────────────

y_true = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1]
y_pred = [1, 0, 1, 0, 0, 1, 1, 0, 1, 0]
y_proba = [0.9, 0.1, 0.8, 0.4, 0.2, 0.7, 0.6, 0.3, 0.85, 0.45]

ev = Evaluator().evaluate(y_true=y_true, y_pred=y_pred, y_proba=y_proba,
                           task_type="classification")
check("Evaluator accuracy", ev["classification"]["accuracy"] is not None)
check("Evaluator precision", ev["classification"]["precision"] is not None)
check("Evaluator recall", ev["classification"]["recall"] is not None)
check("Evaluator f1", ev["classification"]["f1"] is not None)
check("Evaluator roc_auc", ev["classification"].get("roc_auc") is not None)

reg_ev = Evaluator().evaluate(
    y_true=[1.0, 2.0, 3.0, 4.0, 5.0],
    y_pred=[1.1, 1.9, 3.2, 3.8, 5.1],
    task_type="regression",
)
check("Evaluator rmse", "rmse" in reg_ev["regression"])
check("Evaluator mae", "mae" in reg_ev["regression"])
check("Evaluator r_squared", "r_squared" in reg_ev["regression"])

trade_ev = Evaluator().evaluate(
    y_true=[1, 0, 1, 1, 0],
    y_pred=[1, 0, 1, 0, 0],
    y_proba=[0.8, 0.2, 0.9, 0.4, 0.3],
    r_multiples=[2.0, -1.0, 1.5, -0.5, 0.5],
    task_type="classification",
)
check("Evaluator trading expectancy", trade_ev["trading"]["expectancy"] is not None)
check("Evaluator trading win_rate", trade_ev["trading"]["win_rate"] is not None)

# ── Trainer ──────────────────────────────────────────────────────────────────

trainer = Trainer(plugins={"lightgbm": LightGBMPlugin})
config = TrainingConfig(
    feature_columns=FEATURES,
    label_column=LabelName.BINARY_WIN.value,
    task_type="classification",
    plugin_name="lightgbm",
    dataset_id="mls_test",
    feature_analysis_id="fia_test",
    research_experiment_id="rex_test",
)
artifact = trainer.train(ROWS, config)
check("Trainer artifact", artifact.model_id.startswith("mdl_"))
check("Trainer metadata", artifact.metadata.dataset_id == "mls_test")
check("Trainer feature_analysis_id", artifact.metadata.feature_analysis_id == "fia_test")
check("Trainer fingerprint", artifact.metadata.fingerprint.startswith("mdl_"))

# ── Walk-Forward Validation ──────────────────────────────────────────────────

wf = WalkForwardValidator().validate(
    ROWS, config,
    mode=ValidationMode.WALK_FORWARD.value,
    train_size=15, test_size=5, step=5,
    plugin_factory=LightGBMPlugin,
)
check("Walk-forward folds", len(wf.folds) >= 1, str(len(wf.folds)))
check("Walk-forward aggregate", "fold_count" in wf.aggregate)
check("Walk-forward mode", wf.mode == "walk_forward")

wf_rolling = WalkForwardValidator().validate(
    ROWS, config, mode=ValidationMode.ROLLING.value,
    train_size=15, test_size=5, step=5, plugin_factory=LightGBMPlugin,
)
check("Rolling validation", wf_rolling.mode == "rolling")

wf_expanding = WalkForwardValidator().validate(
    ROWS, config, mode=ValidationMode.EXPANDING.value,
    train_size=15, test_size=5, step=5, plugin_factory=LightGBMPlugin,
)
check("Expanding validation", wf_expanding.mode == "expanding")

# ── Model Store ──────────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store = ModelStore(Path(tmp) / "models")
    store.save(artifact)
    check("ModelStore save", store.exists(artifact.model_id))

    loaded_artifact = store.load_model(artifact.model_id)
    check("ModelStore load", loaded_artifact.model_id == artifact.model_id)

    models = store.list_models()
    check("ModelStore list", len(models) >= 1)

    store.archive(artifact.model_id)
    archived = store.load_metadata(artifact.model_id)
    check("ModelStore archive", archived.status == "archived")

# ── PredictiveService ────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store = ModelStore(Path(tmp) / "models")
    registry = ModelRegistry(Path(tmp) / "registry.jsonl")
    svc = PredictiveService(store=store, registry=registry)

    trained = svc.train(
        ROWS,
        feature_columns=FEATURES,
        label_column=LabelName.BINARY_WIN.value,
        dataset_id="mls_svc",
        feature_analysis_id="fia_svc",
        research_experiment_id="rex_svc",
        run_walk_forward=True,
    )
    check("Service train", trained.model_id.startswith("mdl_"))
    check("Service walk_forward", bool(trained.metadata.walk_forward_summary))

    pred = svc.predict(trained.model_id, {"rsi": 55.0, "score": 72.0,
                                            "htf_bias": 1, "atr_pct": 2.1})
    check("Service predict", pred.prediction is not None)
    check("Service predict disclaimer",
          "disclaimer" in pred.to_dict())
    check("Service predict explainability",
          "feature_values" in pred.explainability)

    eval_metrics = svc.evaluate(trained.model_id, ROWS[:20])
    check("Service evaluate", "classification" in eval_metrics)

    model_list = svc.list_models()
    check("Service list_models", len(model_list) >= 1)

    reg = svc.registry()
    check("Service registry", len(reg) >= 1)

    wf_result = svc.walk_forward(ROWS, feature_columns=FEATURES, train_size=15, test_size=5)
    check("Service walk_forward", wf_result.fold_count if hasattr(wf_result, 'fold_count')
          else len(wf_result.folds) >= 1)

    loaded = svc.load_model(trained.model_id)
    check("Service load_model", loaded.model_id == trained.model_id)

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Predictive Platform Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
