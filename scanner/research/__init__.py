"""Quant research — dashboard computation and research laboratory."""

from .dashboard import build_dashboard
from .services import ResearchService
from .research_engine import ResearchEngine
from .experiment import Experiment, ExperimentStatus, ExperimentStore
from .hypothesis import Hypothesis, HypothesisEngine
from .dataset import Dataset, DatasetBuilder
from .metrics import MetricsEngine
from .comparison import ComparisonEngine, ComparisonResult
from .report import ResearchReport, ReportGenerator
from .orchestrator import ResearchOrchestrator, ResearchTrigger
from .jobs import ResearchJob, JobStore, JobStatus
from .config import ResearchOrchestratorConfig, load_research_config

__all__ = [
    "build_dashboard",
    "ResearchService",
    "ResearchEngine",
    "Experiment",
    "ExperimentStatus",
    "ExperimentStore",
    "Hypothesis",
    "HypothesisEngine",
    "Dataset",
    "DatasetBuilder",
    "MetricsEngine",
    "ComparisonEngine",
    "ComparisonResult",
    "ResearchReport",
    "ReportGenerator",
    "ResearchOrchestrator",
    "ResearchTrigger",
    "ResearchJob",
    "JobStore",
    "JobStatus",
    "ResearchOrchestratorConfig",
    "load_research_config",
]
