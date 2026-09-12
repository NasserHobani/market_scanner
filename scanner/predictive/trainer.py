# -*- coding: utf-8 -*-
"""Generic trainer — delegates to predictive model plugins."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from scanner.ml.label_store import LabelName

from .model_metadata import ModelMetadata, ModelStatus, compute_fingerprint
from .plugins.base import PredictiveModel


@dataclass
class TrainingConfig:
    """Training configuration."""

    feature_columns: list[str]
    label_column: str = LabelName.BINARY_WIN.value
    task_type: str = "classification"
    plugin_name: str = "lightgbm"
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    dataset_id: str = ""
    feature_analysis_id: str = ""
    research_experiment_id: str = ""
    feature_version: str = "1.0.0"


@dataclass
class ModelArtifact:
    """Trained model artifact."""

    model_id: str
    model: PredictiveModel
    metadata: ModelMetadata
    feature_columns: list[str]
    label_column: str
    task_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "metadata": self.metadata.to_dict(),
            "feature_columns": list(self.feature_columns),
            "label_column": self.label_column,
            "task_type": self.task_type,
        }


def new_model_id() -> str:
    return f"mdl_{uuid.uuid4().hex[:16]}"


class Trainer:
    """Generic trainer — receives dataset, features, labels, calls plugin."""

    def __init__(self, plugins: dict[str, type[PredictiveModel]] | None = None) -> None:
        self._plugins = plugins or {}

    def register_plugin(self, name: str, plugin_cls: type[PredictiveModel]) -> None:
        self._plugins[name] = plugin_cls

    def train(self, rows: list[dict[str, Any]], config: TrainingConfig) -> ModelArtifact:
        plugin_cls = self._plugins.get(config.plugin_name)
        if plugin_cls is None:
            raise ValueError(f"Unknown plugin: {config.plugin_name}")

        X, y, r_multiples = self._extract(rows, config)
        plugin = plugin_cls()

        result = plugin.train(
            X, y,
            feature_names=config.feature_columns,
            hyperparameters=config.hyperparameters,
            task_type=config.task_type,
        )
        if not result.success:
            raise RuntimeError(f"Training failed: {result.notes}")

        model_id = new_model_id()
        fp_data = {
            "model_id": model_id,
            "plugin": config.plugin_name,
            "dataset_id": config.dataset_id,
            "feature_columns": config.feature_columns,
            "label_column": config.label_column,
            "hyperparameters": config.hyperparameters,
        }
        metadata = ModelMetadata(
            model_id=model_id,
            plugin=config.plugin_name,
            dataset_id=config.dataset_id,
            feature_analysis_id=config.feature_analysis_id,
            research_experiment_id=config.research_experiment_id,
            training_timestamp=datetime.now(timezone.utc).isoformat(),
            hyperparameters=dict(config.hyperparameters),
            fingerprint=compute_fingerprint(fp_data),
            status=ModelStatus.TRAINED.value,
            feature_columns=list(config.feature_columns),
            label_column=config.label_column,
            task_type=config.task_type,
            feature_version=config.feature_version,
            extra={"train_metrics": result.train_metrics, "train_notes": result.notes},
        )

        return ModelArtifact(
            model_id=model_id,
            model=plugin,
            metadata=metadata,
            feature_columns=list(config.feature_columns),
            label_column=config.label_column,
            task_type=config.task_type,
        )

    @staticmethod
    def _extract(rows: list[dict], config: TrainingConfig
                 ) -> tuple[list[list[float]], list[float | int], list[float]]:
        X: list[list[float]] = []
        y: list[float | int] = []
        r_multiples: list[float] = []

        for row in rows:
            feats = row.get("features") or row
            vec = []
            skip = False
            for col in config.feature_columns:
                val = feats.get(col) if isinstance(feats, dict) else row.get(col)
                if val is None:
                    val = 0.0
                if not isinstance(val, (int, float)):
                    skip = True
                    break
                vec.append(float(val))
            if skip:
                continue

            label = row.get(config.label_column)
            if label is None:
                labels = row.get("labels") or {}
                label = labels.get(config.label_column)
            if label is None:
                continue

            X.append(vec)
            y.append(float(label) if config.task_type == "regression" else int(label))

            r = row.get(LabelName.R_MULTIPLE.value) or row.get("r_multiple")
            if r is None:
                labels = row.get("labels") or {}
                r = labels.get(LabelName.R_MULTIPLE.value)
            r_multiples.append(float(r) if r is not None else 0.0)

        return X, y, r_multiples
