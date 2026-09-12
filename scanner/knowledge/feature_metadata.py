# -*- coding: utf-8 -*-
"""Typed feature metadata for evolvable feature store."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeatureValue:
    """Single feature with full provenance metadata."""

    name: str
    value: Any
    source: str = "platform"
    calculation_module: str = ""
    calculation_version: str = "1.0"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "source": self.source,
            "calculation_module": self.calculation_module,
            "calculation_version": self.calculation_version,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> FeatureValue:
        return cls(
            name=str(row.get("name") or ""),
            value=row.get("value"),
            source=str(row.get("source") or "platform"),
            calculation_module=str(row.get("calculation_module") or ""),
            calculation_version=str(row.get("calculation_version") or "1.0"),
            notes=str(row.get("notes") or ""),
        )


@dataclass
class FeatureRegistry:
    """Named collection of FeatureValue entries."""

    entries: dict[str, FeatureValue] = field(default_factory=dict)

    def add(self, feature: FeatureValue) -> None:
        self.entries[feature.name] = feature

    def get(self, name: str) -> FeatureValue | None:
        return self.entries.get(name)

    def to_dict(self) -> dict[str, Any]:
        return {k: v.to_dict() for k, v in self.entries.items()}

    @classmethod
    def from_dict(cls, row: dict[str, Any] | None) -> FeatureRegistry:
        reg = cls()
        for key, val in (row or {}).items():
            if isinstance(val, dict):
                reg.entries[key] = FeatureValue.from_dict(val)
        return reg

    def numeric_values(self) -> dict[str, float]:
        """Return numeric features only — for vector export."""
        out: dict[str, float] = {}
        for name, fv in self.entries.items():
            if isinstance(fv.value, (int, float)) and fv.value is not None:
                out[name] = float(fv.value)
        return out
