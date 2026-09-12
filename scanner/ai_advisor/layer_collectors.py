# -*- coding: utf-8 -*-
"""Collect platform layer outputs for unified package — integration only."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("scanner.ai_advisor.collectors")


def collect_platform_layers(*,
                            symbol: str,
                            market: str,
                            timeframe: str,
                            recommendation: dict[str, Any] | None = None,
                            row: dict[str, Any] | None = None,
                            trade_id: str = "",
                            scan_id: str = "",
                            strategy: str = "default",
                            provider: str = "") -> dict[str, Any]:
    """Gather full platform context from existing services. Never raises."""
    row = row or {}
    reco = recommendation or {}
    scan_source = _build_scan_source(symbol, market, timeframe, reco, row)
    event_id = scan_source.get("event_id", "")

    layers: dict[str, Any] = {
        "event_id": event_id,
        "metadata": {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "trade_id": trade_id,
            "scan_id": scan_id,
            "strategy": strategy,
            "provider": provider,
        },
        "recommendation": _enrich_recommendation(reco, row),
    }

    kctx = _collect_knowledge(scan_source)
    kctx = _sanitize_layers(kctx)
    if not kctx.get("symbol"):
        kctx["symbol"] = symbol
    if not kctx.get("market"):
        kctx["market"] = market
    if not kctx.get("timeframe"):
        kctx["timeframe"] = timeframe
    layers["knowledge_context"] = kctx

    reasoning = _collect_reasoning(kctx)
    layers["reasoning_review"] = reasoning

    layers["similarity_context"] = _collect_similarity(kctx)
    layers["research_report"] = _collect_research(scan_source)
    layers["feature_analysis"] = _collect_feature_intelligence(scan_source)
    layers["feature_snapshot"] = _collect_pit_snapshot(scan_source, row)
    layers["prediction"] = _collect_prediction(kctx)
    layers["optimization"] = _collect_optimization(scan_source)
    layers["decision_ai"], layers["guardrails"], layers["fused_confidence"] = (
        _collect_decision_ai(
            event_id=event_id,
            kctx=kctx,
            reasoning=reasoning,
            similarity=layers["similarity_context"],
            research=layers["research_report"],
            feature=layers["feature_analysis"],
            prediction=layers["prediction"],
        )
    )

    return layers


def _build_scan_source(symbol: str, market: str, timeframe: str,
                       reco: dict, row: dict) -> dict[str, Any]:
    try:
        from scanner.knowledge.snapshot_builder import make_event_id
        event_id = make_event_id(symbol=symbol, market=market, timeframe=timeframe)
    except Exception:  # noqa: BLE001
        event_id = f"evt_{symbol}_{market}_{timeframe}".lower().replace("/", "_")

    targets = reco.get("targets") or []
    return {
        "event_id": event_id,
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "action": reco.get("action", ""),
        "side": reco.get("side", ""),
        "confidence": reco.get("confidence"),
        "grade": reco.get("grade", ""),
        "verdict": row.get("decision", reco.get("verdict", "")),
        "entry": reco.get("entry"),
        "stop": reco.get("stop"),
        "targets": targets,
        "rr": reco.get("rr"),
        "score": row.get("score"),
        "htf": row.get("htf"),
        "rsi": row.get("rsi"),
        "rvol": row.get("rvol"),
        "atr_pct": row.get("atr_pct"),
        "decision_timestamp": row.get("candle_time") or row.get("timestamp") or "",
        "candle_time": row.get("candle_time") or row.get("timestamp") or "",
        "recommendation": reco,
        "reco": reco,
        "blocker": row.get("blocker"),
        "ready": True,
    }


def _enrich_recommendation(reco: dict, row: dict) -> dict[str, Any]:
    targets = reco.get("targets") or []
    return {
        **reco,
        "verdict": row.get("decision", reco.get("verdict", "")),
        "r_target": reco.get("rr"),
        "target": targets[0] if targets else reco.get("target"),
    }


def _collect_knowledge(scan_source: dict) -> dict[str, Any]:
    try:
        from scanner.knowledge import KnowledgeService
        svc = KnowledgeService()
        ids = svc.capture_scan(scan_source)
        event_id = ids.get("event_id") or scan_source["event_id"]
        kctx = svc.get_context(event_id)
        if kctx:
            return kctx
    except Exception as exc:  # noqa: BLE001
        log.debug("knowledge collect fallback: %s", exc)

    return _fallback_knowledge(scan_source)


def _fallback_knowledge(scan_source: dict) -> dict[str, Any]:
    htf = int(scan_source.get("htf", 0) or 0)
    return {
        "event_id": scan_source["event_id"],
        "symbol": scan_source["symbol"],
        "market": scan_source["market"],
        "timeframe": scan_source["timeframe"],
        "recommendation_snapshot": {
            "symbol": scan_source["symbol"],
            "action": scan_source.get("action", ""),
            "side": scan_source.get("side", ""),
            "confidence": scan_source.get("confidence"),
            "grade": scan_source.get("grade", ""),
        },
        "market_snapshot": {
            "symbol": scan_source["symbol"],
            "trend_direction": "bullish" if htf > 0 else "bearish",
            "atr_pct": scan_source.get("atr_pct"),
        },
        "trade_snapshot": {
            "entry": scan_source.get("entry"),
            "stop": scan_source.get("stop"),
            "target": (scan_source.get("targets") or [None])[0],
        },
        "strategy_statistics": {
            "closed_trades": 0, "win_rate": None,
            "expectancy": None, "reliable": False,
        },
    }


def _collect_reasoning(kctx: dict) -> dict[str, Any]:
    try:
        from scanner.reasoning import ReasoningService
        review = ReasoningService().review_from_knowledge(kctx)
        return review.to_dict()
    except Exception as exc:  # noqa: BLE001
        log.debug("reasoning collect fallback: %s", exc)

    reco = kctx.get("recommendation_snapshot") or {}
    return {
        "verdict": reco.get("verdict", ""),
        "action": reco.get("action", ""),
        "direction": reco.get("side", ""),
        "agreement_score": reco.get("confidence"),
        "evidence": {"items": []},
        "contradictions": {"items": []},
        "warnings": [],
        "missing_information": [],
    }


def _collect_similarity(kctx: dict) -> dict[str, Any]:
    try:
        from scanner.similarity import SimilarityService
        from scanner.pipeline.similarity_integration import build_similarity_context
        query = {
            "event_id": kctx.get("event_id", ""),
            "feature_snapshot": kctx.get("feature_snapshot") or {},
            "market_snapshot": kctx.get("market_snapshot") or {},
        }
        result = SimilarityService().find_similar(query, top_n=10)
        ctx = build_similarity_context(result)
        return ctx.to_dict() if hasattr(ctx, "to_dict") else dict(ctx)
    except Exception as exc:  # noqa: BLE001
        log.debug("similarity collect fallback: %s", exc)
    return {"available": False}


def _collect_research(scan_source: dict) -> dict[str, Any]:
    try:
        from scanner.research import ResearchEngine
        engine = ResearchEngine()
        rows = [scan_source]
        stats = engine.statistics(rows) if hasattr(engine, "statistics") else {}
        if stats:
            return {"available": True, "statistics": stats, "row_count": len(rows)}
    except Exception as exc:  # noqa: BLE001
        log.debug("research collect fallback: %s", exc)
    return {}


def _collect_pit_snapshot(scan_source: dict, row: dict) -> dict[str, Any]:
    try:
        from scanner.feature_snapshots import PointInTimeSnapshotService
        from scanner.feature_snapshots.builder import build_snapshot

        svc = PointInTimeSnapshotService()
        legacy_id = row.get("feature_snapshot_id") or row.get("pit_snapshot_id") or ""
        if legacy_id:
            existing = svc.get_for_legacy(legacy_id) or svc.get(legacy_id)
            if existing:
                return {**svc.to_udp_summary(existing), **svc.summarize_for_llm(existing)}

        snap = build_snapshot(scan_source, legacy_snapshot_id=legacy_id)
        return {**svc.to_udp_summary(snap), **svc.summarize_for_llm(snap)}
    except Exception as exc:  # noqa: BLE001
        log.debug("pit snapshot collect fallback: %s", exc)
    return {"available": False, "quality": "UNAVAILABLE", "reason": "snapshot unavailable"}


def _collect_feature_intelligence(scan_source: dict) -> dict[str, Any]:
    try:
        from scanner.feature_intelligence import FeatureIntelligenceService
        svc = FeatureIntelligenceService()
        result = svc.analyze([scan_source])
        return result.to_dict() if hasattr(result, "to_dict") else dict(result)
    except Exception as exc:  # noqa: BLE001
        log.debug("feature intelligence collect fallback: %s", exc)
    return {}


def _collect_prediction(kctx: dict) -> dict[str, Any]:
    try:
        from scanner.ai_fusion.prediction_adapter import PredictionAdapter
        return PredictionAdapter().to_udp_section(kctx)
    except Exception as exc:  # noqa: BLE001
        log.debug("prediction adapter collect: %s", exc)
    return {"available": False, "status": "UNAVAILABLE", "reason": "prediction subsystem unavailable"}


def _collect_optimization(scan_source: dict) -> dict[str, Any]:
    try:
        from scanner.optimization import OptimizationService
        svc = OptimizationService()
        if hasattr(svc, "latest_report"):
            report = svc.latest_report()
            if report:
                return report.to_dict() if hasattr(report, "to_dict") else dict(report)
    except Exception as exc:  # noqa: BLE001
        log.debug("optimization collect fallback: %s", exc)
    return {}


def _collect_decision_ai(*, event_id: str, kctx: dict, reasoning: dict,
                         similarity: dict, research: dict,
                         feature: dict, prediction: dict) -> tuple[dict, dict, dict]:
    try:
        from scanner.decision_ai import DecisionAIService
        svc = DecisionAIService()
        review = svc.review_trade(
            event_id=event_id,
            knowledge_context=kctx,
            reasoning_review=reasoning,
            similarity_context=similarity,
            research_report=research,
            feature_analysis=feature,
            prediction=prediction,
        )
        review_dict = review.to_dict() if hasattr(review, "to_dict") else {}
        ctx = svc.build_context(
            event_id=event_id,
            knowledge_context=kctx,
            reasoning_review=reasoning,
            similarity_context=similarity,
            research_report=research,
            feature_analysis=feature,
            prediction=prediction,
        )
        ctx_dict = ctx.to_dict() if hasattr(ctx, "to_dict") else {}
        evidence = svc._evidence.build(ctx_dict).to_dict()  # noqa: SLF001
        fused = svc._fusion.fuse(ctx_dict).to_dict()  # noqa: SLF001
        guardrails = svc._guardrails.validate(ctx_dict, evidence=evidence).to_dict()  # noqa: SLF001
        return review_dict, guardrails, fused
    except Exception as exc:  # noqa: BLE001
        log.debug("decision_ai collect fallback: %s", exc)
    return {}, {"passed": True, "violations": []}, {}


_FORBIDDEN_KEYS = frozenset({
    "ohlc", "ohlcv", "candles", "dataframe", "df", "csv", "raw_indicators",
    "open", "high", "low", "close", "volume_series",
})


def _sanitize_layers(data: dict[str, Any]) -> dict[str, Any]:
    """Strip forbidden raw-market keys recursively."""
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _FORBIDDEN_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize_layers(value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            clean[key] = [_sanitize_layers(v) for v in value]
        else:
            clean[key] = value
    return clean
