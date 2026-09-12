# -*- coding: utf-8 -*-
"""Deterministic preprocessing — no fitting, no learned normalization."""
from __future__ import annotations

from typing import Any

from .feature_registry import FeatureDataType, MLFeatureRegistry
from .feature_store import MLDataset, MLDatasetRow


# Fixed encoding maps — deterministic, never learned from data
_GRADE_MAP = {"—": 0, "C": 1, "B": 2, "A": 3, "": 0}
_MARKET_MAP = {"crypto": 0, "forex": 1, "stocks": 2, "commodities": 3, "unknown": -1}
_TIMEFRAME_ORDER = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")


class PreprocessingPipeline:
    """Apply deterministic transformations to ML datasets.

    Rules:
    - No fitting on data
    - No learned normalization
    - Fixed fill values for missing numerics
    - Fixed categorical encodings
    """

    def __init__(self, registry: MLFeatureRegistry | None = None,
                 missing_numeric_fill: float = 0.0,
                 missing_categorical_fill: int = -1) -> None:
        self._registry = registry or MLFeatureRegistry()
        self._missing_numeric = missing_numeric_fill
        self._missing_categorical = missing_categorical_fill

    def transform(self, dataset: MLDataset) -> MLDataset:
        transformed = [
            self._transform_row(row) for row in dataset.rows
        ]
        return MLDataset(
            dataset_id=dataset.dataset_id,
            rows=transformed,
            column_order=list(dataset.column_order),
            label_columns=list(dataset.label_columns),
            filters_applied=dataset.filters_applied + ["preprocessing:deterministic"],
        )

    def _transform_row(self, row: MLDatasetRow) -> MLDatasetRow:
        features: dict[str, Any] = {}
        missing: list[str] = []

        for name, val in row.features.items():
            feat_def = self._registry.get(name)
            dtype = feat_def.data_type if feat_def else FeatureDataType.NUMERIC.value

            if val is None:
                missing.append(name)
                features[name] = self._fill(dtype, name)
            elif dtype == FeatureDataType.CATEGORICAL.value:
                features[name] = self._encode_categorical(name, val)
            elif dtype == FeatureDataType.BOOLEAN.value:
                features[name] = 1 if val else 0
            elif dtype in (FeatureDataType.NUMERIC.value, FeatureDataType.INTEGER.value):
                features[name] = self._clip_numeric(name, float(val))
            else:
                features[name] = val

        return MLDatasetRow(
            event_id=row.event_id,
            snapshot_id=row.snapshot_id,
            features=features,
            labels=dict(row.labels),
            meta=dict(row.meta),
            missing_features=missing,
        )

    def _fill(self, dtype: str, name: str) -> Any:
        if dtype == FeatureDataType.CATEGORICAL.value:
            return self._missing_categorical
        if dtype == FeatureDataType.BOOLEAN.value:
            return 0
        return self._missing_numeric

    def _encode_categorical(self, name: str, val: Any) -> int:
        s = str(val)
        if name == "final_grade" or name == "grade":
            return _GRADE_MAP.get(s, self._missing_categorical)
        if name == "market":
            return _MARKET_MAP.get(s.lower(), self._missing_categorical)
        if name == "timeframe":
            try:
                return _TIMEFRAME_ORDER.index(s.lower())
            except ValueError:
                return self._missing_categorical
        return hash(s) % 1000  # deterministic fallback

    @staticmethod
    def _clip_numeric(name: str, val: float) -> float:
        if name == "rsi":
            return max(0.0, min(100.0, val))
        if name in ("htf_bias",) or name.startswith("c_"):
            return max(-1.0, min(1.0, val))
        return val
