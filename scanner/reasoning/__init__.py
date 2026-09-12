"""AI Reasoning Framework — explainable evidence-based review.

Sits between the Knowledge Layer and future AI Assistant.
Does NOT generate recommendations or call any LLM.
"""

from .confidence import ConfidenceBreakdown, ConfidenceEngine, ConfidenceProvider, DEFAULT_CATEGORY_WEIGHTS
from .contradiction import Contradiction, ContradictionEngine, ContradictionReport
from .decision_tree import DecisionStage, DecisionTree, DecisionTreeResult, DEFAULT_STAGES
from .evidence import Evidence, EvidenceBundle, EvidenceCategory, EvidenceDirection, EvidenceStrength
from .evidence_engine import EvidenceEngine, EvidenceProvider
from .explainability import ExplainabilityEngine, ExplainabilityProvider, StructuredExplanation
from .interfaces import ReasoningProvider
from .reasoning_context import ReasoningContext
from .reasoning_engine import ReasoningEngine
from .recommendation_review import RecommendationReview, RecommendationReviewer
from .services import ReasoningService

__all__ = [
    "ConfidenceBreakdown",
    "ConfidenceEngine",
    "ConfidenceProvider",
    "Contradiction",
    "ContradictionEngine",
    "ContradictionReport",
    "DEFAULT_CATEGORY_WEIGHTS",
    "DEFAULT_STAGES",
    "DecisionStage",
    "DecisionTree",
    "DecisionTreeResult",
    "Evidence",
    "EvidenceBundle",
    "EvidenceCategory",
    "EvidenceDirection",
    "EvidenceEngine",
    "EvidenceProvider",
    "EvidenceStrength",
    "ExplainabilityEngine",
    "ExplainabilityProvider",
    "ReasoningContext",
    "ReasoningEngine",
    "ReasoningProvider",
    "ReasoningService",
    "RecommendationReview",
    "RecommendationReviewer",
    "StructuredExplanation",
]
