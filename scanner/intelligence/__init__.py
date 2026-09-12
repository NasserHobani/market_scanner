"""Intelligence Layer — statistical discovery from historical trades.

Sits above Knowledge and Reasoning. Does NOT use LLM, ML, or prediction.
Discovers patterns, monitors edge, and produces structured insights.
"""

from .edge_monitor import EdgeAlert, EdgeMonitor, EdgeMonitorReport, EdgeSnapshot
from .historical_statistics import HistoricalStatistics, HistoricalStatisticsEngine, StatRow
from .insight import (
    Insight,
    InsightCategory,
    InsightEngine,
    InsightImportance,
    InsightReport,
)
from .intelligence_engine import IntelligenceEngine, IntelligenceReport
from .interfaces import HealthProvider, InsightProvider, IntelligenceProvider, PatternProvider
from .knowledge_summary import FactorImportance, KnowledgeSummary, KnowledgeSummaryEngine
from .market_memory import MarketMemory, MarketMemoryEngine, MarketMemoryRecord
from .pattern_engine import PatternEngine, PatternInsight, PatternReport
from .services import IntelligenceService
from .strategy_health import StrategyHealthEngine, StrategyHealthReport
from .trend_monitor import TrendMonitor, TrendMonitorReport, TrendPoint

__all__ = [
    "EdgeAlert",
    "EdgeMonitor",
    "EdgeMonitorReport",
    "EdgeSnapshot",
    "FactorImportance",
    "HealthProvider",
    "HistoricalStatistics",
    "HistoricalStatisticsEngine",
    "Insight",
    "InsightCategory",
    "InsightEngine",
    "InsightImportance",
    "InsightProvider",
    "InsightReport",
    "IntelligenceEngine",
    "IntelligenceProvider",
    "IntelligenceReport",
    "IntelligenceService",
    "KnowledgeSummary",
    "KnowledgeSummaryEngine",
    "MarketMemory",
    "MarketMemoryEngine",
    "MarketMemoryRecord",
    "PatternEngine",
    "PatternInsight",
    "PatternProvider",
    "PatternReport",
    "StatRow",
    "StrategyHealthEngine",
    "StrategyHealthReport",
    "TrendMonitor",
    "TrendMonitorReport",
    "TrendPoint",
]
