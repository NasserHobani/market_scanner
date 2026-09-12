"""Production Integration Pipeline — connects Knowledge, Reasoning, Intelligence."""

from .coordinator import PipelineCoordinatorImpl
from .event_bus import EventBus
from .events import (
    DomainEvent,
    intelligence_completed,
    knowledge_captured,
    pipeline_completed,
    pipeline_failed,
    reasoning_completed,
    similarity_completed,
    stage_completed,
    stage_failed,
    stage_started,
)
from .context import NO_HISTORICAL_EVIDENCE, SimilarityContext, SimilaritySummary
from .similarity_integration import (
    build_similarity_context,
    build_similarity_summary,
    enrich_intelligence_report,
)
from .metrics import MetricsCollector, PipelineMetrics
from .persistence import PipelineStore
from .services import PipelineService
from .state import (
    PIPELINE_VERSION,
    PipelineExecution,
    PipelineStatus,
    PipelineType,
    StageName,
    StageResult,
)
from .validation import ValidationError

__all__ = [
    "DomainEvent",
    "EventBus",
    "EventPublisher",
    "MetricsCollector",
    "PipelineCoordinator",
    "PipelineCoordinatorImpl",
    "PipelineExecution",
    "PipelineMetrics",
    "PipelineRepository",
    "PipelineService",
    "PipelineStatus",
    "PipelineStore",
    "PipelineType",
    "PIPELINE_VERSION",
    "SimilarityContext",
    "SimilaritySummary",
    "NO_HISTORICAL_EVIDENCE",
    "build_similarity_context",
    "build_similarity_summary",
    "enrich_intelligence_report",
    "similarity_completed",
    "StageExecutor",
    "StageName",
    "StageResult",
    "ValidationError",
    "intelligence_completed",
    "knowledge_captured",
    "pipeline_completed",
    "pipeline_failed",
    "reasoning_completed",
    "similarity_completed",
    "stage_completed",
    "stage_failed",
    "stage_started",
]
