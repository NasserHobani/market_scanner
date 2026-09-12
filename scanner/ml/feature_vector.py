# -*- coding: utf-8 -*-
"""Feature vector builder — deterministic, no ML libraries."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scanner.knowledge.feature_metadata import FeatureRegistry
from scanner.knowledge.feature_vector import components_to_vector, registry_to_vector

from .feature_registry import FeatureDataType, MLFeatureRegistry


@dataclass
class FeatureVector:
    """Single row feature vector with typed values and metadata."""

    event_id: str
    snapshot_id: str
    values: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    column_order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "snapshot_id": self.snapshot_id,
            "values": dict(self.values),
            "missing": list(self.missing),
            "column_order": list(self.column_order),
        }

    def to_flat_list(self) -> list[Any]:
        return [self.values.get(c) for c in self.column_order]


class FeatureVectorBuilder:
    """Convert knowledge snapshots into deterministic feature vectors."""

    def __init__(self, registry: MLFeatureRegistry | None = None) -> None:
        self._registry = registry or MLFeatureRegistry()

    def from_feature_snapshot(self, snapshot: dict[str, Any], *,
                              include_meta: bool = True,
                              include_components: bool = True) -> FeatureVector:
        """Build vector from a FeatureSnapshot dict."""
        event_id = snapshot.get("event_id") or ""
        snapshot_id = snapshot.get("snapshot_id") or ""

        reg_data = snapshot.get("feature_registry") or {}
        feature_reg = FeatureRegistry.from_dict(reg_data)
        numeric = feature_reg.numeric_values()

        values: dict[str, Any] = {}
        missing: list[str] = []

        for feat_def in self._registry.list_training():
            name = feat_def.name
            if name.startswith("c_") and not include_components:
                continue
            if name in ("market", "timeframe", "final_grade") and not include_meta:
                continue

            val = self._resolve_value(name, snapshot, numeric)
            if val is None:
                if feat_def.nullable:
                    missing.append(name)
                values[name] = None
            else:
                values[name] = self._coerce(val, feat_def.data_type)

        if include_meta:
            for meta_key in ("market", "timeframe", "final_grade"):
                if meta_key not in values:
                    val = snapshot.get(meta_key)
                    if meta_key == "final_grade":
                        val = val or snapshot.get("final_grade")
                    values[meta_key] = val
                    if val is None:
                        missing.append(meta_key)

        if include_components:
            components = snapshot.get("raw_components") or {}
            for comp_name, comp_val in components.items():
                key = f"c_{comp_name}" if not comp_name.startswith("c_") else comp_name
                values[key] = int(comp_val) if comp_val is not None else None

        score = snapshot.get("final_score")
        if score is not None:
            values["final_score"] = float(score)

        column_order = sorted(values.keys())
        return FeatureVector(
            event_id=event_id,
            snapshot_id=snapshot_id,
            values=values,
            missing=missing,
            column_order=column_order,
        )

    def from_registry(self, registry: FeatureRegistry, *,
                      event_id: str = "", snapshot_id: str = "",
                      column_order: list[str] | None = None) -> FeatureVector:
        """Build vector directly from a FeatureRegistry."""
        numeric = registry.numeric_values()
        order = column_order or sorted(numeric.keys())
        values = {k: numeric.get(k) for k in order}
        missing = [k for k, v in values.items() if v is None]
        return FeatureVector(
            event_id=event_id,
            snapshot_id=snapshot_id,
            values=values,
            missing=missing,
            column_order=order,
        )

    def to_numeric_vector(self, vector: FeatureVector) -> list[float | None]:
        """Flat numeric vector using knowledge registry_to_vector."""
        reg = FeatureRegistry()
        for name, val in vector.values.items():
            if isinstance(val, (int, float)):
                from scanner.knowledge.feature_metadata import FeatureValue
                reg.add(FeatureValue(name=name, value=val))
        return registry_to_vector(reg, column_order=vector.column_order)

    def component_vector(self, snapshot: dict[str, Any]) -> list[int]:
        components = snapshot.get("raw_components") or {}
        return components_to_vector(components)

    def _resolve_value(self, name: str, snapshot: dict[str, Any],
                       numeric: dict[str, float]) -> Any:
        if name in numeric:
            return numeric[name]
        if name == "final_score":
            return snapshot.get("final_score")
        if name in ("market", "timeframe", "final_grade"):
            return snapshot.get(name)
        if name.startswith("c_"):
            comp_key = name[2:]
            components = snapshot.get("raw_components") or {}
            return components.get(comp_key)
        return None

    @staticmethod
    def _coerce(val: Any, data_type: str) -> Any:
        if val is None:
            return None
        if data_type == FeatureDataType.NUMERIC.value:
            return float(val)
        if data_type == FeatureDataType.INTEGER.value:
            return int(val)
        if data_type == FeatureDataType.BOOLEAN.value:
            return bool(val)
        return str(val)
