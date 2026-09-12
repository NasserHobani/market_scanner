# -*- coding: utf-8 -*-
"""Public ML foundation service API."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .dataset_export import DatasetExporter, ExportFormat, ExportResult
from .dataset_registry import DatasetRegistry, RegisteredDataset, new_dataset_id
from .feature_registry import FeatureDefinition, MLFeatureRegistry
from .feature_store import FeatureStore, MLDataset
from .label_store import LabelDefinition, LabelStore
from .metadata import FEATURE_VERSION, LABEL_VERSION, SCHEMA_VERSION
from .preprocessing import PreprocessingPipeline
from .validation import DatasetValidator, ValidationResult


class MLFoundationService:
    """Public facade for ML data preparation infrastructure.

    No model training. No predictions. Infrastructure only.
    """

    def __init__(self,
                 feature_registry: MLFeatureRegistry | None = None,
                 label_store: LabelStore | None = None,
                 feature_store: FeatureStore | None = None,
                 validator: DatasetValidator | None = None,
                 exporter: DatasetExporter | None = None,
                 registry: DatasetRegistry | None = None,
                 preprocessor: PreprocessingPipeline | None = None) -> None:
        self._features = feature_registry or MLFeatureRegistry()
        self._labels = label_store or LabelStore()
        self._store = feature_store or FeatureStore(
            label_store=self._labels,
        )
        self._validator = validator or DatasetValidator(
            feature_registry=self._features,
            label_store=self._labels,
        )
        self._exporter = exporter or DatasetExporter()
        self._registry = registry or DatasetRegistry()
        self._preprocessor = preprocessor or PreprocessingPipeline(
            registry=self._features,
        )

    def build_dataset(self, *,
                      feature_snapshots: list[dict[str, Any]],
                      trade_rows: list[dict[str, Any]],
                      outcome_rows: list[dict[str, Any]] | None = None,
                      dataset_id: str | None = None,
                      research_experiment_id: str = "",
                      completed_only: bool = True,
                      apply_preprocessing: bool = True,
                      validate: bool = True,
                      join_key: str = "feature_snapshot_id") -> MLDataset:
        """Build a versioned ML dataset from provided snapshots and trades."""
        did = dataset_id or new_dataset_id()
        filters = ["source:provided"]
        if completed_only:
            filters.append("completed_only")

        dataset = self._store.build_dataset(
            dataset_id=did,
            feature_snapshots=feature_snapshots,
            trade_rows=trade_rows,
            outcome_rows=outcome_rows,
            filters_applied=filters,
            join_key=join_key,
            completed_only=completed_only,
        )

        if apply_preprocessing:
            dataset = self._preprocessor.transform(dataset)

        if validate:
            result = self._validator.validate(dataset)
            if not result.valid:
                raise ValueError(
                    f"Dataset validation failed: "
                    f"{result.to_dict()['error_count']} errors"
                )

        self._registry.register(
            dataset_id=did,
            row_count=dataset.row_count,
            feature_count=len(dataset.column_order),
            label_columns=dataset.label_columns,
            filters_applied=dataset.filters_applied,
            research_experiment_id=research_experiment_id,
            schema_version=SCHEMA_VERSION,
            feature_version=FEATURE_VERSION,
            label_version=LABEL_VERSION,
        )
        return dataset

    def export_dataset(self, dataset: MLDataset, path: Path | str, *,
                       fmt: ExportFormat = "csv",
                       include_meta_columns: bool = False) -> ExportResult:
        """Export dataset to CSV, JSON, or Parquet (interface)."""
        return self._exporter.export(
            dataset, path,
            fmt=fmt,
            include_meta_columns=include_meta_columns,
        )

    def validate_dataset(self, dataset: MLDataset, **kwargs: Any) -> ValidationResult:
        """Validate dataset without building."""
        return self._validator.validate(dataset, **kwargs)

    def list_features(self) -> list[FeatureDefinition]:
        return self._features.list_all()

    def list_labels(self) -> list[LabelDefinition]:
        return self._labels.list_all()

    def dataset_history(self, *, limit: int = 50) -> list[RegisteredDataset]:
        return self._registry.history(limit=limit)

    def load_registry_entry(self, dataset_id: str) -> RegisteredDataset:
        return self._registry.load(dataset_id)
