# -*- coding: utf-8 -*-
"""Feature vector export — no ML library dependencies."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .feature_metadata import FeatureRegistry


VECTOR_COLUMNS = (
    "name", "value", "source", "calculation_module", "calculation_version",
)


@runtime_checkable
class FeatureVectorExport(Protocol):
  def to_dict(self) -> dict[str, Any]: ...
  def to_vector(self) -> list[float | None]: ...
  def to_dataframe(self) -> dict[str, Any]: ...


def registry_to_dict(registry: FeatureRegistry,
                     groups: dict[str, Any] | None = None,
                     raw_components: dict[str, int] | None = None,
                     meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "features": registry.to_dict(),
        "groups": groups or {},
        "raw_components": raw_components or {},
        "meta": meta or {},
    }


def registry_to_vector(registry: FeatureRegistry, *,
                       column_order: list[str] | None = None) -> list[float | None]:
    """Flat numeric vector in stable column order."""
    numeric = registry.numeric_values()
    keys = column_order or sorted(numeric.keys())
    return [numeric.get(k) for k in keys]


def registry_to_dataframe(registry: FeatureRegistry) -> dict[str, Any]:
    """Tabular export without pandas — ``columns`` + ``rows``."""
    rows = []
    for fv in registry.entries.values():
        rows.append([fv.name, fv.value, fv.source,
                     fv.calculation_module, fv.calculation_version])
    return {"columns": list(VECTOR_COLUMNS), "rows": rows}


def components_to_vector(components: dict[str, int],
                         order: list[str] | None = None) -> list[int]:
    keys = order or sorted(components.keys())
    return [int(components.get(k, 0)) for k in keys]
