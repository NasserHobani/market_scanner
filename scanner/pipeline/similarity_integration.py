# -*- coding: utf-8 -*-
"""Similarity integration adapters — pipeline layer only."""
from __future__ import annotations

from typing import Any

from .context import NO_HISTORICAL_EVIDENCE, SimilarityContext, SimilaritySummary


def build_similarity_context(result: dict[str, Any] | None) -> SimilarityContext:
    """Convert SimilarityService output into pipeline execution context."""
    if not result or not result.get("matches"):
        return SimilarityContext(
            similarity_result=result or {},
            similarity_statistics=result.get("statistics", {}) if result else {},
            match_count=0,
            historical_evidence=(NO_HISTORICAL_EVIDENCE,),
            available=False,
        )

    stats = result.get("statistics") or {}
    matches = result.get("matches") or []
    evidence: list[str] = []
    warnings: list[str] = []

    match_count = len(matches)
    avg_sim = stats.get("avg_similarity")
    avg_r = stats.get("avg_r")
    win_rate = stats.get("win_rate")

    if match_count:
        evidence.append(f"historical_match_count={match_count}")
    if avg_sim is not None:
        evidence.append(f"historical_avg_similarity={avg_sim}%")
    if win_rate is not None:
        evidence.append(f"historical_win_rate={win_rate}%")
    if avg_r is not None:
        evidence.append(f"historical_avg_r={avg_r}R")

    for m in matches[:3]:
        oc = m.get("outcome_class") or m.get("historical_outcome") or "unknown"
        sim = m.get("similarity_score", {}).get("overall", 0)
        evidence.append(
            f"match:{m.get('event_id')} similarity={sim}% outcome={oc}"
        )

    if match_count < 3:
        warnings.append("Low historical match count")
    if avg_sim is not None and avg_sim < 50:
        warnings.append("Low average similarity score")
    if win_rate is not None and win_rate < 40:
        warnings.append("Historical win rate below 40%")
    if avg_r is not None and avg_r < 0:
        warnings.append("Negative historical average R")

    return SimilarityContext(
        similarity_result=result,
        similarity_statistics=stats,
        match_count=match_count,
        average_win_rate=win_rate,
        average_r=avg_r,
        historical_evidence=tuple(evidence) if evidence else (NO_HISTORICAL_EVIDENCE,),
        historical_warnings=tuple(warnings),
        available=match_count > 0,
    )


def build_similarity_summary(result: dict[str, Any] | None,
                             *, event_id: str = "") -> SimilaritySummary:
    """Build persisted summary with references only."""
    if not result:
        return SimilaritySummary(event_id=event_id, knowledge_event_id=event_id)

    stats = result.get("statistics") or {}
    matches = result.get("matches") or []
    query_fp = (result.get("query_fingerprint") or {}).get("fingerprint_id", "")

    top_refs = tuple(
        {
            "event_id": m.get("event_id"),
            "similarity": m.get("similarity_score", {}).get("overall"),
            "r_multiple": m.get("r_multiple"),
            "outcome_class": m.get("outcome_class"),
            "rank_score": m.get("rank_score"),
        }
        for m in matches[:5]
    )

    return SimilaritySummary(
        match_count=len(matches),
        avg_similarity=stats.get("avg_similarity"),
        avg_r=stats.get("avg_r"),
        win_rate=stats.get("win_rate"),
        query_fingerprint_id=query_fp,
        top_matches=top_refs,
        event_id=event_id,
        knowledge_event_id=event_id,
    )


def enrich_intelligence_report(report: dict[str, Any],
                               sim_ctx: SimilarityContext) -> dict[str, Any]:
    """Attach similarity statistics to intelligence report without modifying engine."""
    enriched = dict(report)
    enriched["similarity_statistics"] = {
        "match_count": sim_ctx.match_count,
        "average_win_rate": sim_ctx.average_win_rate,
        "average_r": sim_ctx.average_r,
        "statistics": dict(sim_ctx.similarity_statistics),
        "top_historical_patterns": _extract_patterns(sim_ctx),
        "historical_regimes": _extract_regimes(sim_ctx),
        "outcome_distribution": _outcome_distribution(sim_ctx),
        "available": sim_ctx.available,
    }
    return enriched


def _extract_patterns(sim_ctx: SimilarityContext) -> list[dict[str, Any]]:
    matches = (sim_ctx.similarity_result or {}).get("matches") or []
    patterns: list[dict[str, Any]] = []
    for m in matches[:5]:
        fp = m.get("fingerprint") or {}
        patterns.append({
            "event_id": m.get("event_id"),
            "similarity": m.get("similarity_score", {}).get("overall"),
            "components": fp.get("components", {}),
        })
    return patterns


def _extract_regimes(sim_ctx: SimilarityContext) -> list[dict[str, Any]]:
    matches = (sim_ctx.similarity_result or {}).get("matches") or []
    regimes: list[dict[str, Any]] = []
    for m in matches[:5]:
        fp = m.get("fingerprint") or {}
        comp = fp.get("components") or {}
        regimes.append({
            "event_id": m.get("event_id"),
            "regime": comp.get("regime"),
            "market": m.get("market"),
            "timeframe": m.get("timeframe"),
        })
    return regimes


def _outcome_distribution(sim_ctx: SimilarityContext) -> dict[str, int]:
    matches = (sim_ctx.similarity_result or {}).get("matches") or []
    dist: dict[str, int] = {}
    for m in matches:
        oc = m.get("outcome_class") or m.get("historical_outcome") or "unknown"
        dist[oc] = dist.get(oc, 0) + 1
    return dist
