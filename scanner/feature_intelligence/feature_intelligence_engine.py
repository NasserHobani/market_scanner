# -*- coding: utf-8 -*-
"""Feature intelligence engine — orchestrator."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .feature_correlation import FeatureCorrelationEngine
from .feature_drift import FeatureDriftEngine
from .feature_importance import FeatureImportanceEngine
from .feature_report import AnalysisReport, FeatureReportGenerator
from .feature_stability import FeatureStabilityEngine
from .ranking import FeatureRankingEngine, RankedFeature
from .redundancy import RedundancyDetector

FEATURE_INTELLIGENCE_VERSION = "1.0.0"
DEFAULT_HISTORY = Path("data/feature_intelligence/history.jsonl")


@dataclass
class AnalysisResult:
    """Complete feature intelligence analysis."""

    analysis_id: str
    version: str = FEATURE_INTELLIGENCE_VERSION
    importance: list[dict[str, Any]] = field(default_factory=list)
    stability: list[dict[str, Any]] = field(default_factory=list)
    drift: list[dict[str, Any]] = field(default_factory=list)
    correlation: dict[str, Any] = field(default_factory=dict)
    redundancy: dict[str, Any] = field(default_factory=dict)
    ranking: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    row_count: int = 0
    feature_count: int = 0
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "version": self.version,
            "importance": self.importance,
            "stability": self.stability,
            "drift": self.drift,
            "correlation": self.correlation,
            "redundancy": self.redundancy,
            "ranking": self.ranking,
            "report": self.report,
            "row_count": self.row_count,
            "feature_count": self.feature_count,
            "created_at": self.created_at,
        }


class AnalysisHistoryStore:
    """Append-only analysis history."""

    def __init__(self, path: Path | str = DEFAULT_HISTORY) -> None:
        self.path = Path(path)

    def save(self, result: AnalysisResult) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result.to_dict(), ensure_ascii=False, default=str) + "\n")
        return result.analysis_id

    def _read_all(self) -> list[AnalysisResult]:
        if not self.path.exists():
            return []
        out: list[AnalysisResult] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(AnalysisResult(
                    analysis_id=d["analysis_id"],
                    version=d.get("version", FEATURE_INTELLIGENCE_VERSION),
                    importance=d.get("importance", []),
                    stability=d.get("stability", []),
                    drift=d.get("drift", []),
                    correlation=d.get("correlation", {}),
                    redundancy=d.get("redundancy", {}),
                    ranking=d.get("ranking", []),
                    report=d.get("report", {}),
                    row_count=d.get("row_count", 0),
                    feature_count=d.get("feature_count", 0),
                    created_at=d.get("created_at", ""),
                ))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def load(self, analysis_id: str) -> AnalysisResult:
        for r in self._read_all():
            if r.analysis_id == analysis_id:
                return r
        raise KeyError(f"analysis not found: {analysis_id}")

    def history(self, *, limit: int = 50) -> list[AnalysisResult]:
        rows = self._read_all()
        rows.sort(key=lambda r: r.created_at or "", reverse=True)
        return rows[:limit]


class FeatureIntelligenceEngine:
    """Central orchestrator for feature analytics."""

    def __init__(self,
                 importance: FeatureImportanceEngine | None = None,
                 stability: FeatureStabilityEngine | None = None,
                 drift: FeatureDriftEngine | None = None,
                 correlation: FeatureCorrelationEngine | None = None,
                 redundancy: RedundancyDetector | None = None,
                 ranking: FeatureRankingEngine | None = None,
                 reporter: FeatureReportGenerator | None = None,
                 store: AnalysisHistoryStore | None = None) -> None:
        self._importance = importance or FeatureImportanceEngine()
        self._stability = stability or FeatureStabilityEngine()
        self._drift = drift or FeatureDriftEngine()
        self._correlation = correlation or FeatureCorrelationEngine()
        self._redundancy = redundancy or RedundancyDetector()
        self._ranking = ranking or FeatureRankingEngine()
        self._reporter = reporter or FeatureReportGenerator()
        self._store = store or AnalysisHistoryStore()

    def analyze(self, rows: list[dict[str, Any]], *,
                feature_names: list[str] | None = None,
                research_confidence: dict[str, float] | None = None,
                persist: bool = True) -> AnalysisResult:
        import uuid
        analysis_id = f"fia_{uuid.uuid4().hex[:16]}"

        imp = self._importance.compute(rows, feature_names=feature_names)
        stab = self._stability.compute(rows, feature_names=feature_names)
        dr = self._drift.compute(rows, feature_names=feature_names)
        corr = self._correlation.compute_matrix(rows, feature_names=feature_names)
        red = self._redundancy.detect(rows, feature_names=feature_names)
        ranked = self._ranking.rank(
            importance=imp, stability=stab, drift=dr, rows=rows,
            research_confidence=research_confidence,
        )

        imp_map = {r.feature: r for r in imp}
        stab_map = {r.feature: r for r in stab}
        drift_map = {r.feature: r for r in dr}
        rank_map = {r.feature: r for r in ranked}

        feature_reports: list = []
        for feat in (feature_names or [r.feature for r in ranked]):
            feature_reports.append(self._reporter.generate_feature_report(
                feature=feat,
                importance=imp_map.get(feat),
                stability=stab_map.get(feat),
                drift=drift_map.get(feat),
                ranking=rank_map.get(feat),
                outcome_correlation=corr.outcome_correlations.get(feat),
            ))

        analysis_report = self._reporter.generate_analysis_report(
            feature_reports=feature_reports,
            redundancy=red,
            ranking=ranked,
            row_count=len(rows),
        )

        result = AnalysisResult(
            analysis_id=analysis_id,
            importance=[r.to_dict() for r in imp],
            stability=[r.to_dict() for r in stab],
            drift=[r.to_dict() for r in dr],
            correlation=corr.to_dict(),
            redundancy=red.to_dict(),
            ranking=[r.to_dict() for r in ranked],
            report=analysis_report.to_dict(),
            row_count=len(rows),
            feature_count=len(ranked),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        if persist:
            self._store.save(result)
        return result

    def rank(self, rows: list[dict[str, Any]], **kwargs: Any) -> list[RankedFeature]:
        result = self.analyze(rows, persist=False, **kwargs)
        return [
            RankedFeature(
                feature=r["feature"], rank=r["rank"],
                composite_score=r["composite_score"],
                importance_score=r.get("importance_score"),
                stability_score=r.get("stability_score"),
                coverage_score=r.get("coverage_score"),
                drift_score=r.get("drift_score"),
                data_quality_score=r.get("data_quality_score"),
                research_confidence_score=r.get("research_confidence_score"),
                components=r.get("components", {}),
                notes=r.get("notes", []),
            )
            for r in result.ranking
        ]

    def drift(self, rows: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._drift.compute(rows, **kwargs)]

    def report(self, analysis_id: str) -> dict[str, Any]:
        return self._store.load(analysis_id).report

    def history(self, *, limit: int = 50) -> list[AnalysisResult]:
        return self._store.history(limit=limit)
