# -*- coding: utf-8 -*-
"""Runtime snapshot enrichment — record existing platform outputs at decision time."""
from __future__ import annotations

import logging
import time
from typing import Any

from scanner.scoring.engine import ScoreResult

from .builder import V3_FEATURE_SPECS, extract_v3_features

log = logging.getLogger("scanner.feature_snapshots.enrichment")

FEATURE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "trend": (
        "trend_direction", "trend_strength", "higher_timeframe_trend", "multi_timeframe_alignment",
    ),
    "momentum": ("rsi", "momentum_state", "divergence", "momentum_strength"),
    "volatility": ("atr_pct", "atr_percentile", "volatility_regime"),
    "volume": ("rvol", "volume_participation", "volume_trend"),
    "structure": (
        "bos_count", "choch_count", "structure_direction", "support_distance", "resistance_distance",
    ),
    "similarity": (
        "match_count", "similarity_score", "historical_win_rate", "historical_expectancy",
    ),
    "knowledge": (
        "knowledge_score", "detected_pattern_count", "regime", "knowledge_confidence",
    ),
    "research": ("research_signal", "research_confidence", "research_sample_size"),
    "platform": (
        "score", "confidence", "grade_enc", "risk_reward", "expected_r", "side_buy",
    ),
}


def missing_by_category(missing_features: list[str]) -> dict[str, int]:
    missing_set = set(missing_features)
    return {
        cat: sum(1 for name in names if name in missing_set)
        for cat, names in FEATURE_CATEGORIES.items()
    }


def row_to_components(row: dict[str, Any]) -> dict[str, int]:
    comps: dict[str, int] = {}
    for key, val in row.items():
        if not str(key).startswith("c_"):
            continue
        try:
            comps[str(key)[2:]] = int(val)
        except (TypeError, ValueError):
            continue
    return comps


def normalize_structure(analysis: dict[str, Any], *, close: float | None = None) -> dict[str, Any]:
    """Map recommendation price_action to V3 structure fields — no new indicators."""
    pa = dict(analysis.get("price_action") or {})
    if not pa:
        return {}
    events = pa.get("events") or pa.get("structure_events") or []
    bos = sum(1 for e in events if "BOS" in str(e.get("kind", "")))
    choch = sum(1 for e in events if "CHoCH" in str(e.get("kind", "")).upper()
                or "CHOCH" in str(e.get("kind", "")).upper())
    trend = str(pa.get("trend") or "")
    struct_dir: str | None = None
    if trend in ("صاعد", "bullish", "up"):
        struct_dir = "bullish"
    elif trend in ("هابط", "bearish", "down"):
        struct_dir = "bearish"

    support_dist = resistance_dist = None
    if close is not None:
        for zone in pa.get("zones") or []:
            if not isinstance(zone, dict):
                continue
            kind = zone.get("kind", "")
            if kind == "demand" and support_dist is None:
                support_dist = abs(float(close) - float(zone.get("top", close)))
            if kind == "supply" and resistance_dist is None:
                resistance_dist = abs(float(zone.get("bottom", close)) - float(close))

    out: dict[str, Any] = {
        "bos_count": bos,
        "choch_count": choch,
        "structure_analyzed": True,
    }
    if struct_dir:
        out["structure_direction"] = struct_dir
    if support_dist is not None:
        out["support_distance"] = support_dist
    if resistance_dist is not None:
        out["resistance_distance"] = resistance_dist
    if pa.get("score") is not None:
        out["structure_confidence"] = pa.get("score")
    return out


def build_source_from_score_result(sr: ScoreResult, *, market: str) -> dict[str, Any]:
    """Flatten ScoreResult into snapshot source — preserves engine outputs."""
    reco = dict(sr.recommendation or {})
    analysis = dict(reco.get("analysis") or {})
    decision_ts = str(sr.timestamp.isoformat() if hasattr(sr.timestamp, "isoformat") else sr.timestamp)
    ctx = dict(sr.context or {})
    structure = normalize_structure(analysis, close=sr.close)

    factor_flags = [k for k, v in (sr.components or {}).items() if v]
    return {
        "symbol": sr.symbol,
        "market": market,
        "timeframe": sr.timeframe,
        "decision_timestamp": decision_ts,
        "feature_timestamp": decision_ts,
        "candle_time": decision_ts,
        "close": sr.close,
        "score": sr.score,
        "htf": sr.htf,
        "components": dict(sr.components or {}),
        "context": ctx,
        "score_context": ctx,
        "confluence": list(sr.confluence or []),
        "factor_count": len(factor_flags),
        "factor_flags": factor_flags,
        "recommendation": reco,
        "reco": reco,
        "analysis": analysis,
        "rsi": ctx.get("rsi"),
        "rvol": ctx.get("rvol"),
        "atr_pct": ctx.get("atr_pct"),
        "atr_percentile": ctx.get("atr_percentile"),
        "structure": structure,
        "breakdown": reco.get("breakdown") or [],
        "votes": reco.get("votes"),
    }


def build_source_from_row(*, symbol: str, market: str, timeframe: str,
                          row: dict[str, Any], reco: dict[str, Any] | None,
                          candle_time: str) -> dict[str, Any]:
    """Fallback when ScoreResult is unavailable — use flattened scan row."""
    reco = dict(reco or {})
    analysis = dict(reco.get("analysis") or {})
    components = row_to_components(row)
    if not components:
        components = dict(row.get("components") or {})
    ctx = {
        "rsi": row.get("rsi"),
        "rvol": row.get("rvol"),
        "atr_pct": row.get("atr_pct"),
        "atr_percentile": row.get("atr_percentile"),
        "delta": row.get("delta"),
        "channel": row.get("channel"),
        "ch_zone": row.get("ch_zone"),
        "htf_text": row.get("htf_text"),
    }
    structure = normalize_structure(analysis, close=row.get("close"))
    return {
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "decision_timestamp": candle_time,
        "feature_timestamp": candle_time,
        "candle_time": candle_time,
        "close": row.get("close"),
        "score": row.get("score"),
        "htf": row.get("htf"),
        "components": components,
        "context": ctx,
        "recommendation": reco,
        "reco": reco,
        "analysis": analysis,
        "rsi": row.get("rsi"),
        "rvol": row.get("rvol"),
        "atr_pct": row.get("atr_pct"),
        "structure": structure,
        "breakdown": reco.get("breakdown") or [],
    }


def _collect_knowledge(scan_source: dict[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        from scanner.ai_advisor.layer_collectors import _collect_knowledge, _sanitize_layers
        kctx = _sanitize_layers(_collect_knowledge(scan_source))
        # AIA-11: expose confidence from existing reco snapshot — no new scorer
        if kctx and kctx.get("knowledge_confidence") is None:
            reco_snap = kctx.get("recommendation_snapshot") or {}
            conf = reco_snap.get("confidence")
            if conf is None:
                conf = (scan_source.get("recommendation") or {}).get("confidence")
            if conf is not None:
                kctx["knowledge_confidence"] = conf
        return kctx, ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"knowledge_collection_failed:{str(exc)[:80]}"


def _collect_similarity(kctx: dict[str, Any], decision_ts: str) -> tuple[dict[str, Any], str]:
    try:
        from scanner.ai_advisor.layer_collectors import _collect_similarity
        sim = _collect_similarity(kctx)
        if not sim:
            return {"similarity_status": "unavailable"}, "missing_similarity"
        stats = sim.get("similarity_statistics") or {}
        result = sim.get("similarity_result") or {}
        inner = result.get("statistics") or {}
        match_count = sim.get("match_count") or len(result.get("matches") or [])
        if match_count <= 0 and not stats and not inner:
            return {"similarity_status": "unavailable"}, "missing_similarity"
        return {
            "match_count": match_count,
            "average_similarity": sim.get("average_similarity") or inner.get("avg_similarity"),
            "average_win_rate": sim.get("average_win_rate") or inner.get("win_rate"),
            "average_r": sim.get("average_r") or inner.get("avg_r"),
            "confidence": inner.get("confidence") or stats.get("confidence"),
            "sample_size": inner.get("sample_size") or stats.get("sample_size"),
            "similarity_dataset_timestamp": decision_ts,
            "similarity_status": "available",
        }, ""
    except Exception as exc:  # noqa: BLE001
        return {"similarity_status": "unavailable"}, f"similarity_collection_failed:{str(exc)[:80]}"


def collect_validated_research(decision_ts: str) -> tuple[dict[str, Any], str]:
    """Only validated completed experiments with ended_at <= decision_ts."""
    try:
        from scanner.research.experiment import ExperimentStatus, ExperimentStore
        store = ExperimentStore()
        for exp in store.history(limit=100):
            if exp.status != ExperimentStatus.COMPLETED.value:
                continue
            ended = str(exp.ended_at or exp.started_at or "")
            if ended and decision_ts and ended > decision_ts:
                continue
            report = (exp.results or {}).get("report") or {}
            metrics = report.get("metrics") or {}
            hypothesis = exp.hypothesis or {}
            validation = str(hypothesis.get("validation_status") or "").upper()
            significant = bool(metrics.get("significant"))
            if validation not in ("VALIDATED", "APPROVED") and not significant:
                continue
            sample = metrics.get("sample_size") or (exp.dataset or {}).get("row_count")
            return {
                "available": True,
                "research_id": exp.experiment_id,
                "validation_status": validation or ("VALIDATED" if significant else ""),
                "created_at": ended,
                "statistics": metrics,
                "confidence": metrics.get("confidence"),
                "row_count": sample,
                "significant": significant,
            }, ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"research_collection_failed:{str(exc)[:80]}"
    return {}, "missing_research"


def enrich_snapshot_source(
    base_source: dict[str, Any],
    *,
    score_result: ScoreResult | None = None,
    market: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attach knowledge, similarity, research, and coverage metadata."""
    t0 = time.perf_counter()
    meta: dict[str, Any] = {
        "collector_failures": [],
        "collection_latency_ms": 0.0,
    }
    decision_ts = str(base_source.get("decision_timestamp") or base_source.get("candle_time") or "")

    if score_result is not None:
        source = build_source_from_score_result(score_result, market=market or base_source.get("market", ""))
        source.update({k: v for k, v in base_source.items() if k not in source or source.get(k) in (None, "", {})})
    else:
        source = dict(base_source)

    # Baseline coverage (pre platform-layer collection)
    feats_before, _ = extract_v3_features(source, decision_ts=decision_ts)
    meta["coverage_before"] = round(len(feats_before) / len(V3_FEATURE_SPECS), 4)
    meta["features_before"] = len(feats_before)

    try:
        from scanner.ai_advisor.layer_collectors import _build_scan_source
        scan_source = _build_scan_source(
            source.get("symbol", ""),
            source.get("market", market),
            source.get("timeframe", ""),
            source.get("recommendation") or source.get("reco") or {},
            {
                **source,
                "timestamp": decision_ts,
                "candle_time": decision_ts,
                "decision": source.get("decision"),
            },
        )
        scan_source.update({
            "components": source.get("components") or {},
            "context": source.get("context") or {},
            "score": source.get("score"),
            "htf": source.get("htf"),
            "candle_time": decision_ts,
            "analysis": source.get("analysis") or {},
        })
        source["event_id"] = scan_source.get("event_id", "")
    except Exception as exc:  # noqa: BLE001
        scan_source = dict(source)
        meta["collector_failures"].append(f"scan_source_failed:{str(exc)[:60]}")

    try:
        kctx, kerr = _collect_knowledge(scan_source)
    except Exception as exc:  # noqa: BLE001
        kctx, kerr = {}, f"knowledge_collection_failed:{str(exc)[:80]}"
    if kerr:
        meta["collector_failures"].append(kerr)

    try:
        sim, serr = _collect_similarity(kctx, decision_ts)
    except Exception as exc:  # noqa: BLE001
        sim, serr = {"similarity_status": "unavailable"}, f"similarity_collection_failed:{str(exc)[:80]}"
    if serr:
        meta["collector_failures"].append(serr)

    try:
        research, rerr = collect_validated_research(decision_ts)
    except Exception as exc:  # noqa: BLE001
        research, rerr = {}, f"research_collection_failed:{str(exc)[:80]}"
    if rerr and not research:
        meta["collector_failures"].append(rerr)

    source["knowledge_context"] = kctx
    source["enriched_similarity"] = sim
    source["enriched_research"] = research

    feats_after, _ = extract_v3_features(
        source,
        decision_ts=decision_ts,
        similarity=sim if sim.get("similarity_status") == "available" else None,
        research=research if research.get("available") else None,
        knowledge=kctx,
    )
    meta["coverage_after"] = round(len(feats_after) / len(V3_FEATURE_SPECS), 4)
    meta["features_after"] = len(feats_after)
    meta["coverage_delta"] = round(meta["coverage_after"] - meta["coverage_before"], 4)
    meta["missing_features"] = [
        name for name, _, _ in V3_FEATURE_SPECS if name not in feats_after
    ]
    meta["missing_by_category"] = missing_by_category(meta["missing_features"])
    meta["scoring_components"] = dict(source.get("components") or {})
    meta["factor_count"] = source.get("factor_count")
    meta["factor_flags"] = list(source.get("factor_flags") or [])
    meta["collection_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return source, meta


def evidence_ids_for_snapshot(snap_features: dict[str, float]) -> dict[str, str]:
    ids: dict[str, str] = {}
    if any(k in snap_features for k in FEATURE_CATEGORIES["trend"]):
        ids["trend"] = "ev_pit_trend"
    if any(k in snap_features for k in FEATURE_CATEGORIES["momentum"]):
        ids["momentum"] = "ev_pit_rsi"
    if any(k in snap_features for k in FEATURE_CATEGORIES["volatility"]):
        ids["volatility"] = "ev_pit_volatility"
    if any(k in snap_features for k in FEATURE_CATEGORIES["volume"]):
        ids["volume"] = "ev_pit_volume"
    if any(k in snap_features for k in FEATURE_CATEGORIES["structure"]):
        ids["structure"] = "ev_pit_structure"
    if any(k in snap_features for k in FEATURE_CATEGORIES["similarity"]):
        ids["similarity"] = "ev_pit_similarity"
    if any(k in snap_features for k in FEATURE_CATEGORIES["knowledge"]):
        ids["knowledge"] = "ev_pit_knowledge"
    if any(k in snap_features for k in FEATURE_CATEGORIES["research"]):
        ids["research"] = "ev_pit_research"
    if any(k in snap_features for k in FEATURE_CATEGORIES["platform"]):
        ids["platform"] = "ev_pit_platform"
    return ids
