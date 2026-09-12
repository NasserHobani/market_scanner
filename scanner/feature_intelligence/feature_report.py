# -*- coding: utf-8 -*-
"""Structured feature reports — no natural language AI."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .feature_drift import DriftResult
from .feature_importance import ImportanceResult
from .feature_stability import StabilityResult
from .ranking import RankedFeature
from .redundancy import RedundancyResult


@dataclass
class FeatureReport:
    """Structured report for a single feature."""

    report_id: str
    feature: str
    history: dict[str, Any] = field(default_factory=dict)
    importance: dict[str, Any] = field(default_factory=dict)
    stability: dict[str, Any] = field(default_factory=dict)
    correlation: dict[str, Any] = field(default_factory=dict)
    drift: dict[str, Any] = field(default_factory=dict)
    ranking: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "feature": self.feature,
            "history": dict(self.history),
            "importance": dict(self.importance),
            "stability": dict(self.stability),
            "correlation": dict(self.correlation),
            "drift": dict(self.drift),
            "ranking": dict(self.ranking),
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
            "generated_at": self.generated_at,
        }


@dataclass
class AnalysisReport:
    """Full feature intelligence analysis report."""

    analysis_id: str
    feature_reports: list[FeatureReport] = field(default_factory=list)
    redundancy: dict[str, Any] = field(default_factory=dict)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "feature_reports": [r.to_dict() for r in self.feature_reports],
            "redundancy": self.redundancy,
            "ranking": self.ranking,
            "summary": self.summary,
            "generated_at": self.generated_at,
        }


class FeatureReportGenerator:
    """Generate structured feature intelligence reports."""

    def generate_feature_report(self, *,
                                feature: str,
                                importance: ImportanceResult | None = None,
                                stability: StabilityResult | None = None,
                                drift: DriftResult | None = None,
                                ranking: RankedFeature | None = None,
                                outcome_correlation: float | None = None,
                                history: dict[str, Any] | None = None) -> FeatureReport:
        warnings: list[str] = []
        recommendations: list[str] = []

        if importance and importance.sample_size < 20:
            warnings.append(f"Low sample size for importance (n={importance.sample_size})")
        if stability and stability.overall_stability is not None and stability.overall_stability < 0.5:
            warnings.append("Low stability score")
            recommendations.append("Investigate feature stability before using in ML")
        if drift and drift.warnings:
            warnings.extend(drift.warnings)
            recommendations.append("Monitor drift — consider re-baselining")
        if ranking and ranking.coverage_score is not None and ranking.coverage_score < 0.7:
            warnings.append("Coverage below 70%")
            recommendations.append("Improve data collection for this feature")

        imp_abs = abs(importance.correlation_r_multiple or 0) if importance else 0
        if imp_abs > 0.3:
            recommendations.append("Feature shows meaningful outcome correlation — candidate for ML")

        return FeatureReport(
            report_id=f"frep_{uuid.uuid4().hex[:16]}",
            feature=feature,
            history=history or {},
            importance=importance.to_dict() if importance else {},
            stability=stability.to_dict() if stability else {},
            correlation={"outcome_correlation": outcome_correlation},
            drift=drift.to_dict() if drift else {},
            ranking=ranking.to_dict() if ranking else {},
            warnings=warnings,
            recommendations=recommendations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def generate_analysis_report(self, *,
                                 feature_reports: list[FeatureReport],
                                 redundancy: RedundancyResult | None = None,
                                 ranking: list[RankedFeature] | None = None,
                                 row_count: int = 0) -> AnalysisReport:
        return AnalysisReport(
            analysis_id=f"fia_{uuid.uuid4().hex[:16]}",
            feature_reports=feature_reports,
            redundancy=redundancy.to_dict() if redundancy else {},
            ranking=[r.to_dict() for r in (ranking or [])],
            summary={
                "feature_count": len(feature_reports),
                "row_count": row_count,
                "top_feature": ranking[0].feature if ranking else None,
                "redundancy_warnings": len(redundancy.warnings) if redundancy else 0,
            },
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
