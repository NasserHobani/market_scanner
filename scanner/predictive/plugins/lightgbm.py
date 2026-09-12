# -*- coding: utf-8 -*-
"""LightGBM predictive model plugin — first implementation."""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

from .base import PluginMetadata, PredictiveModel, TrainResult

DEFAULT_HYPERPARAMS = {
    "n_estimators": 100,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "random_state": 42,
}


class LightGBMPlugin(PredictiveModel):
    """LightGBM classifier/regressor with sklearn fallback."""

    PLUGIN_NAME = "lightgbm"

    def __init__(self, model: Any = None, *,
                 feature_names: list[str] | None = None,
                 task_type: str = "classification",
                 hyperparameters: dict[str, Any] | None = None) -> None:
        self._model = model
        self._feature_names = feature_names or []
        self._task_type = task_type
        self._hyperparameters = hyperparameters or dict(DEFAULT_HYPERPARAMS)

    @property
    def plugin_name(self) -> str:
        return self.PLUGIN_NAME

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self.PLUGIN_NAME,
            version="1.0.0",
            task_types=["classification", "regression"],
            description="LightGBM with sklearn RandomForest fallback",
        )

    def train(self, X: list[list[float]], y: list[float | int], *,
              feature_names: list[str] | None = None,
              hyperparameters: dict[str, Any] | None = None,
              task_type: str = "classification") -> TrainResult:
        self._feature_names = feature_names or []
        self._task_type = task_type
        self._hyperparameters = {**DEFAULT_HYPERPARAMS, **(hyperparameters or {})}
        notes: list[str] = []

        if len(X) < 10:
            return TrainResult(success=False, notes=["Insufficient training samples (n<10)"])

        model, backend = self._create_model(task_type, self._hyperparameters)
        notes.append(f"Backend: {backend}")

        try:
            model.fit(X, y)
            self._model = model
            preds = model.predict(X)
            if task_type == "classification" and hasattr(model, "predict_proba"):
                proba = model.predict_proba(X)
                train_acc = sum(1 for p, t in zip(preds, y) if p == t) / len(y)
                train_metrics = {"train_accuracy": round(train_acc, 4), "backend": backend}
            else:
                errors = [abs(float(p) - float(t)) for p, t in zip(preds, y)]
                train_metrics = {
                    "train_mae": round(sum(errors) / len(errors), 4),
                    "backend": backend,
                }
            return TrainResult(success=True, model=model, train_metrics=train_metrics, notes=notes)
        except Exception as exc:
            return TrainResult(success=False, notes=[f"Training failed: {exc}"])

    def predict(self, X: list[list[float]], *,
                feature_names: list[str] | None = None) -> list[float]:
        if self._model is None:
            raise RuntimeError("Model not trained or loaded")
        return [float(v) for v in self._model.predict(X)]

    def predict_proba(self, X: list[list[float]], *,
                      feature_names: list[str] | None = None) -> list[float] | None:
        if self._model is None:
            raise RuntimeError("Model not trained or loaded")
        if self._task_type != "classification":
            return None
        if hasattr(self._model, "predict_proba"):
            proba = self._model.predict_proba(X)
            return [float(p[1]) if len(p) > 1 else float(p[0]) for p in proba]
        preds = self.predict(X)
        return [float(p) for p in preds]

    def evaluate(self, X: list[list[float]], y: list[float | int], *,
                 feature_names: list[str] | None = None,
                 task_type: str = "classification") -> dict[str, Any]:
        preds = self.predict(X)
        proba = self.predict_proba(X, feature_names=feature_names)
        from scanner.predictive.evaluator import Evaluator
        return Evaluator().evaluate(
            y_true=[float(v) for v in y],
            y_pred=preds,
            y_proba=proba,
            task_type=task_type,
        )

    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plugin": self.PLUGIN_NAME,
            "task_type": self._task_type,
            "feature_names": self._feature_names,
            "hyperparameters": self._hyperparameters,
            "model": self._model,
        }
        with p.open("wb") as fh:
            pickle.dump(payload, fh)
        meta_path = p.with_suffix(".meta.json")
        meta_path.write_text(json.dumps({
            "plugin": self.PLUGIN_NAME,
            "task_type": self._task_type,
            "feature_names": self._feature_names,
            "hyperparameters": self._hyperparameters,
        }, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> LightGBMPlugin:
        with Path(path).open("rb") as fh:
            payload = pickle.load(fh)
        inst = cls(
            model=payload["model"],
            feature_names=payload.get("feature_names", []),
            task_type=payload.get("task_type", "classification"),
            hyperparameters=payload.get("hyperparameters", {}),
        )
        return inst

    @staticmethod
    def _create_model(task_type: str, params: dict[str, Any]) -> tuple[Any, str]:
        try:
            if task_type == "regression":
                from lightgbm import LGBMRegressor
                return LGBMRegressor(**params), "lightgbm"
            from lightgbm import LGBMClassifier
            return LGBMClassifier(**params), "lightgbm"
        except ImportError:
            pass
        try:
            from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
            rf_params = {
                "n_estimators": params.get("n_estimators", 100),
                "random_state": params.get("random_state", 42),
                "min_samples_leaf": 5,
            }
            if task_type == "regression":
                return RandomForestRegressor(**rf_params), "sklearn_rf"
            return RandomForestClassifier(**rf_params), "sklearn_rf"
        except ImportError:
            pass
        if task_type == "regression":
            return _SimpleFallbackRegressor(), "simple_fallback"
        return _SimpleFallbackClassifier(), "simple_fallback"


class _SimpleFallbackClassifier:
    """Deterministic pure-Python classifier when LightGBM/sklearn unavailable."""

    def __init__(self) -> None:
        self._pos_mean: list[float] = []
        self._neg_mean: list[float] = []
        self._threshold: float = 0.5

    def fit(self, X: list[list[float]], y: list) -> _SimpleFallbackClassifier:
        pos = [row for row, yi in zip(X, y) if int(yi) == 1]
        neg = [row for row, yi in zip(X, y) if int(yi) == 0]
        n_feat = len(X[0]) if X else 0
        self._pos_mean = (
            [sum(r[i] for r in pos) / len(pos) for i in range(n_feat)] if pos
            else [0.0] * n_feat
        )
        self._neg_mean = (
            [sum(r[i] for r in neg) / len(neg) for i in range(n_feat)] if neg
            else [0.0] * n_feat
        )
        return self

    def predict(self, X: list[list[float]]) -> list[int]:
        proba = self.predict_proba(X)
        return [1 if p[1] >= self._threshold else 0 for p in proba]

    def predict_proba(self, X: list[list[float]]) -> list[list[float]]:
        out: list[list[float]] = []
        for row in X:
            d_pos = sum((a - b) ** 2 for a, b in zip(row, self._pos_mean)) ** 0.5
            d_neg = sum((a - b) ** 2 for a, b in zip(row, self._neg_mean)) ** 0.5
            total = d_pos + d_neg + 1e-9
            p1 = d_neg / total
            out.append([1 - p1, p1])
        return out


class _SimpleFallbackRegressor:
    """Deterministic pure-Python regressor when LightGBM/sklearn unavailable."""

    def __init__(self) -> None:
        self._mean_target: float = 0.0
        self._weights: list[float] = []

    def fit(self, X: list[list[float]], y: list) -> _SimpleFallbackRegressor:
        self._mean_target = sum(float(v) for v in y) / len(y) if y else 0.0
        n_feat = len(X[0]) if X else 0
        self._weights = [0.0] * n_feat
        if X and y:
            for j in range(n_feat):
                num = sum(float(yi) * X[i][j] for i, yi in enumerate(y))
                den = sum(X[i][j] ** 2 for i in range(len(X))) + 1e-9
                self._weights[j] = num / den
        return self

    def predict(self, X: list[list[float]]) -> list[float]:
        return [sum(w * x for w, x in zip(self._weights, row)) for row in X]

    def predict_proba(self, X: list[list[float]]) -> None:
        return None
