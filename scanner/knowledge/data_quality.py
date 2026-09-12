# -*- coding: utf-8 -*-
"""Data quality assessment — never silently accept invalid snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .exceptions import SnapshotValidationError


@dataclass
class DataQualityReport:
    """Quality signals attached to every snapshot."""

    completeness_score: float = 1.0
    missing_features: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    unknown_values: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "completeness_score": round(self.completeness_score, 4),
            "missing_features": list(self.missing_features),
            "warnings": list(self.warnings),
            "validation_errors": list(self.validation_errors),
            "unknown_values": list(self.unknown_values),
            "is_valid": self.is_valid,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any] | None) -> DataQualityReport:
        if not row:
            return cls()
        return cls(
            completeness_score=float(row.get("completeness_score", 1.0)),
            missing_features=list(row.get("missing_features") or []),
            warnings=list(row.get("warnings") or []),
            validation_errors=list(row.get("validation_errors") or []),
            unknown_values=list(row.get("unknown_values") or []),
        )


def assess_completeness(payload: dict[str, Any], *,
                        required: list[str],
                        optional: list[str] | None = None) -> DataQualityReport:
    """Score completeness from required and optional field presence."""
    optional = optional or []
    missing: list[str] = []
    unknown: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    for key in required:
        val = payload.get(key)
        if val is None or val == "" or val == []:
            missing.append(key)
            errors.append(f"required field missing: {key}")

    absent_optional = [k for k in optional if payload.get(k) in (None, "", [])]
    total = len(required) + len(optional)
    present = total - len(missing) - len(absent_optional)
    score = present / total if total else 1.0

    for key, val in payload.items():
        if val == "unknown" or val == "—":
            unknown.append(key)

    if score < 0.7:
        warnings.append(f"low completeness: {score:.0%}")

    return DataQualityReport(
        completeness_score=score,
        missing_features=missing + absent_optional,
        warnings=warnings,
        validation_errors=errors,
        unknown_values=unknown,
    )


def assert_valid(report: DataQualityReport, *, strict: bool = False) -> None:
    """Raise when validation errors exist and strict mode is enabled."""
    if strict and report.validation_errors:
        raise SnapshotValidationError("; ".join(report.validation_errors))
