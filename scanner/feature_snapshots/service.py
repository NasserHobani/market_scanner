# -*- coding: utf-8 -*-
"""Point-in-time snapshot service — runtime capture, non-blocking."""
from __future__ import annotations

import logging
import time
from typing import Any

from .builder import build_snapshot
from .contract import PointInTimeSnapshot, SnapshotStatus
from .enrichment import (
    build_source_from_row,
    enrich_snapshot_source,
    evidence_ids_for_snapshot,
    missing_by_category,
    row_to_components,
)
from .observability import log_event
from .runtime_audit import (
    enrich_snapshot_audit,
    make_recommendation_id,
    snapshot_content_hash,
    classify_runtime_quality,
)
from .store import get_by_id, get_by_legacy, save

log = logging.getLogger("scanner.feature_snapshots.service")


class PointInTimeSnapshotService:
    """Capture snapshots at recommendation/decision time."""

    def capture_from_scan_row(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        candle_time: str,
        row: dict[str, Any],
        reco: dict[str, Any] | None = None,
        legacy_snapshot_id: str = "",
        similarity: dict[str, Any] | None = None,
        research: dict[str, Any] | None = None,
        knowledge: dict[str, Any] | None = None,
        components: dict[str, Any] | None = None,
        score_result: Any | None = None,
        skip_enrichment: bool = False,
    ) -> PointInTimeSnapshot:
        t0 = time.perf_counter()
        reco_id = make_recommendation_id(
            legacy_snapshot_id=legacy_snapshot_id,
            symbol=symbol, market=market, timeframe=timeframe, candle_time=candle_time,
        )
        log_event(
            "SNAPSHOT_STARTED",
            symbol=symbol,
            timeframe=timeframe,
            recommendation_id=reco_id,
            timestamp=candle_time,
        )
        source: dict[str, Any] = {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "decision_timestamp": candle_time,
            "feature_timestamp": candle_time,
            "candle_time": candle_time,
            "score": row.get("score"),
            "htf": row.get("htf"),
            "close": row.get("close"),
            "rsi": row.get("rsi"),
            "rvol": row.get("rvol"),
            "atr_pct": row.get("atr_pct"),
            "decision": row.get("decision"),
            "recommendation": reco or {},
            "reco": reco or {},
            "components": components or row_to_components(row) or row.get("components") or {},
            "context": {
                "rsi": row.get("rsi"),
                "rvol": row.get("rvol"),
                "atr_pct": row.get("atr_pct"),
                "delta": row.get("delta"),
                "channel": row.get("channel"),
                "ch_zone": row.get("ch_zone"),
                "htf_text": row.get("htf_text"),
                "atr_percentile": row.get("atr_percentile"),
                "volatility": row.get("volatility"),
                **(row.get("context") or {}),
            },
            "features": {
                "rsi": row.get("rsi"),
                "rvol": row.get("rvol"),
                "atr_pct": row.get("atr_pct"),
            },
            "recommendation_id": reco_id,
        }
        enrichment_meta: dict[str, Any] = {}
        collection_ms = 0.0
        sim_ctx = similarity
        res_ctx = research
        know_ctx = knowledge
        if not skip_enrichment and similarity is None and research is None and knowledge is None:
            try:
                base = build_source_from_row(
                    symbol=symbol, market=market, timeframe=timeframe,
                    row=row, reco=reco, candle_time=candle_time,
                )
                base["recommendation_id"] = reco_id
                source, enrichment_meta = enrich_snapshot_source(
                    base, score_result=score_result, market=market,
                )
                collection_ms = float(enrichment_meta.get("collection_latency_ms") or 0)
                sim_ctx = source.get("enriched_similarity")
                res_ctx = source.get("enriched_research")
                know_ctx = source.get("knowledge_context")
            except Exception as exc:  # noqa: BLE001
                enrichment_meta["collector_failures"] = [f"enrichment_failed:{str(exc)[:80]}"]
                log.warning("snapshot enrichment failed %s: %s", symbol, str(exc)[:120])
        try:
            snap = build_snapshot(
                source,
                legacy_snapshot_id=legacy_snapshot_id,
                similarity=sim_ctx if sim_ctx and sim_ctx.get("similarity_status") == "available" else sim_ctx,
                research=res_ctx if res_ctx and res_ctx.get("available") else res_ctx,
                knowledge=know_ctx,
            )
            snap.recommendation_id = reco_id
            snap.collection_latency_ms = collection_ms
            snap.enrichment_meta = enrichment_meta
            if enrichment_meta.get("missing_by_category"):
                snap.missing_by_category = dict(enrichment_meta["missing_by_category"])
            elif snap.missing_features:
                snap.missing_by_category = missing_by_category(snap.missing_features)
        except Exception as exc:  # noqa: BLE001
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            log_event(
                "SNAPSHOT_FAILED",
                symbol=symbol,
                timeframe=timeframe,
                recommendation_id=reco_id,
                reason=str(exc)[:200],
                extra={"latency_ms": latency_ms},
            )
            return PointInTimeSnapshot(
                snapshot_id="",
                symbol=symbol,
                timeframe=timeframe,
                market=market,
                decision_timestamp=candle_time,
                recommendation_id=reco_id,
                status=SnapshotStatus.FAILED.value,
                failure_reason=str(exc)[:200],
                capture_latency_ms=latency_ms,
            )

        snap = enrich_snapshot_audit(snap)
        snap.capture_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        snap.content_hash = snapshot_content_hash(snap)

        audit = classify_runtime_quality(snap)
        if not audit.get("leakage_pass", True):
            log_event(
                "LEAKAGE_DETECTED",
                symbol=symbol,
                timeframe=timeframe,
                snapshot_id=snap.snapshot_id or "",
                recommendation_id=reco_id,
                reason=";".join(audit.get("leakage_violations", [])[:3]),
            )

        if not snap.snapshot_id:
            log_event(
                "SNAPSHOT_REJECTED",
                symbol=symbol,
                timeframe=timeframe,
                recommendation_id=reco_id,
                reason=snap.failure_reason or "empty snapshot id",
                extra={"latency_ms": snap.capture_latency_ms},
            )
            return snap

        event_extra = {
            "latency_ms": snap.capture_latency_ms,
            "runtime_quality": snap.runtime_quality,
            "coverage": snap.coverage,
            "missing_reasons": snap.failure_reasons[:8],
        }
        if snap.runtime_quality == "FAILED" or snap.status == SnapshotStatus.FAILED.value:
            log_event(
                "SNAPSHOT_FAILED",
                symbol=symbol,
                timeframe=timeframe,
                snapshot_id=snap.snapshot_id,
                recommendation_id=reco_id,
                reason=";".join(snap.failure_reasons[:5]) or snap.failure_reason,
                extra=event_extra,
            )
        elif snap.status == SnapshotStatus.PARTIAL.value or snap.runtime_quality == "PARTIAL":
            log_event(
                "SNAPSHOT_PARTIAL",
                symbol=symbol,
                timeframe=timeframe,
                snapshot_id=snap.snapshot_id,
                recommendation_id=reco_id,
                extra=event_extra,
            )
        else:
            log_event(
                "SNAPSHOT_CREATED",
                symbol=symbol,
                timeframe=timeframe,
                snapshot_id=snap.snapshot_id,
                recommendation_id=reco_id,
                extra=event_extra,
            )

        try:
            save(snap)
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot persist failed: %s", exc)
            snap.status = SnapshotStatus.FAILED.value
            snap.failure_reason = f"persist failed: {exc}"[:200]
            log_event(
                "SNAPSHOT_FAILED",
                symbol=symbol,
                timeframe=timeframe,
                snapshot_id=snap.snapshot_id,
                reason=snap.failure_reason,
                extra={"latency_ms": snap.capture_latency_ms},
            )
        return snap

    def get(self, snapshot_id: str) -> PointInTimeSnapshot | None:
        return get_by_id(snapshot_id)

    def get_for_legacy(self, legacy_id: str) -> PointInTimeSnapshot | None:
        return get_by_legacy(legacy_id)

    def verify_immutable(self, snapshot_id: str, expected_hash: str) -> bool:
        snap = self.get(snapshot_id)
        if not snap:
            return False
        return snapshot_content_hash(snap) == expected_hash

    def to_udp_summary(self, snap: PointInTimeSnapshot | None) -> dict[str, Any]:
        if not snap or not snap.snapshot_id:
            return {
                "available": False,
                "quality": "UNAVAILABLE",
                "reason": snap.failure_reason if snap else "no snapshot",
            }
        quality = snap.runtime_quality or snap.quality_status
        return {
            "available": True,
            "snapshot_id": snap.snapshot_id,
            "recommendation_id": snap.recommendation_id,
            "version": snap.snapshot_version,
            "timestamp": snap.decision_timestamp,
            "coverage": snap.coverage,
            "coverage_pct": round(snap.coverage * 100, 2),
            "quality": quality,
            "feature_count": len(snap.features),
            "status": snap.status,
            "missing_features": snap.missing_features[:10],
            "missing_by_category": snap.missing_by_category,
            "failure_reasons": snap.failure_reasons[:8],
            "latency_ms": snap.capture_latency_ms,
            "collection_latency_ms": snap.collection_latency_ms,
            "enrichment": {
                "coverage_before": (snap.enrichment_meta or {}).get("coverage_before"),
                "coverage_after": (snap.enrichment_meta or {}).get("coverage_after"),
                "coverage_delta": (snap.enrichment_meta or {}).get("coverage_delta"),
            },
        }

    def summarize_for_llm(self, snap: PointInTimeSnapshot | None) -> dict[str, Any]:
        """Summarized features for Claude/Qwen — no raw OHLC."""
        if not snap or not snap.features:
            return {"available": False}
        f = snap.features
        summary = {
            "trend": {
                "direction": f.get("trend_direction"),
                "strength": f.get("trend_strength"),
                "htf": f.get("higher_timeframe_trend"),
            },
            "momentum": {
                "rsi": f.get("rsi"),
                "strength": f.get("momentum_strength"),
                "divergence": f.get("divergence"),
            },
            "volatility": {
                "atr_pct": f.get("atr_pct"),
                "atr_percentile": f.get("atr_percentile"),
                "regime": f.get("volatility_regime"),
            },
            "volume": {
                "rvol": f.get("rvol"),
                "participation": f.get("volume_participation"),
            },
            "structure": {
                "direction": f.get("structure_direction"),
                "bos_count": f.get("bos_count"),
                "choch_count": f.get("choch_count"),
            },
            "similarity": {
                "win_rate": f.get("historical_win_rate"),
                "score": f.get("similarity_score"),
                "matches": f.get("match_count"),
            },
            "knowledge": {
                "score": f.get("knowledge_score"),
                "patterns": f.get("detected_pattern_count"),
                "confidence": f.get("knowledge_confidence"),
            },
            "research": {
                "signal": f.get("research_signal"),
                "confidence": f.get("research_confidence"),
                "sample_size": f.get("research_sample_size"),
            },
            "platform": {
                "score": f.get("score"),
                "confidence": f.get("confidence"),
            },
        }
        evidence_ids = evidence_ids_for_snapshot(f)
        flat = {
            "trend_direction": f.get("trend_direction"),
            "trend_strength": f.get("trend_strength"),
            "rsi": f.get("rsi"),
            "atr_percentile": f.get("atr_percentile"),
            "rvol": f.get("rvol"),
            "structure_direction": f.get("structure_direction"),
            "similarity_win_rate": f.get("historical_win_rate"),
            "knowledge_score": f.get("knowledge_score"),
            "score": f.get("score"),
            "confidence": f.get("confidence"),
        }
        return {
            "available": True,
            "snapshot_id": snap.snapshot_id,
            "summary": {k: v for k, v in flat.items() if v is not None},
            "summary_by_category": summary,
            "evidence_id": f"ev_pit_{snap.snapshot_id[-8:]}",
            "evidence_ids": evidence_ids,
        }
