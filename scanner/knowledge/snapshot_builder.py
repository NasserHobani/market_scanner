# -*- coding: utf-8 -*-
"""Build knowledge snapshots from platform-native data — no new calculations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .feature_metadata import FeatureRegistry, FeatureValue
from .feature_snapshot import FeatureGroups, FeatureSnapshot
from .fingerprint import market_fingerprint
from .market_environment import MarketEnvironment
from .market_snapshot import MarketSnapshot, OHLCV
from .outcome_snapshot import OutcomeSnapshot
from .recommendation_snapshot import RecommendationSnapshot
from .schemas import OutcomeClass, TradeLifecycle
from .snapshot_envelope import (
    default_audit,
    quality_for_features,
    quality_for_market,
)
from .trade_snapshot import TradeSnapshot
from .versioning import SchemaMetadata


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def make_event_id(*, symbol: str, market: str, timeframe: str,
                  candle_time: datetime | Any) -> str:
    ts = _parse_ts(candle_time) or _utcnow()
    raw = json.dumps({
        "symbol": symbol, "market": market, "timeframe": timeframe,
        "candle_time": ts.isoformat(),
    }, sort_keys=True).encode("utf-8")
    return f"ke_{hashlib.sha256(raw).hexdigest()[:20]}"


def make_snapshot_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:20]}"


def _trend_label(htf: int | None, components: dict[str, int] | None) -> str:
    if htf == 1:
        return "bullish"
    if htf == -1:
        return "bearish"
    trend = (components or {}).get("trend")
    if trend == 1:
        return "bullish"
    if trend == -1:
        return "bearish"
    return "neutral"


def _infer_trend_state(mctx: dict[str, Any], *, htf: int | None = None) -> str:
    """Map existing regime/volatility text — no new calculations."""
    vol = str(mctx.get("volatility") or "").lower()
    if "مرتفع" in vol or "high" in vol:
        return "expansion"
    if "منخفض" in vol or "low" in vol:
        return "compression"
    score = mctx.get("regime_score")
    if score == 1 or htf == 1:
        return "trending"
    if score == -1 or htf == -1:
        return "trending"
    if score == 0:
        return "range"
    return ""


def build_feature_registry(source: dict[str, Any]) -> FeatureRegistry:
    """Build typed feature metadata from platform context and components."""
    components = dict(source.get("components") or {})
    ctx = dict(source.get("context") or source.get("score_context") or {})
    reg = FeatureRegistry()

    def _add(name: str, value: Any, *, module: str, notes: str = "") -> None:
        if value is None:
            return
        reg.add(FeatureValue(
            name=name,
            value=value,
            source="score_context" if name in ctx else "score_components",
            calculation_module=module,
            calculation_version="1.0",
            notes=notes,
        ))

    _add("rsi", ctx.get("rsi"), module="scanner.indicators.pine")
    _add("rvol", ctx.get("rvol"), module="scanner.indicators.volume")
    _add("atr_pct", ctx.get("atr_pct") or source.get("atr_pct"),
         module="scanner.indicators.pine")
    _add("delta", ctx.get("delta"), module="scanner.indicators.volume")
    _add("score", source.get("score"), module="scanner.scoring.engine")
    _add("htf_bias", source.get("htf"), module="scanner.indicators.htf")

    component_modules = {
        "trend": "scanner.scoring.engine",
        "rsi": "scanner.indicators.pine",
        "obv_macd": "scanner.indicators.volume",
        "vwap": "scanner.indicators.volume",
        "spike": "scanner.indicators.volume",
        "obv": "scanner.indicators.volume",
        "cmf": "scanner.indicators.volume",
        "mfi": "scanner.indicators.volume",
        "ad": "scanner.indicators.volume",
        "delta": "scanner.indicators.volume",
        "fib": "scanner.indicators.structure",
        "div": "scanner.indicators.structure",
    }
    for key, val in components.items():
        if val is None:
            continue
        reg.add(FeatureValue(
            name=f"c_{key}",
            value=int(val),
            source="score_components",
            calculation_module=component_modules.get(key, "scanner.scoring.engine"),
            calculation_version="1.0",
            notes="signed component -1/0/+1",
        ))
    return reg


def build_market_environment(source: dict[str, Any]) -> MarketEnvironment:
    """Build macro environment object from market_context."""
    symbol = source["symbol"]
    market = source["market"]
    timeframe = source["timeframe"]
    candle_time = (_parse_ts(source.get("candle_time") or source.get("timestamp"))
                   or _utcnow())
    event_id = source.get("event_id") or make_event_id(
        symbol=symbol, market=market, timeframe=timeframe, candle_time=candle_time)
    mctx = dict(source.get("market_context") or {})
    env_extra = dict(source.get("environment") or {})

    payload = {"market": market, "timeframe": timeframe, "timestamp": candle_time.isoformat()}
    environment_id = source.get("environment_id") or make_snapshot_id("me", payload)

    env = MarketEnvironment(
        environment_id=environment_id,
        event_id=event_id,
        market=market,
        timeframe=timeframe,
        timestamp=candle_time,
        market_regime=mctx.get("regime") or source.get("regime") or "",
        trend_state=_infer_trend_state(mctx, htf=source.get("htf")),
        volatility_class=mctx.get("volatility") or source.get("volatility") or "",
        liquidity_class=source.get("liquidity") or source.get("liquidity_class") or "unknown",
        trading_session=source.get("session") or env_extra.get("trading_session") or "",
        dominance=env_extra.get("dominance"),
        fear_greed=env_extra.get("fear_greed"),
        market_breadth=mctx.get("breadth_pct"),
        sector_strength=dict(env_extra.get("sector_strength") or {}),
        correlation_summary=dict(env_extra.get("correlation_summary") or {}),
        linked_market_snapshot_id=source.get("market_snapshot_id") or "",
        schema=SchemaMetadata(created_by=source.get("created_by") or "knowledge_builder"),
        audit=default_audit(
            creator=source.get("created_by") or "knowledge_builder",
            pipeline_stage="environment_capture",
        ),
        extensions=dict(env_extra.get("extensions") or {}),
    )
    env.quality = quality_for_market(env.to_dict())
    return env


def build_market_snapshot(source: dict[str, Any]) -> MarketSnapshot:
    """Map scan/score row + optional OHLCV and market context."""
    symbol = source["symbol"]
    market = source["market"]
    timeframe = source["timeframe"]
    candle_time = (_parse_ts(source.get("candle_time") or source.get("timestamp"))
                   or _utcnow())
    event_id = source.get("event_id") or make_event_id(
        symbol=symbol, market=market, timeframe=timeframe, candle_time=candle_time)

    ohlcv_raw = source.get("ohlcv") or {}
    ctx = source.get("context") or source.get("score_context") or {}
    mctx = source.get("market_context") or {}

    payload = {
        "symbol": symbol, "market": market, "timeframe": timeframe,
        "timestamp": candle_time.isoformat(),
    }
    snapshot_id = source.get("market_snapshot_id") or make_snapshot_id("ms", payload)

    snap = MarketSnapshot(
        snapshot_id=snapshot_id,
        event_id=event_id,
        symbol=symbol,
        exchange=source.get("exchange") or market,
        market=market,
        timeframe=timeframe,
        timestamp=candle_time,
        ohlcv=OHLCV(
            open=ohlcv_raw.get("open", source.get("open")),
            high=ohlcv_raw.get("high", source.get("high")),
            low=ohlcv_raw.get("low", source.get("low")),
            close=ohlcv_raw.get("close", source.get("close")),
            volume=ohlcv_raw.get("volume", source.get("volume")),
        ),
        session=source.get("session") or ctx.get("session") or "",
        regime=mctx.get("regime") or source.get("regime") or "",
        regime_score=mctx.get("regime_score", source.get("regime_score")),
        trend_direction=source.get("trend_direction") or _trend_label(
            source.get("htf"), source.get("components")),
        htf_bias=source.get("htf"),
        atr=source.get("atr") or ctx.get("atr"),
        atr_pct=source.get("atr_pct") or ctx.get("atr_pct"),
        liquidity_class=source.get("liquidity") or source.get("liquidity_class") or "unknown",
        quote_volume=source.get("quote_volume"),
        volatility=mctx.get("volatility") or source.get("volatility") or "",
        breadth_pct=mctx.get("breadth_pct"),
        linked_environment_id=source.get("environment_id") or "",
        extensions=dict(source.get("extensions") or {}),
        schema=SchemaMetadata(created_by=source.get("created_by") or "knowledge_builder"),
        audit=default_audit(
            creator=source.get("created_by") or "knowledge_builder",
            pipeline_stage="market_capture",
        ),
    )
    row = snap.to_dict()
    snap.fingerprint = market_fingerprint(row)
    snap.quality = quality_for_market(row)
    return snap


def _component_sign(components: dict[str, int], key: str) -> int | None:
    val = components.get(key)
    return int(val) if val is not None else None


def build_feature_snapshot(source: dict[str, Any]) -> FeatureSnapshot:
    """Map score components, context, and recommendation analysis."""
    symbol = source["symbol"]
    market = source["market"]
    timeframe = source["timeframe"]
    candle_time = (_parse_ts(source.get("candle_time") or source.get("timestamp"))
                   or _utcnow())
    event_id = source.get("event_id") or make_event_id(
        symbol=symbol, market=market, timeframe=timeframe, candle_time=candle_time)

    components = dict(source.get("components") or {})
    ctx = dict(source.get("context") or source.get("score_context") or {})
    reco = dict(source.get("recommendation") or source.get("reco") or {})
    analysis = dict(reco.get("analysis") or source.get("analysis") or {})
    pa = dict(analysis.get("price_action") or {})

    groups = FeatureGroups(
        trend={
            "htf_bias": source.get("htf"),
            "htf_text": ctx.get("htf_text"),
            "trend_component": _component_sign(components, "trend"),
            "price_action_trend": pa.get("trend"),
            "decision": source.get("decision"),
        },
        ema_alignment={
            "trend_signal": _component_sign(components, "trend"),
        },
        momentum={
            "rsi": ctx.get("rsi"),
            "rsi_signal": _component_sign(components, "rsi"),
            "obv_macd_signal": _component_sign(components, "obv_macd"),
            "delta": ctx.get("delta"),
            "delta_signal": _component_sign(components, "delta"),
        },
        volume={
            "rvol": ctx.get("rvol"),
            "spike_signal": _component_sign(components, "spike"),
            "obv_signal": _component_sign(components, "obv"),
            "cmf_signal": _component_sign(components, "cmf"),
            "mfi_signal": _component_sign(components, "mfi"),
            "ad_signal": _component_sign(components, "ad"),
            "vwap_signal": _component_sign(components, "vwap"),
        },
        market_structure={
            "events": pa.get("structure_events") or pa.get("events") or [],
            "hh_hl_lh_ll": pa.get("structure_events") or [],
            "bos": [e for e in (pa.get("structure_events") or [])
                    if str(e.get("kind", "")).lower() in ("bos", "break_of_structure")],
            "choch": [e for e in (pa.get("structure_events") or [])
                      if str(e.get("kind", "")).lower() in ("choch", "change_of_character")],
            "channel": analysis.get("channel"),
        },
        liquidity={
            "class": source.get("liquidity") or source.get("liquidity_class"),
            "quote_volume": source.get("quote_volume"),
            "sweeps": pa.get("sweeps") or [],
            "order_blocks": [z for z in (pa.get("zones") or [])
                             if z.get("kind") in ("demand", "supply")],
            "fvg": [z for z in (pa.get("zones") or [])
                    if str(z.get("kind", "")).startswith("fvg")],
        },
        patterns={
            "candlestick": analysis.get("candles") or [],
            "candle_score": analysis.get("candle_score"),
            "chart_patterns": analysis.get("chart_patterns") or [],
            "pattern_score": analysis.get("pattern_score"),
        },
        elliott=dict(analysis.get("elliott") or {}),
        support_resistance={
            "zones": pa.get("zones") or [],
            "equal_levels": pa.get("equal_levels") or [],
            "premium_discount": pa.get("premium_discount"),
            "fib_signal": _component_sign(components, "fib"),
            "divergence_signal": _component_sign(components, "div"),
        },
        confluence={
            "reasons": source.get("confluence") if isinstance(source.get("confluence"), list)
            else list(source.get("confluence_reasons") or []),
            "count": source.get("confluence_count") or source.get("confluence"),
            "breakdown": reco.get("breakdown") or [],
        },
        scoring={
            "score": source.get("score"),
            "ready": source.get("ready"),
            "blocker": source.get("blocker"),
        },
        extensions=dict(source.get("feature_extensions") or ctx),
    )

    factors = reco.get("factors")
    if not factors and reco.get("breakdown"):
        factors = [x.get("label") for x in reco["breakdown"]
                   if isinstance(x, dict) and (x.get("value") or 0) > 0]

    payload = {"event_id": event_id, "symbol": symbol, "candle_time": candle_time.isoformat()}
    snapshot_id = (source.get("feature_snapshot_id")
                   or make_snapshot_id("ks", payload))

    registry = build_feature_registry(source)
    feat = FeatureSnapshot(
        snapshot_id=snapshot_id,
        event_id=event_id,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        candle_time=candle_time,
        groups=groups,
        feature_registry=registry,
        raw_components=components,
        factor_labels=list(factors or []),
        final_grade=reco.get("grade") or source.get("grade") or "—",
        final_score=source.get("score"),
        linked_market_snapshot_id=source.get("market_snapshot_id") or "",
        schema=SchemaMetadata(created_by=source.get("created_by") or "knowledge_builder"),
        audit=default_audit(
            creator=source.get("created_by") or "knowledge_builder",
            pipeline_stage="feature_capture",
        ),
    )
    feat.quality = quality_for_features(feat.to_dict())
    return feat


def build_recommendation_snapshot(source: dict[str, Any]) -> RecommendationSnapshot:
    """Map recommendation dict at generation time."""
    reco = dict(source.get("recommendation") or source.get("reco") or source)
    symbol = source["symbol"]
    market = source["market"]
    timeframe = source["timeframe"]
    generated_at = (_parse_ts(source.get("generated_at") or source.get("candle_time")
                              or source.get("signal_at")) or _utcnow())
    event_id = source.get("event_id") or make_event_id(
        symbol=symbol, market=market, timeframe=timeframe, candle_time=generated_at)
    feature_id = source.get("feature_snapshot_id") or ""

    payload = {"event_id": event_id, "action": reco.get("action")}
    snapshot_id = source.get("recommendation_snapshot_id") or make_snapshot_id("kr", payload)

    analysis = reco.get("analysis") or {}
    analysis_summary = {
        "candle_count": len(analysis.get("candles") or []),
        "chart_pattern_count": len(analysis.get("chart_patterns") or []),
        "has_elliott": bool(analysis.get("elliott")),
        "price_action_trend": (analysis.get("price_action") or {}).get("trend"),
        "channel": analysis.get("channel"),
    }

    targets = list(reco.get("targets") or [])
    if not targets and source.get("target1"):
        targets = [source["target1"]]

    return RecommendationSnapshot(
        snapshot_id=snapshot_id,
        event_id=event_id,
        feature_snapshot_id=feature_id,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        direction=reco.get("side") or source.get("side") or "—",
        action=reco.get("action") or "none",
        entry=reco.get("entry"),
        stop=reco.get("stop"),
        targets=targets,
        risk_reward=reco.get("rr"),
        confidence=float(reco.get("confidence") or 0.0),
        grade=reco.get("grade") or "—",
        generated_at=generated_at,
        reasons=list(reco.get("reasons") or []),
        warnings=list(reco.get("warnings") or []),
        vetoes=list(reco.get("vetoes") or []),
        trigger=reco.get("trigger") or "",
        votes=float(reco.get("votes") or 0.0),
        breakdown=list(reco.get("breakdown") or []),
        headline=reco.get("headline") or "",
        invalidation=reco.get("invalidation"),
        valid_until=reco.get("valid_until") or "",
        size=dict(reco.get("size") or {}),
        analysis_summary=analysis_summary,
        schema=SchemaMetadata(created_by=source.get("created_by") or "knowledge_builder"),
        audit=default_audit(pipeline_stage="recommendation_capture"),
    )


def _lifecycle_from_status(status: str) -> str:
    if status in ("won", "lost"):
        return TradeLifecycle.CLOSED.value
    if status == "cancelled":
        return TradeLifecycle.CANCELLED.value
    if status == "open":
        return TradeLifecycle.RUNNING.value
    if status == "expired":
        return TradeLifecycle.EXPIRED.value
    return TradeLifecycle.PENDING.value


def build_trade_snapshot(source: dict[str, Any]) -> TradeSnapshot:
    """Map trade row at open, update, or close."""
    symbol = source["symbol"]
    market = source["market"]
    timeframe = source["timeframe"]
    signal_at = _parse_ts(source.get("signal_at"))
    opened_at = _parse_ts(source.get("opened_at"))
    closed_at = _parse_ts(source.get("closed_at"))
    candle_time = _parse_ts(source.get("candle_time")) or signal_at or _utcnow()
    event_id = source.get("event_id") or make_event_id(
        symbol=symbol, market=market, timeframe=timeframe, candle_time=candle_time)

    status = source.get("status") or "pending"
    duration = None
    if opened_at and closed_at:
        duration = (closed_at - opened_at).total_seconds()
    elif opened_at:
        duration = (_utcnow() - opened_at).total_seconds()

    current_r = source.get("r_multiple")
    if current_r is None:
        current_r = source.get("unrealized_r")

    payload = {"event_id": event_id, "trade_id": source.get("trade_id"), "status": status}
    snapshot_id = source.get("trade_snapshot_id") or make_snapshot_id("kt", payload)

    return TradeSnapshot(
        snapshot_id=snapshot_id,
        event_id=event_id,
        recommendation_snapshot_id=source.get("recommendation_snapshot_id") or "",
        feature_snapshot_id=source.get("feature_snapshot_id") or "",
        trade_id=source.get("trade_id") or source.get("id"),
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        side=source.get("side") or "buy",
        source=source.get("source") or "auto",
        status=status,
        lifecycle=_lifecycle_from_status(status),
        planned_entry=source.get("entry") or source.get("planned_entry"),
        planned_stop=source.get("stop") or source.get("planned_stop"),
        planned_target=source.get("target1") or source.get("planned_target"),
        planned_rr=source.get("rr") or source.get("planned_rr"),
        entry_price=source.get("entry_price"),
        exit_price=source.get("exit_price"),
        current_r=current_r,
        unrealized_r=source.get("unrealized_r"),
        grade=source.get("grade") or "—",
        score=source.get("score"),
        confidence=float(source.get("confidence") or 0.0),
        factors=list(source.get("factors") or []),
        signal_at=signal_at,
        candle_time=candle_time,
        opened_at=opened_at,
        closed_at=closed_at,
        duration_seconds=duration,
        bars_held=int(source.get("bars_held") or 0),
        resolution_note=source.get("resolution_note") or "",
        extensions=dict(source.get("extensions") or {}),
        schema=SchemaMetadata(created_by=source.get("created_by") or "knowledge_builder"),
        audit=default_audit(pipeline_stage="trade_capture"),
    )


def _outcome_class(status: str, r_multiple: float | None) -> str:
    if status == "won" or (r_multiple is not None and r_multiple > 0):
        return OutcomeClass.WINNER.value
    if status == "lost" or (r_multiple is not None and r_multiple < 0):
        return OutcomeClass.LOSER.value
    if r_multiple is not None and r_multiple == 0:
        return OutcomeClass.BREAK_EVEN.value
    return OutcomeClass.UNKNOWN.value


def build_outcome_snapshot(source: dict[str, Any]) -> OutcomeSnapshot:
    """Map closed trade / resolution data."""
    symbol = source["symbol"]
    market = source["market"]
    timeframe = source["timeframe"]
    closed_at = _parse_ts(source.get("closed_at")) or _utcnow()
    event_id = source.get("event_id") or make_event_id(
        symbol=symbol, market=market, timeframe=timeframe,
        candle_time=_parse_ts(source.get("candle_time")) or closed_at)

    status = source.get("status") or ""
    r_multiple = source.get("r_multiple")
    oc = _outcome_class(status, r_multiple)

    opened_at = _parse_ts(source.get("opened_at"))
    holding = None
    if opened_at and closed_at:
        holding = (closed_at - opened_at).total_seconds()

    excursion = source.get("excursion") or {}
    mfe = source.get("best_r") or excursion.get("best_r")
    mae = source.get("worst_r") or excursion.get("worst_r")

    payload = {"event_id": event_id, "trade_id": source.get("trade_id"), "status": status}
    snapshot_id = source.get("outcome_snapshot_id") or make_snapshot_id("ko", payload)

    return OutcomeSnapshot(
        snapshot_id=snapshot_id,
        event_id=event_id,
        trade_snapshot_id=source.get("trade_snapshot_id") or "",
        trade_id=source.get("trade_id") or source.get("id"),
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        outcome_class=oc,
        status=status,
        profit=oc == OutcomeClass.WINNER.value,
        loss=oc == OutcomeClass.LOSER.value,
        break_even=oc == OutcomeClass.BREAK_EVEN.value,
        r_multiple=r_multiple,
        mfe_r=mfe,
        mae_r=mae,
        holding_time_seconds=holding,
        bars_held=int(source.get("bars_held") or 0),
        exit_reason=source.get("resolution_note") or source.get("exit_reason") or "",
        entry_price=source.get("entry_price"),
        exit_price=source.get("exit_price"),
        fees=source.get("fees"),
        slippage=source.get("slippage"),
        closed_at=closed_at,
        extensions=dict(source.get("extensions") or {}),
        schema=SchemaMetadata(created_by=source.get("created_by") or "knowledge_builder"),
        audit=default_audit(pipeline_stage="outcome_capture"),
    )


class SnapshotBuilder:
    """Concrete SnapshotProvider — maps platform dicts to snapshot models."""

    def build_environment(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_market_environment(source).to_dict()

    def build_market(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_market_snapshot(source).to_dict()

    def build_features(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_feature_snapshot(source).to_dict()

    def build_recommendation(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_recommendation_snapshot(source).to_dict()

    def build_trade(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_trade_snapshot(source).to_dict()

    def build_outcome(self, source: dict[str, Any]) -> dict[str, Any]:
        return build_outcome_snapshot(source).to_dict()
