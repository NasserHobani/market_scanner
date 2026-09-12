"""Feature intelligence — deterministic feature analytics."""

from .services import FeatureIntelligenceService
from .feature_intelligence_engine import (
    FeatureIntelligenceEngine,
    AnalysisResult,
    AnalysisHistoryStore,
    FEATURE_INTELLIGENCE_VERSION,
)
from .feature_importance import FeatureImportanceEngine, ImportanceResult
from .feature_stability import FeatureStabilityEngine, StabilityResult
from .feature_drift import FeatureDriftEngine, DriftResult
from .feature_correlation import FeatureCorrelationEngine, CorrelationMatrix
from .redundancy import RedundancyDetector, RedundancyResult
from .ranking import FeatureRankingEngine, RankedFeature, RANKING_WEIGHTS
from .feature_report import FeatureReport, AnalysisReport, FeatureReportGenerator

__all__ = [
    "FeatureIntelligenceService",
    "FeatureIntelligenceEngine",
    "AnalysisResult",
    "AnalysisHistoryStore",
    "FEATURE_INTELLIGENCE_VERSION",
    "FeatureImportanceEngine",
    "ImportanceResult",
    "FeatureStabilityEngine",
    "StabilityResult",
    "FeatureDriftEngine",
    "DriftResult",
    "FeatureCorrelationEngine",
    "CorrelationMatrix",
    "RedundancyDetector",
    "RedundancyResult",
    "FeatureRankingEngine",
    "RankedFeature",
    "RANKING_WEIGHTS",
    "FeatureReport",
    "AnalysisReport",
    "FeatureReportGenerator",
]
