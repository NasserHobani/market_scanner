# -*- coding: utf-8 -*-
"""Guardrails — validation rules that report uncertainty."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardrailViolation:
    rule: str
    severity: str  # warning | error
    message: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass
class GuardrailReport:
    passed: bool
    violations: list[GuardrailViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": list(self.warnings),
            "missing_evidence": list(self.missing_evidence),
            "violation_count": len(self.violations),
            "warning_count": len(self.warnings),
        }


class Guardrails:
    """Validate decision context — never hide missing evidence."""

    PREDICTION_CONFIDENCE_MIN = 0.55
    RESEARCH_SAMPLE_MIN = 20
    SIMILARITY_MATCH_MIN = 3
    FEATURE_DRIFT_MAX = 0.5
    MODEL_AGE_DAYS_MAX = 90

    def validate(self, context: dict[str, Any], *,
                 evidence: dict[str, Any] | None = None) -> GuardrailReport:
        violations: list[GuardrailViolation] = []
        warnings: list[str] = []
        missing: list[str] = []

        ev = evidence or {}
        for src in ev.get("sources_missing") or []:
            missing.append(src)
            violations.append(GuardrailViolation(
                rule="missing_evidence_source",
                severity="warning",
                message=f"Evidence source not available: {src}",
                evidence=f"sources_missing={src}",
            ))

        # Prediction confidence too low
        pred = context.get("prediction") or {}
        pred_conf = pred.get("confidence") or pred.get("probability")
        if pred and pred_conf is not None and float(pred_conf) < self.PREDICTION_CONFIDENCE_MIN:
            violations.append(GuardrailViolation(
                rule="prediction_confidence_low",
                severity="warning",
                message=f"Prediction confidence {pred_conf} below threshold {self.PREDICTION_CONFIDENCE_MIN}",
                evidence=f"confidence={pred_conf}",
            ))

        # Research sample too small
        research = context.get("research") or {}
        if research:
            ds = research.get("dataset_summary") or {}
            n = ds.get("closed_count") or ds.get("count") or 0
            if n < self.RESEARCH_SAMPLE_MIN:
                violations.append(GuardrailViolation(
                    rule="research_sample_small",
                    severity="warning",
                    message=f"Research sample size {n} below minimum {self.RESEARCH_SAMPLE_MIN}",
                    evidence=f"sample_size={n}",
                ))

        # Similarity insufficient
        sim = context.get("similarity") or {}
        if sim.get("available") and (sim.get("match_count") or 0) < self.SIMILARITY_MATCH_MIN:
            violations.append(GuardrailViolation(
                rule="similarity_insufficient",
                severity="warning",
                message=f"Similarity match count {sim.get('match_count')} below minimum {self.SIMILARITY_MATCH_MIN}",
                evidence=f"match_count={sim.get('match_count')}",
            ))
        elif not sim.get("available"):
            missing.append("similarity")
            warnings.append("No historical similarity evidence available")

        # High feature drift
        fi = context.get("feature_intelligence") or {}
        drift_list = fi.get("drift") or []
        for d in drift_list:
            if isinstance(d, dict) and (d.get("drift_score") or 0) > self.FEATURE_DRIFT_MAX:
                violations.append(GuardrailViolation(
                    rule="feature_drift_high",
                    severity="warning",
                    message=f"High drift on feature '{d.get('feature')}': {d.get('drift_score')}",
                    evidence=f"drift_score={d.get('drift_score')}",
                ))

        # Model outdated (check prediction model_version timestamp if available)
        if pred.get("model_id") and not pred.get("model_version"):
            warnings.append("Model version not recorded — cannot verify freshness")

        # Reasoning missing information
        reasoning = context.get("reasoning") or {}
        for mi in reasoning.get("missing_information") or []:
            missing.append(f"reasoning:{mi}")
            warnings.append(f"Reasoning missing: {mi}")

        # Memory gaps
        for gap in context.get("memory_gaps") or []:
            missing.append(f"memory:{gap}")

        errors = [v for v in violations if v.severity == "error"]
        return GuardrailReport(
            passed=len(errors) == 0,
            violations=violations,
            warnings=warnings,
            missing_evidence=sorted(set(missing)),
        )
