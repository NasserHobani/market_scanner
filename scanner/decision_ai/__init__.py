"""AI Decision Support Engine — structured reasoning, no LLM."""

from .services import DecisionAIService
from .context_builder import ContextBuilder, DecisionAIContext, DECISION_AI_VERSION
from .evidence_builder import EvidenceBuilder, UnifiedEvidenceItem, UnifiedEvidenceBundle
from .prompt_builder import PromptBuilder, PromptType, StructuredPrompt
from .decision_summary import DecisionSummary, DecisionSummaryBuilder
from .confidence_fusion import ConfidenceFusion, FusedConfidence, FUSION_WEIGHTS
from .guardrails import Guardrails, GuardrailReport, GuardrailViolation
from .ai_review import AIReview, AIReviewEngine

__all__ = [
    "DecisionAIService",
    "ContextBuilder",
    "DecisionAIContext",
    "DECISION_AI_VERSION",
    "EvidenceBuilder",
    "UnifiedEvidenceItem",
    "UnifiedEvidenceBundle",
    "PromptBuilder",
    "PromptType",
    "StructuredPrompt",
    "DecisionSummary",
    "DecisionSummaryBuilder",
    "ConfidenceFusion",
    "FusedConfidence",
    "FUSION_WEIGHTS",
    "Guardrails",
    "GuardrailReport",
    "GuardrailViolation",
    "AIReview",
    "AIReviewEngine",
]
