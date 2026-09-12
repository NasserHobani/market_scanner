# -*- coding: utf-8 -*-
"""ML feature schema registry — describes every available feature."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeatureDataType(str, Enum):
    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    CATEGORICAL = "categorical"
    INTEGER = "integer"


class FeatureCategory(str, Enum):
    MOMENTUM = "momentum"
    VOLUME = "volume"
    TREND = "trend"
    STRUCTURE = "structure"
    SCORING = "scoring"
    MARKET = "market"
    META = "meta"
    COMPONENT = "component"


@dataclass(frozen=True)
class FeatureDefinition:
    """Schema definition for a single ML feature."""

    name: str
    description: str
    data_type: str
    source_layer: str
    version: str = "1.0.0"
    nullable: bool = True
    category: str = FeatureCategory.META.value
    used_for_training: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "data_type": self.data_type,
            "source_layer": self.source_layer,
            "version": self.version,
            "nullable": self.nullable,
            "category": self.category,
            "used_for_training": self.used_for_training,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> FeatureDefinition:
        return cls(
            name=row["name"],
            description=row.get("description") or "",
            data_type=row.get("data_type") or FeatureDataType.NUMERIC.value,
            source_layer=row.get("source_layer") or "knowledge",
            version=row.get("version") or "1.0.0",
            nullable=bool(row.get("nullable", True)),
            category=row.get("category") or FeatureCategory.META.value,
            used_for_training=bool(row.get("used_for_training", True)),
        )


# Canonical feature definitions derived from knowledge layer
_BUILTIN_FEATURES: list[FeatureDefinition] = [
    FeatureDefinition("rsi", "Relative Strength Index", FeatureDataType.NUMERIC.value,
                      "knowledge.feature_registry", category=FeatureCategory.MOMENTUM.value),
    FeatureDefinition("rvol", "Relative volume", FeatureDataType.NUMERIC.value,
                      "knowledge.feature_registry", category=FeatureCategory.VOLUME.value),
    FeatureDefinition("atr_pct", "ATR as percentage of price", FeatureDataType.NUMERIC.value,
                      "knowledge.feature_registry", category=FeatureCategory.MARKET.value),
    FeatureDefinition("delta", "Volume delta", FeatureDataType.NUMERIC.value,
                      "knowledge.feature_registry", category=FeatureCategory.VOLUME.value),
    FeatureDefinition("score", "Composite score", FeatureDataType.NUMERIC.value,
                      "knowledge.feature_registry", category=FeatureCategory.SCORING.value),
    FeatureDefinition("htf_bias", "Higher timeframe bias", FeatureDataType.INTEGER.value,
                      "knowledge.feature_registry", category=FeatureCategory.TREND.value),
    FeatureDefinition("final_score", "Final feature snapshot score", FeatureDataType.NUMERIC.value,
                      "knowledge.feature_snapshot", category=FeatureCategory.SCORING.value),
    FeatureDefinition("market", "Market type", FeatureDataType.CATEGORICAL.value,
                      "knowledge.feature_snapshot", category=FeatureCategory.META.value),
    FeatureDefinition("timeframe", "Chart timeframe", FeatureDataType.CATEGORICAL.value,
                      "knowledge.feature_snapshot", category=FeatureCategory.META.value),
    FeatureDefinition("final_grade", "Final grade", FeatureDataType.CATEGORICAL.value,
                      "knowledge.feature_snapshot", category=FeatureCategory.SCORING.value),
]

_COMPONENT_NAMES = (
    "trend", "rsi", "obv_macd", "vwap", "spike", "obv", "cmf", "mfi", "ad", "delta", "fib", "div",
)
for _comp in _COMPONENT_NAMES:
    _BUILTIN_FEATURES.append(FeatureDefinition(
        f"c_{_comp}",
        f"Signed component signal for {_comp}",
        FeatureDataType.INTEGER.value,
        "knowledge.raw_components",
        category=FeatureCategory.COMPONENT.value,
        nullable=False,
    ))


class MLFeatureRegistry:
    """Registry of all features available for ML dataset building."""

    def __init__(self) -> None:
        self._features: dict[str, FeatureDefinition] = {
            f.name: f for f in _BUILTIN_FEATURES
        }

    def register(self, feature: FeatureDefinition) -> None:
        self._features[feature.name] = feature

    def get(self, name: str) -> FeatureDefinition | None:
        return self._features.get(name)

    def list_all(self) -> list[FeatureDefinition]:
        return sorted(self._features.values(), key=lambda f: f.name)

    def list_training(self) -> list[FeatureDefinition]:
        return [f for f in self.list_all() if f.used_for_training]

    def list_by_category(self, category: str) -> list[FeatureDefinition]:
        return [f for f in self.list_all() if f.category == category]

    def names(self) -> list[str]:
        return sorted(self._features.keys())

    def to_dict(self) -> dict[str, Any]:
        return {name: f.to_dict() for name, f in self._features.items()}

    def schema_version(self) -> str:
        versions = sorted({f.version for f in self._features.values()})
        return versions[-1] if versions else "1.0.0"
