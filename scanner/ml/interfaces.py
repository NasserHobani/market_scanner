# -*- coding: utf-8 -*-
"""ML foundation protocols."""
from __future__ import annotations

from typing import Any, Protocol

from .feature_store import MLDataset
from .validation import ValidationResult


class FeatureVectorBuilderProtocol(Protocol):
    def from_feature_snapshot(self, snapshot: dict[str, Any], **kwargs: Any) -> Any: ...


class LabelStoreProtocol(Protocol):
    def extract(self, trade_row: dict[str, Any], **kwargs: Any) -> dict[str, Any]: ...
    def list_all(self) -> list: ...


class DatasetBuilderProtocol(Protocol):
    def build_dataset(self, **kwargs: Any) -> MLDataset: ...


class DatasetValidatorProtocol(Protocol):
    def validate(self, dataset: MLDataset, **kwargs: Any) -> ValidationResult: ...


class DatasetExporterProtocol(Protocol):
    def export(self, dataset: MLDataset, path: Any, **kwargs: Any) -> Any: ...


class MLFoundationServiceProtocol(Protocol):
    def build_dataset(self, **kwargs: Any) -> MLDataset: ...
    def export_dataset(self, dataset: MLDataset, path: Any, **kwargs: Any) -> Any: ...
    def validate_dataset(self, dataset: MLDataset, **kwargs: Any) -> ValidationResult: ...
    def list_features(self) -> list: ...
    def list_labels(self) -> list: ...
