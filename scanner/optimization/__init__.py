"""Strategy Optimization Engine — deterministic parameter search."""

from .services import OptimizationService
from .optimization_engine import OptimizationEngine
from .optimizer import Optimizer, OptimizationMethod
from .parameter_space import Parameter, ParameterSpace, ParameterType, ParameterConstraint
from .grid_search import GridSearchOptimizer
from .random_search import RandomSearchOptimizer
from .walk_forward_optimizer import WalkForwardOptimizer
from .evaluation import ParameterEvaluator, apply_parameters, sort_rows_by_time
from .ranking import ParameterRanker, DEFAULT_RANKING_WEIGHTS
from .report import OptimizationReportGenerator
from .experiment_registry import (
    ExperimentRegistry,
    OptimizationExperiment,
    OptimizationStatus,
    OPTIMIZATION_VERSION,
)
from .interfaces import OptimizerProtocol, EvaluatorProtocol, OptimizationEngineProtocol

__all__ = [
    "OptimizationService",
    "OptimizationEngine",
    "Optimizer",
    "OptimizationMethod",
    "Parameter",
    "ParameterSpace",
    "ParameterType",
    "ParameterConstraint",
    "GridSearchOptimizer",
    "RandomSearchOptimizer",
    "WalkForwardOptimizer",
    "ParameterEvaluator",
    "apply_parameters",
    "sort_rows_by_time",
    "ParameterRanker",
    "DEFAULT_RANKING_WEIGHTS",
    "OptimizationReportGenerator",
    "ExperimentRegistry",
    "OptimizationExperiment",
    "OptimizationStatus",
    "OPTIMIZATION_VERSION",
    "OptimizerProtocol",
    "EvaluatorProtocol",
    "OptimizationEngineProtocol",
]
