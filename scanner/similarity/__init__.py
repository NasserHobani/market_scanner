"""Knowledge Similarity Engine — deterministic historical retrieval."""

from .feature_distance import DistanceConfig, FeatureDistance, FeatureDistanceCalculator
from .filters import RetrievalFilters
from .fingerprint import SituationalFingerprint, build_fingerprint, fingerprint_match_score
from .interfaces import DistanceProvider, RankingProvider, RetrievalProvider, SimilarityProvider
from .ranking import RankingEngine, RankingWeights
from .result import SimilarityMatch, SimilarityResult
from .retrieval import RetrievalEngine
from .services import SimilarityService
from .similarity_engine import SimilarityEngine
from .similarity_score import ComponentWeights, SimilarityScore, SimilarityScorer

__all__ = [
    "ComponentWeights",
    "DistanceConfig",
    "DistanceProvider",
    "FeatureDistance",
    "FeatureDistanceCalculator",
    "RankingEngine",
    "RankingProvider",
    "RankingWeights",
    "RetrievalEngine",
    "RetrievalFilters",
    "RetrievalProvider",
    "SimilarityEngine",
    "SimilarityMatch",
    "SimilarityProvider",
    "SimilarityResult",
    "SimilarityScore",
    "SimilarityScorer",
    "SimilarityService",
    "SituationalFingerprint",
    "build_fingerprint",
    "fingerprint_match_score",
]
