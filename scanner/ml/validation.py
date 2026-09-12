# -*- coding: utf-8 -*-
"""Dataset validation — schema, features, labels, versions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .feature_registry import MLFeatureRegistry
from .feature_store import MLDataset
from .label_store import LabelStore, LabelName
from .metadata import FEATURE_VERSION, LABEL_VERSION, SCHEMA_VERSION


@dataclass
class ValidationIssue:
    severity: str  # error | warning
    code: str
    message: str
    row_index: int | None = None
    field: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "row_index": self.row_index,
            "field": self.field,
        }


@dataclass
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    row_count: int = 0
    feature_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [i.to_dict() for i in self.issues],
            "row_count": self.row_count,
            "feature_count": self.feature_count,
            "error_count": sum(1 for i in self.issues if i.severity == "error"),
            "warning_count": sum(1 for i in self.issues if i.severity == "warning"),
        }


class DatasetValidator:
    """Validate ML datasets before export or training."""

    def __init__(self,
                 feature_registry: MLFeatureRegistry | None = None,
                 label_store: LabelStore | None = None) -> None:
        self._features = feature_registry or MLFeatureRegistry()
        self._labels = label_store or LabelStore()

    def validate(self, dataset: MLDataset, *,
                 expected_schema_version: str = SCHEMA_VERSION,
                 expected_feature_version: str = FEATURE_VERSION,
                 expected_label_version: str = LABEL_VERSION,
                 required_features: list[str] | None = None,
                 required_labels: list[str] | None = None,
                 max_missing_pct: float = 50.0) -> ValidationResult:
        issues: list[ValidationIssue] = []

        if dataset.row_count == 0:
            issues.append(ValidationIssue("error", "EMPTY_DATASET",
                                          "Dataset has zero rows"))

        if expected_schema_version != SCHEMA_VERSION:
            issues.append(ValidationIssue(
                "error", "SCHEMA_VERSION_MISMATCH",
                f"Expected schema {expected_schema_version}, current {SCHEMA_VERSION}",
            ))

        if expected_feature_version != self._features.schema_version():
            issues.append(ValidationIssue(
                "warning", "FEATURE_VERSION_MISMATCH",
                f"Expected feature version {expected_feature_version}, "
                f"registry is {self._features.schema_version()}",
            ))

        if expected_label_version != self._labels.schema_version():
            issues.append(ValidationIssue(
                "warning", "LABEL_VERSION_MISMATCH",
                f"Expected label version {expected_label_version}, "
                f"store is {self._labels.schema_version()}",
            ))

        req_features = required_features or []
        req_labels = required_labels or [LabelName.R_MULTIPLE.value]

        for idx, row in enumerate(dataset.rows):
            for feat in req_features:
                if feat not in row.features or row.features[feat] is None:
                    issues.append(ValidationIssue(
                        "warning", "MISSING_FEATURE",
                        f"Required feature '{feat}' missing",
                        row_index=idx, field=feat,
                    ))

            for lbl in req_labels:
                val = row.labels.get(lbl)
                if val is None:
                    issues.append(ValidationIssue(
                        "error", "INVALID_LABEL",
                        f"Required label '{lbl}' is null",
                        row_index=idx, field=lbl,
                    ))

            r_mult = row.labels.get(LabelName.R_MULTIPLE.value)
            if r_mult is not None and not isinstance(r_mult, (int, float)):
                issues.append(ValidationIssue(
                    "error", "INVALID_LABEL",
                    f"R-multiple must be numeric, got {type(r_mult).__name__}",
                    row_index=idx, field=LabelName.R_MULTIPLE.value,
                ))

        if dataset.rows:
            total_missing = sum(len(r.missing_features) for r in dataset.rows)
            total_features = len(dataset.rows) * max(len(dataset.column_order), 1)
            missing_pct = (total_missing / total_features * 100) if total_features else 0
            if missing_pct > max_missing_pct:
                issues.append(ValidationIssue(
                    "warning", "HIGH_MISSING_RATE",
                    f"Missing feature rate {missing_pct:.1f}% exceeds {max_missing_pct}%",
                ))

        errors = [i for i in issues if i.severity == "error"]
        return ValidationResult(
            valid=len(errors) == 0,
            issues=issues,
            row_count=dataset.row_count,
            feature_count=len(dataset.column_order),
        )
