# -*- coding: utf-8 -*-
"""Response validator — never trust the LLM."""
from __future__ import annotations

from typing import Any

from .decision_package import DecisionPackage
from .unified_package import UnifiedDecisionPackage

REQUIRED_FIELDS = frozenset({
    "agreement", "confidence", "summary", "reasoning",
    "supporting_evidence", "contradicting_evidence",
    "risks", "missing_information", "suggested_experiment",
    "shadow_mode_acknowledged",
})

VALID_AGREEMENTS = frozenset({"agree", "disagree", "partial"})

FORBIDDEN_OVERRIDE_FIELDS = frozenset({
    "buy", "sell", "stop", "target", "action_override",
    "direction_override", "entry_override", "exit_override",
})


class ValidationResult:
  def __init__(self) -> None:
    self.errors: list[str] = []
    self.warnings: list[str] = []
    self.hallucinations: list[str] = []
    self.grounding_failures: list[str] = []

  @property
  def valid(self) -> bool:
    return len(self.errors) == 0

  @property
  def rejected(self) -> bool:
    return bool(self.errors) or bool(self.hallucinations)

  def to_dict(self) -> dict[str, Any]:
    return {
      "valid": self.valid,
      "rejected": self.rejected,
      "errors": list(self.errors),
      "warnings": list(self.warnings),
      "hallucinations": list(self.hallucinations),
      "grounding_failures": list(self.grounding_failures),
      "hallucination_count": len(self.hallucinations),
    }


class ResponseValidator:
    """Validate LLM responses against the Decision Package."""

    def validate(self, parsed: dict[str, Any],
                 package: DecisionPackage | UnifiedDecisionPackage) -> ValidationResult:
        result = ValidationResult()

        self._check_required_fields(parsed, result)
        self._check_agreement(parsed, result)
        self._check_confidence(parsed, result)
        self._check_shadow_mode(parsed, result)
        self._check_no_overrides(parsed, result)
        self._check_grounding(parsed, package, result)
        self._check_evidence_citations(parsed, package, result)

        return result

    def _check_required_fields(self, parsed: dict, result: ValidationResult) -> None:
        missing = REQUIRED_FIELDS - set(parsed.keys())
        if missing:
            result.errors.append(f"Missing required fields: {sorted(missing)}")

    def _check_agreement(self, parsed: dict, result: ValidationResult) -> None:
        agreement = parsed.get("agreement")
        if agreement and agreement not in VALID_AGREEMENTS:
            result.errors.append(f"Invalid agreement value: {agreement}")

    def _check_confidence(self, parsed: dict, result: ValidationResult) -> None:
        conf = parsed.get("confidence")
        if conf is not None:
            try:
                val = float(conf)
                if not 0 <= val <= 100:
                    result.warnings.append(f"Confidence out of range: {val}")
            except (TypeError, ValueError):
                result.errors.append(f"Invalid confidence: {conf}")

    def _check_shadow_mode(self, parsed: dict, result: ValidationResult) -> None:
        if not parsed.get("shadow_mode_acknowledged"):
            result.errors.append("shadow_mode_acknowledged must be true")

    def _check_no_overrides(self, parsed: dict, result: ValidationResult) -> None:
        for key in parsed:
            if key.lower() in FORBIDDEN_OVERRIDE_FIELDS:
                result.errors.append(f"Forbidden override field: {key}")

        text_blob = str(parsed).lower()
        for term in ("override buy", "override sell", "change stop", "change target"):
            if term in text_blob:
                result.errors.append(f"Response attempts to override decision: {term}")

    def _check_grounding(self, parsed: dict, package: DecisionPackage | UnifiedDecisionPackage,
                         result: ValidationResult) -> None:
        allowed_ids = package.evidence_ids()
        allowed_sections = package.allowed_sections() | {"reasoning"}

        for field_name in ("supporting_evidence", "contradicting_evidence"):
            items = parsed.get(field_name) or []
            if not isinstance(items, list):
                result.errors.append(f"{field_name} must be a list")
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                eid = item.get("evidence_id", "")
                section = item.get("section", "")

                if eid and eid not in allowed_ids:
                    msg = f"Unknown evidence_id: {eid}"
                    result.hallucinations.append(msg)
                    result.grounding_failures.append(msg)

                if section and section not in allowed_sections:
                    msg = f"Unknown section reference: {section}"
                    result.hallucinations.append(msg)
                    result.grounding_failures.append(msg)

    def _check_evidence_citations(self, parsed: dict, package: DecisionPackage | UnifiedDecisionPackage,
                                  result: ValidationResult) -> None:
        """Flag claims in reasoning that reference unknown evidence."""
        reasoning = str(parsed.get("reasoning", ""))
        if not reasoning:
            return

        for word in reasoning.split():
            if word.startswith("ev_") and word not in package.evidence_ids():
                result.warnings.append(f"Reasoning references unknown id: {word}")
