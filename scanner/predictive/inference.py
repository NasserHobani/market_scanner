# -*- coding: utf-8 -*-
"""Inference engine — prediction interface."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .model_metadata import PREDICTIVE_VERSION
from .prediction import PredictionResult
from .trainer import ModelArtifact


class InferenceEngine:
    """Run predictions on feature vectors — analytical signal only."""

    def predict(self, artifact: ModelArtifact,
                feature_vector: dict[str, float | int] | list[float],
                *, feature_names: list[str] | None = None) -> PredictionResult:
        cols = feature_names or artifact.feature_columns
        if isinstance(feature_vector, dict):
            X = [[float(feature_vector.get(c, 0.0)) for c in cols]]
        else:
            X = [list(feature_vector)]

        model = artifact.model
        preds = model.predict(X, feature_names=cols)
        proba = model.predict_proba(X, feature_names=cols)

        prediction = float(preds[0])
        probability = float(proba[0]) if proba else None
        confidence = self._confidence(probability, prediction)

        return PredictionResult(
            prediction=prediction,
            probability=probability,
            confidence=confidence,
            model_id=artifact.model_id,
            model_version=artifact.metadata.model_version or PREDICTIVE_VERSION,
            feature_version=artifact.metadata.feature_version,
            plugin=artifact.metadata.plugin,
            explainability={
                "feature_columns": cols,
                "feature_values": dict(zip(cols, X[0])),
                "task_type": artifact.task_type,
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def predict_batch(self, artifact: ModelArtifact,
                      feature_vectors: list[dict[str, float | int]],
                      *, feature_names: list[str] | None = None) -> list[PredictionResult]:
        return [self.predict(artifact, fv, feature_names=feature_names)
                for fv in feature_vectors]

    @staticmethod
    def _confidence(probability: float | None, prediction: float) -> float | None:
        if probability is not None:
            return round(max(probability, 1 - probability), 4)
        if prediction in (0.0, 1.0):
            return 1.0
        return None
