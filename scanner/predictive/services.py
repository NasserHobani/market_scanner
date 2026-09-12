# -*- coding: utf-8 -*-
"""Public predictive modeling service API."""
from __future__ import annotations

from typing import Any

from .model_registry import ModelRegistry
from .model_store import ModelStore
from .predictive_engine import PredictiveEngine, ValidationMode, WalkForwardResult
from .prediction import PredictionResult
from .trainer import ModelArtifact, TrainingConfig


class PredictiveService:
    """Public facade for predictive modeling.

    Prediction only — no trading recommendations, no trade execution.
    """

    def __init__(self, engine: PredictiveEngine | None = None,
                 store: ModelStore | None = None,
                 registry: ModelRegistry | None = None) -> None:
        self._store = store or ModelStore()
        self._registry = registry or ModelRegistry()
        self._engine = engine or PredictiveEngine(store=self._store, registry=self._registry)

    def train(self, rows: list[dict[str, Any]], *,
              feature_columns: list[str],
              label_column: str = "label_binary_win",
              task_type: str = "classification",
              plugin_name: str = "lightgbm",
              hyperparameters: dict[str, Any] | None = None,
              dataset_id: str = "",
              feature_analysis_id: str = "",
              research_experiment_id: str = "",
              run_walk_forward: bool = False,
              walk_forward_mode: str = ValidationMode.WALK_FORWARD.value) -> ModelArtifact:
        config = TrainingConfig(
            feature_columns=feature_columns,
            label_column=label_column,
            task_type=task_type,
            plugin_name=plugin_name,
            hyperparameters=hyperparameters or {},
            dataset_id=dataset_id,
            feature_analysis_id=feature_analysis_id,
            research_experiment_id=research_experiment_id,
        )
        return self._engine.train(
            rows, config,
            run_walk_forward=run_walk_forward,
            walk_forward_mode=walk_forward_mode,
        )

    def predict(self, model_id: str,
                feature_vector: dict[str, float | int]) -> PredictionResult:
        return self._engine.predict(model_id, feature_vector)

    def evaluate(self, model_id: str,
                 rows: list[dict[str, Any]]) -> dict[str, Any]:
        return self._engine.evaluate(model_id, rows)

    def list_models(self) -> list[dict[str, Any]]:
        return self._engine.list_models()

    def load_model(self, model_id: str) -> ModelArtifact:
        return self._engine.load_model(model_id)

    def registry(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._engine.registry(limit=limit)

    def walk_forward(self, rows: list[dict[str, Any]], *,
                     feature_columns: list[str],
                     label_column: str = "label_binary_win",
                     task_type: str = "classification",
                     plugin_name: str = "lightgbm",
                     mode: str = ValidationMode.WALK_FORWARD.value,
                     train_size: int = 20,
                     test_size: int = 5) -> WalkForwardResult:
        config = TrainingConfig(
            feature_columns=feature_columns,
            label_column=label_column,
            task_type=task_type,
            plugin_name=plugin_name,
        )
        return self._engine.walk_forward(
            rows, config, mode=mode,
            train_size=train_size, test_size=test_size,
        )

    def archive_model(self, model_id: str) -> None:
        self._store.archive(model_id)

    def delete_model(self, model_id: str) -> None:
        self._store.delete(model_id)
