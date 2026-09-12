# -*- coding: utf-8 -*-
"""Knowledge service — orchestrates snapshot building and persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .context_builder import ContextBuilder
from .memory import KnowledgeMemory
from .relationships import build_explicit_relationships, build_graph_from_history
from .repository import KnowledgeRepository
from .schemas import KnowledgeRecord, SnapshotKind, StrategyStatistics
from .snapshot_builder import (
    SnapshotBuilder,
    build_feature_snapshot,
    build_market_environment,
    build_market_snapshot,
    build_outcome_snapshot,
    build_recommendation_snapshot,
    build_trade_snapshot,
    make_event_id,
)


class KnowledgeService:
    """High-level API for capturing and retrieving platform knowledge."""

    def __init__(self, *,
                 repository: KnowledgeRepository | None = None,
                 builder: SnapshotBuilder | None = None,
                 context_builder: ContextBuilder | None = None) -> None:
        self.repository = repository or KnowledgeRepository()
        self.builder = builder or SnapshotBuilder()
        self.context_builder = context_builder or ContextBuilder(self.repository)

    def _persist(self, kind: SnapshotKind, event_id: str,
                 payload: dict[str, Any]) -> str:
        return self.repository.save_snapshot(
            kind=kind, event_id=event_id, payload=payload)

    def _persist_relationships(self, event_id: str, ids: dict[str, str]) -> list[str]:
        record_ids: list[str] = []
        for edge in build_explicit_relationships(event_id, ids):
            rid = self._persist(SnapshotKind.RELATIONSHIP, event_id, edge.to_dict())
            record_ids.append(rid)
        return record_ids

    def capture_scan(self, source: dict[str, Any]) -> dict[str, str]:
        """Capture environment + market + feature + recommendation snapshots."""
        symbol = source["symbol"]
        market = source["market"]
        timeframe = source["timeframe"]
        candle_time = source.get("candle_time") or source.get("timestamp")
        event_id = source.get("event_id") or make_event_id(
            symbol=symbol, market=market, timeframe=timeframe,
            candle_time=candle_time or datetime.now(timezone.utc))

        source = {**source, "event_id": event_id}
        env = build_market_environment(source)
        source = {**source, "environment_id": env.environment_id}

        mkt = build_market_snapshot(source)
        mkt.linked_environment_id = env.environment_id
        source = {**source, "market_snapshot_id": mkt.snapshot_id}

        features = build_feature_snapshot(source)
        source = {**source, "feature_snapshot_id": features.snapshot_id}

        reco = build_recommendation_snapshot(source)

        ids: dict[str, str] = {
            "event_id": event_id,
            "environment_id": env.environment_id,
            "market_snapshot_id": mkt.snapshot_id,
            "feature_snapshot_id": features.snapshot_id,
            "recommendation_snapshot_id": reco.snapshot_id,
        }
        ids["environment_record_id"] = self._persist(
            SnapshotKind.ENVIRONMENT, event_id, env.to_dict())
        ids["market_snapshot_record_id"] = self._persist(
            SnapshotKind.MARKET, event_id, mkt.to_dict())
        ids["feature_snapshot_record_id"] = self._persist(
            SnapshotKind.FEATURE, event_id, features.to_dict())
        ids["recommendation_snapshot_record_id"] = self._persist(
            SnapshotKind.RECOMMENDATION, event_id, reco.to_dict())
        ids["relationship_record_ids"] = self._persist_relationships(event_id, ids)
        return ids

    def capture_trade(self, source: dict[str, Any]) -> str:
        trade = build_trade_snapshot(source)
        record_id = self._persist(SnapshotKind.TRADE, trade.event_id, trade.to_dict())
        if source.get("recommendation_snapshot_id") and trade.snapshot_id:
            self._persist_relationships(trade.event_id, {
                "recommendation_snapshot_id": source.get("recommendation_snapshot_id"),
                "trade_snapshot_id": trade.snapshot_id,
            })
        return record_id

    def capture_outcome(self, source: dict[str, Any]) -> str:
        outcome = build_outcome_snapshot(source)
        record_id = self._persist(SnapshotKind.OUTCOME, outcome.event_id, outcome.to_dict())
        if source.get("trade_snapshot_id") and outcome.snapshot_id:
            self._persist_relationships(outcome.event_id, {
                "trade_snapshot_id": source.get("trade_snapshot_id"),
                "outcome_snapshot_id": outcome.snapshot_id,
            })
        return record_id

    def capture_lifecycle(self, *,
                          scan_source: dict[str, Any],
                          trade_source: dict[str, Any] | None = None,
                          outcome_source: dict[str, Any] | None = None,
                          ) -> dict[str, Any]:
        """Capture full event chain when data is available."""
        ids = self.capture_scan(scan_source)
        event_id = ids["event_id"]
        result: dict[str, Any] = {"event_id": event_id, **ids}

        if trade_source:
            trade = build_trade_snapshot({
                **trade_source, "event_id": event_id,
                "feature_snapshot_id": ids.get("feature_snapshot_id"),
                "recommendation_snapshot_id": ids.get("recommendation_snapshot_id"),
            })
            trade_source = {**trade_source, "trade_snapshot_id": trade.snapshot_id}
            result["trade_record_id"] = self.capture_trade(trade_source)
            result["trade_snapshot_id"] = trade.snapshot_id

        if outcome_source:
            outcome_source = {**outcome_source, "event_id": event_id,
                              "trade_snapshot_id": result.get("trade_snapshot_id")}
            result["outcome_record_id"] = self.capture_outcome(outcome_source)

        result["graph"] = self.get_graph(event_id).to_dict()
        return result

    def get_graph(self, event_id: str):
        return build_graph_from_history(event_id, self.repository.history(event_id))

    def get_memory(self, event_id: str) -> KnowledgeMemory:
        """Return memory scaffold — summaries filled by AI in future sprints."""
        return KnowledgeMemory(event_id=event_id)

    def get_context(self, event_id: str, *,
                    strategy_stats: StrategyStatistics | None = None,
                    recent_performance: dict[str, Any] | None = None,
                    ) -> dict[str, Any]:
        return self.context_builder.build_context(
            event_id,
            strategy_stats=strategy_stats,
            recent_performance=recent_performance,
        )

    def strategy_stats_from_rows(self, rows: list[dict]) -> StrategyStatistics:
        """Build strategy statistics from tracking rows — uses existing summarize."""
        from scanner.tracking import summarize

        s = summarize(rows)
        closed = [r for r in rows if r.get("status") in ("won", "lost")]
        recent = closed[-30:]
        recent_rs = [float(r["r_multiple"]) for r in recent
                     if r.get("r_multiple") is not None]
        recent_exp = (sum(recent_rs) / len(recent_rs)) if recent_rs else None
        return StrategyStatistics(
            closed_trades=s.get("closed") or 0,
            win_rate=s.get("win_rate"),
            expectancy=s.get("expectancy"),
            profit_factor=s.get("profit_factor"),
            max_drawdown_r=s.get("max_drawdown_r"),
            sharpe=s.get("sharpe"),
            recent_expectancy_30=round(recent_exp, 3) if recent_exp is not None else None,
            reliable=bool(s.get("reliable")),
        )

    @staticmethod
    def event_id_for(symbol: str, market: str, timeframe: str,
                     candle_time: datetime) -> str:
        return make_event_id(symbol=symbol, market=market, timeframe=timeframe,
                             candle_time=candle_time)
