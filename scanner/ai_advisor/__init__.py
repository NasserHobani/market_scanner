"""AI Advisor Framework — LLM integration in Shadow Mode.

The LLM reviews. The platform decides.
"""

from .advisor_service import AIAdvisorService
from .advisor_engine import AdvisorEngine
from .advisor_score import AdvisorScore, AdvisorScoreMetrics
from .decision_package import (
    DecisionPackage,
    DecisionPackageBuilder,
    EvidenceRef,
    AI_ADVISOR_VERSION,
)
from .unified_package import (
    UnifiedDecisionPackage,
    UnifiedPackageBuilder,
    UNIFIED_PACKAGE_VERSION,
)
from .history import AdvisorHistory
from .interfaces import LLMProviderProtocol, AdvisorServiceProtocol, MemoryStoreProtocol
from .memory import AdvisorMemory
from .prompt_builder import PromptBuilder, AdvisorPrompt, PromptTemplate, DEFAULT_PROMPT_VERSION
from .provider_registry import ProviderRegistry, get_registry
from .response_parser import ResponseParser, ResponseParseError
from .response_validator import ResponseValidator, ValidationResult
from .review import AdvisorReview, ReviewEngine, EvidenceCitation, SuggestedExperiment

__all__ = [
    "AIAdvisorService",
    "AdvisorEngine",
    "AdvisorScore",
    "AdvisorScoreMetrics",
    "DecisionPackage",
    "DecisionPackageBuilder",
    "EvidenceRef",
    "AI_ADVISOR_VERSION",
    "UnifiedDecisionPackage",
    "UnifiedPackageBuilder",
    "UNIFIED_PACKAGE_VERSION",
    "AdvisorHistory",
    "AdvisorMemory",
    "LLMProviderProtocol",
    "AdvisorServiceProtocol",
    "MemoryStoreProtocol",
    "PromptBuilder",
    "AdvisorPrompt",
    "PromptTemplate",
    "DEFAULT_PROMPT_VERSION",
    "ProviderRegistry",
    "get_registry",
    "ResponseParser",
    "ResponseParseError",
    "ResponseValidator",
    "ValidationResult",
    "AdvisorReview",
    "ReviewEngine",
    "EvidenceCitation",
    "SuggestedExperiment",
]
