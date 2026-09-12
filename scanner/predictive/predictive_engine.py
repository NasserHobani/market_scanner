# -*- coding: utf-8 -*-
"""Walk-forward validation and predictive engine orchestrator."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .evaluator import Evaluator
from .inference import InferenceEngine
from .model_loader import ModelLoader
from .model_registry import ModelRegistry
from .model_store import ModelStore
from .plugins.lightgbm import LightGBMPlugin
from .prediction import PredictionResult
from .trainer import ModelArtifact, Trainer, TrainingConfig


class ValidationMode(str, Enum):
    ROLLING = "rolling"
    EXPANDING = "expanding"
    WALK_FORWARD = "walk_forward"


@dataclass
class FoldResult:
    fold_index: int
    train_size: int
    test_size: int
    evaluation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "train_size": self.train_size,
            "test_size": self.test_size,
            "evaluation": dict(self.evaluation),
        }


@dataclass
class WalkForwardResult:
    mode: str
    folds: list[FoldResult] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "folds": [f.to_dict() for f in self.folds],
            "aggregate": dict(self.aggregate),
        }


class WalkForwardValidator:
    """Time-aware validation — no random shuffle."""

    def __init__(self, evaluator: Evaluator | None = None) -> None:
        self._evaluator = evaluator or Evaluator()

    def validate(self, rows: list[dict[str, Any]], config: TrainingConfig, *,
                 mode: str = ValidationMode.WALK_FORWARD.value,
                 train_size: int = 20,
                 test_size: int = 5,
                 step: int = 5,
                 plugin_factory: Callable | None = None) -> WalkForwardResult:
        if mode == ValidationMode.ROLLING.value:
            splits = self._rolling_splits(len(rows), train_size, test_size, step)
        elif mode == ValidationMode.EXPANDING.value:
            splits = self._expanding_splits(len(rows), train_size, test_size, step)
        else:
            splits = self._walk_forward_splits(len(rows), train_size, test_size, step)

        folds: list[FoldResult] = []
        factory = plugin_factory or LightGBMPlugin

        for i, (train_idx, test_idx) in enumerate(splits):
            train_rows = [rows[j] for j in train_idx]
            test_rows = [rows[j] for j in test_idx]
            if len(train_rows) < 5 or len(test_rows) < 1:
                continue

            trainer = Trainer(plugins={config.plugin_name: factory})
            try:
                artifact = trainer.train(train_rows, config)
            except RuntimeError:
                continue

            X_test, y_test, r_mults = Trainer._extract(test_rows, config)
            if not X_test:
                continue

            preds = artifact.model.predict(X_test, feature_names=config.feature_columns)
            proba = artifact.model.predict_proba(X_test, feature_names=config.feature_columns)

            evaluation = self._evaluator.evaluate(
                y_true=[float(v) for v in y_test],
                y_pred=preds,
                y_proba=proba,
                r_multiples=r_mults,
                task_type=config.task_type,
            )
            folds.append(FoldResult(
                fold_index=i,
                train_size=len(train_rows),
                test_size=len(test_rows),
                evaluation=evaluation,
            ))

        aggregate = self._aggregate(folds)
        return WalkForwardResult(mode=mode, folds=folds, aggregate=aggregate)

    @staticmethod
    def _rolling_splits(n: int, train_size: int, test_size: int,
                        step: int) -> list[tuple[list[int], list[int]]]:
        splits: list[tuple[list[int], list[int]]] = []
        start = 0
        while start + train_size + test_size <= n:
            train_idx = list(range(start, start + train_size))
            test_idx = list(range(start + train_size, start + train_size + test_size))
            splits.append((train_idx, test_idx))
            start += step
        return splits

    @staticmethod
    def _expanding_splits(n: int, min_train: int, test_size: int,
                          step: int) -> list[tuple[list[int], list[int]]]:
        splits: list[tuple[list[int], list[int]]] = []
        train_end = min_train
        while train_end + test_size <= n:
            train_idx = list(range(0, train_end))
            test_idx = list(range(train_end, train_end + test_size))
            splits.append((train_idx, test_idx))
            train_end += step
        return splits

    @staticmethod
    def _walk_forward_splits(n: int, train_size: int, test_size: int,
                             step: int) -> list[tuple[list[int], list[int]]]:
        """Walk-forward: train on [0..t], test on [t+1..t+test_size], advance by step."""
        splits: list[tuple[list[int], list[int]]] = []
        t = train_size
        while t + test_size <= n:
            train_idx = list(range(0, t))
            test_idx = list(range(t, t + test_size))
            splits.append((train_idx, test_idx))
            t += step
        return splits

    @staticmethod
    def _aggregate(folds: list[FoldResult]) -> dict[str, Any]:
        if not folds:
            return {"fold_count": 0}
        accs = [f.evaluation.get("classification", {}).get("accuracy")
                for f in folds if f.evaluation.get("classification")]
        accs = [a for a in accs if a is not None]
        exp_vals = [f.evaluation.get("trading", {}).get("expectancy")
                    for f in folds if f.evaluation.get("trading")]
        exp_vals = [e for e in exp_vals if e is not None]
        return {
            "fold_count": len(folds),
            "mean_accuracy": round(sum(accs) / len(accs), 4) if accs else None,
            "mean_expectancy": round(sum(exp_vals) / len(exp_vals), 4) if exp_vals else None,
        }


class PredictiveEngine:
    """Central orchestrator for predictive modeling."""

    def __init__(self,
                 trainer: Trainer | None = None,
                 evaluator: Evaluator | None = None,
                 store: ModelStore | None = None,
                 registry: ModelRegistry | None = None,
                 inference: InferenceEngine | None = None,
                 walk_forward: WalkForwardValidator | None = None) -> None:
        self._trainer = trainer or Trainer(plugins={"lightgbm": LightGBMPlugin})
        self._evaluator = evaluator or Evaluator()
        self._store = store or ModelStore()
        self._registry = registry or ModelRegistry()
        self._inference = inference or InferenceEngine()
        self._walk_forward = walk_forward or WalkForwardValidator(self._evaluator)
        self._loader = ModelLoader(self._store)

    def train(self, rows: list[dict[str, Any]], config: TrainingConfig, *,
              run_walk_forward: bool = False,
              walk_forward_mode: str = ValidationMode.WALK_FORWARD.value,
              walk_forward_train_size: int = 20,
              walk_forward_test_size: int = 5) -> ModelArtifact:
        artifact = self._trainer.train(rows, config)

        if run_walk_forward and len(rows) >= walk_forward_train_size + walk_forward_test_size:
            wf = self._walk_forward.validate(
                rows, config,
                mode=walk_forward_mode,
                train_size=walk_forward_train_size,
                test_size=walk_forward_test_size,
            )
            artifact.metadata.walk_forward_summary = wf.to_dict()

        self._store.save(artifact)
        self._registry.register(artifact.metadata)
        return artifact

    def evaluate(self, model_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        artifact = self._loader.load(model_id)
        config = TrainingConfig(
            feature_columns=artifact.feature_columns,
            label_column=artifact.label_column,
            task_type=artifact.task_type,
            plugin_name=artifact.metadata.plugin,
        )
        X, y, r_mults = Trainer._extract(rows, config)
        preds = artifact.model.predict(X, feature_names=artifact.feature_columns)
        proba = artifact.model.predict_proba(X, feature_names=artifact.feature_columns)

        evaluation = self._evaluator.evaluate(
            y_true=[float(v) for v in y],
            y_pred=preds,
            y_proba=proba,
            r_multiples=r_mults,
            task_type=artifact.task_type,
        )
        artifact.metadata.evaluation_summary = evaluation
        self._registry.update_evaluation(model_id, evaluation)
        return evaluation

    def predict(self, model_id: str,
                feature_vector: dict[str, float | int]) -> PredictionResult:
        artifact = self._loader.load(model_id)
        return self._inference.predict(artifact, feature_vector)

    def list_models(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self._store.list_models()]

    def load_model(self, model_id: str) -> ModelArtifact:
        return self._loader.load(model_id)

    def registry(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self._registry.list_all(limit=limit)]

    def walk_forward(self, rows: list[dict[str, Any]], config: TrainingConfig,
                     **kwargs: Any) -> WalkForwardResult:
        return self._walk_forward.validate(rows, config, **kwargs)
