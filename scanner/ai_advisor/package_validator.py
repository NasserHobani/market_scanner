# -*- coding: utf-8 -*-
"""Pre-Claude package validation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .unified_package import UNIFIED_PACKAGE_VERSION, UnifiedDecisionPackage

MAX_PACKAGE_BYTES = 512_000
REQUIRED_SECTIONS = ("recommendation", "reasoning", "decision_ai")


@dataclass
class PackageValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return not self.valid or bool(self.errors)


class PackageValidator:
    """Validate unified package before Claude invocation."""

    def validate(self, package: UnifiedDecisionPackage) -> PackageValidationResult:
        result = PackageValidationResult()

        self._check_version(package, result)
        self._check_completeness(package, result)
        self._check_evidence(package, result)
        self._check_references(package, result)
        self._check_size(package, result)
        self._check_metadata(package, result)

        result.valid = len(result.errors) == 0
        return result

    def _check_version(self, package: UnifiedDecisionPackage,
                       result: PackageValidationResult) -> None:
        if package.schema_version != UNIFIED_PACKAGE_VERSION:
            result.errors.append(
                f"Version mismatch: {package.schema_version} != {UNIFIED_PACKAGE_VERSION}"
            )

    def _check_completeness(self, package: UnifiedDecisionPackage,
                            result: PackageValidationResult) -> None:
        data = package.to_dict()
        for section in REQUIRED_SECTIONS:
            sec = data.get(section)
            if not sec or (isinstance(sec, dict) and not sec):
                result.errors.append(f"Missing required section: {section}")

        if not package.recommendation.get("action") and not package.recommendation.get("direction"):
            result.warnings.append("Recommendation section lacks action/direction")

    def _check_evidence(self, package: UnifiedDecisionPackage,
                        result: PackageValidationResult) -> None:
        if not package.evidence_index:
            result.errors.append("No evidence indexed — untraceable package")
            return
        for ev in package.evidence_index:
            if not ev.evidence_id:
                result.errors.append("Evidence item missing evidence_id")
            if not ev.source_layer:
                result.warnings.append(f"Evidence {ev.evidence_id} missing source_layer")
            if not ev.reference and not ev.section:
                result.warnings.append(f"Evidence {ev.evidence_id} missing reference")

    def _check_references(self, package: UnifiedDecisionPackage,
                          result: PackageValidationResult) -> None:
        allowed = package.allowed_sections()
        for ev in package.evidence_index:
            if ev.section and ev.section not in allowed:
                result.errors.append(f"Invalid evidence section: {ev.section}")

    def _check_size(self, package: UnifiedDecisionPackage,
                    result: PackageValidationResult) -> None:
        size = len(json.dumps(package.to_dict(), default=str))
        if size > MAX_PACKAGE_BYTES:
            result.errors.append(f"Oversized package: {size} bytes > {MAX_PACKAGE_BYTES}")

    def _check_metadata(self, package: UnifiedDecisionPackage,
                        result: PackageValidationResult) -> None:
        meta = package.metadata
        for key in ("symbol", "market", "timeframe"):
            if not meta.get(key):
                result.warnings.append(f"Metadata missing: {key}")
