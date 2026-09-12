# -*- coding: utf-8 -*-
"""Model metadata types."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


PREDICTIVE_VERSION = "1.0.0"


class ModelStatus(str, Enum):
    TRAINING = "training"
    TRAINED = "TRAINED"
    EVALUATED = "evaluated"
    NOT_PROMOTED = "NOT_PROMOTED"
    CANDIDATE_FOR_PROMOTION = "CANDIDATE_FOR_PROMOTION"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    ARCHIVED = "archived"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ModelMetadata:
    """Versioned model metadata."""

    model_id: str
    plugin: str
    dataset_id: str = ""
    feature_analysis_id: str = ""
    research_experiment_id: str = ""
    training_timestamp: str = ""
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    evaluation_summary: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    status: str = ModelStatus.TRAINED.value
    feature_columns: list[str] = field(default_factory=list)
    label_column: str = ""
    task_type: str = "classification"
    feature_version: str = "2.0.0"
    model_version: str = PREDICTIVE_VERSION
    feature_schema_hash: str = ""
    training_period: dict[str, str] = field(default_factory=dict)
    validation_period: dict[str, str] = field(default_factory=dict)
    test_period: dict[str, str] = field(default_factory=dict)
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    calibration_metrics: dict[str, Any] = field(default_factory=dict)
    quality_gate_result: dict[str, Any] = field(default_factory=dict)
    walk_forward_summary: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "plugin": self.plugin,
            "dataset_id": self.dataset_id,
            "feature_analysis_id": self.feature_analysis_id,
            "research_experiment_id": self.research_experiment_id,
            "training_timestamp": self.training_timestamp or _now(),
            "hyperparameters": dict(self.hyperparameters),
            "evaluation_summary": dict(self.evaluation_summary),
            "fingerprint": self.fingerprint,
            "status": self.status,
            "feature_columns": list(self.feature_columns),
            "label_column": self.label_column,
            "task_type": self.task_type,
            "feature_version": self.feature_version,
            "model_version": self.model_version,
            "feature_schema_hash": self.feature_schema_hash,
            "training_period": dict(self.training_period),
            "validation_period": dict(self.validation_period),
            "test_period": dict(self.test_period),
            "baseline_metrics": dict(self.baseline_metrics),
            "calibration_metrics": dict(self.calibration_metrics),
            "quality_gate_result": dict(self.quality_gate_result),
            "walk_forward_summary": dict(self.walk_forward_summary),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> ModelMetadata:
        return cls(
            model_id=row["model_id"],
            plugin=row.get("plugin") or "lightgbm",
            dataset_id=row.get("dataset_id") or "",
            feature_analysis_id=row.get("feature_analysis_id") or "",
            research_experiment_id=row.get("research_experiment_id") or "",
            training_timestamp=row.get("training_timestamp") or "",
            hyperparameters=dict(row.get("hyperparameters") or {}),
            evaluation_summary=dict(row.get("evaluation_summary") or {}),
            fingerprint=row.get("fingerprint") or "",
            status=row.get("status") or ModelStatus.TRAINED.value,
            feature_columns=list(row.get("feature_columns") or []),
            label_column=row.get("label_column") or "",
            task_type=row.get("task_type") or "classification",
            feature_version=row.get("feature_version") or "2.0.0",
            model_version=row.get("model_version") or PREDICTIVE_VERSION,
            feature_schema_hash=row.get("feature_schema_hash") or "",
            training_period=dict(row.get("training_period") or {}),
            validation_period=dict(row.get("validation_period") or {}),
            test_period=dict(row.get("test_period") or {}),
            baseline_metrics=dict(row.get("baseline_metrics") or {}),
            calibration_metrics=dict(row.get("calibration_metrics") or {}),
            quality_gate_result=dict(row.get("quality_gate_result") or {}),
            walk_forward_summary=dict(row.get("walk_forward_summary") or {}),
            extra=dict(row.get("extra") or {}),
        )


def compute_fingerprint(meta: dict[str, Any]) -> str:
    raw = json.dumps(meta, sort_keys=True, default=str).encode("utf-8")
    return f"mdl_{hashlib.sha256(raw).hexdigest()[:16]}"
