"""Trading Knowledge Base — foundation for AI, ML, and research.

This module is the future source of truth for platform knowledge.
It does not modify trading, recommendation, or backtesting logic.
"""

from .audit import AuditTrail, VerificationStatus
from .compat import is_legacy_snapshot, upgrade_snapshot
from .context_builder import ContextBuilder
from .data_quality import DataQualityReport, assert_valid, assess_completeness
from .feature_metadata import FeatureRegistry, FeatureValue
from .feature_vector import FeatureVectorExport
from .fingerprint import market_fingerprint
from .interfaces import (
    ContextProvider,
    FeatureVectorProvider,
    KnowledgeProvider,
    SnapshotProvider,
)
from .market_environment import MarketEnvironment
from .memory import (
    KnowledgeMemory,
    KnowledgeSummary,
    MarketSummary,
    PerformanceSummary,
    StrategySummary,
)
from .relationships import (
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeRelationship,
    RelationKind,
    build_graph_from_history,
)
from .repository import KnowledgeRepository
from .schemas import (
    KnowledgeRecord,
    KnowledgeRef,
    OutcomeClass,
    SnapshotKind,
    StrategyStatistics,
    TradeLifecycle,
)
from .services import KnowledgeService
from .snapshot_builder import SnapshotBuilder
from .versioning import GENERATOR_VERSION, KNOWLEDGE_SCHEMA_VERSION, SchemaMetadata

__all__ = [
    "AuditTrail",
    "ContextBuilder",
    "ContextProvider",
    "DataQualityReport",
    "FeatureRegistry",
    "FeatureValue",
    "FeatureVectorExport",
    "FeatureVectorProvider",
    "GENERATOR_VERSION",
    "KNOWLEDGE_SCHEMA_VERSION",
    "KnowledgeGraph",
    "KnowledgeMemory",
    "KnowledgeNode",
    "KnowledgeProvider",
    "KnowledgeRecord",
    "KnowledgeRef",
    "KnowledgeRelationship",
    "KnowledgeService",
    "KnowledgeSummary",
    "MarketEnvironment",
    "MarketSummary",
    "OutcomeClass",
    "PerformanceSummary",
    "RelationKind",
    "SchemaMetadata",
    "SnapshotBuilder",
    "SnapshotKind",
    "SnapshotProvider",
    "StrategyStatistics",
    "StrategySummary",
    "TradeLifecycle",
    "VerificationStatus",
    "assert_valid",
    "assess_completeness",
    "build_graph_from_history",
    "is_legacy_snapshot",
    "market_fingerprint",
    "upgrade_snapshot",
]
