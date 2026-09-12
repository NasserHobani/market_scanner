# -*- coding: utf-8 -*-
"""Public analysis service API."""
from __future__ import annotations

from typing import Any

from .analysis_orchestrator import AnalysisOrchestrator
from .cache import StageCache
from .result import MarketAnalysis
from .retry import RetryHandler, RetryPolicy
from .scheduler import AnalysisScheduler
from .timeout import TimeoutHandler, TimeoutPolicy
from .workflow import WorkflowDefinition


class AnalysisService:
    """Public facade for market analysis orchestration.

    Coordinates all platform components into one analysis workflow.
    No UI, no REST API, no LLM — orchestration only.
    """

    def __init__(self, orchestrator: AnalysisOrchestrator | None = None,
                 scheduler: AnalysisScheduler | None = None,
                 **orchestrator_kwargs: Any) -> None:
        self._orchestrator = orchestrator or AnalysisOrchestrator(**orchestrator_kwargs)
        self._scheduler = scheduler or AnalysisScheduler()

    def analyze_market(self, *,
                       symbol: str,
                       market: str = "crypto",
                       timeframe: str = "4h",
                       scan_source: dict[str, Any] | None = None,
                       trade_rows: list[dict] | None = None) -> MarketAnalysis:
        """Run full market analysis workflow."""
        return self._orchestrator.run(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            scan_source=scan_source,
            trade_rows=trade_rows,
        )

    def analyze_symbol(self, symbol: str, **kwargs: Any) -> MarketAnalysis:
        """Analyze a specific symbol."""
        return self.analyze_market(symbol=symbol, **kwargs)

    def analyze_strategy(self, strategy_id: str, *,
                       symbol: str,
                       trade_rows: list[dict] | None = None,
                       **kwargs: Any) -> MarketAnalysis:
        """Analyze with strategy context."""
        scan_source = kwargs.pop("scan_source", None) or {}
        scan_source["strategy_id"] = strategy_id
        return self.analyze_market(
            symbol=symbol,
            scan_source=scan_source,
            trade_rows=trade_rows,
            **kwargs,
        )

    def status(self, analysis_id: str) -> dict[str, Any] | None:
        """Get analysis status summary."""
        return self._orchestrator.status(analysis_id)

    def get_analysis(self, analysis_id: str) -> MarketAnalysis | None:
        return self._orchestrator.get_analysis(analysis_id)

    def enqueue(self, symbol: str, **params: Any) -> dict[str, Any]:
        """Queue analysis job."""
        job = self._scheduler.enqueue(symbol, **params)
        return job.to_dict()

    def run_queued(self) -> dict[str, Any] | None:
        """Run next queued job."""
        job = self._scheduler.run_next(self._orchestrator.run)
        return job.to_dict() if job else None

    def cache_stats(self) -> dict[str, Any]:
        return self._orchestrator._cache.stats()

    def invalidate_cache(self, stage: str | None = None) -> int:
        return self._orchestrator._cache.invalidate(stage)
